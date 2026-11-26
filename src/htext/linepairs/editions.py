"""Book-level Rivok-method line pairs: an edition scan plus a whole-book transcription of the same edition.

Input: an edition-pair manifest (heocr-ops records/real-line-edition-pairs-*/consumer-pilot.json): per pair, the scan
(URL, sha256), the transcription (PBY plain text, a Sefaria named-version JSON, or a Wikisource HTML snapshot; URL,
sha256), and the scan pages to use, in reading order, with any exact eval test pages already excluded.

Pass 1 fetches and verifies every input and OCRs the pages (hOCR cached). Pass 2 anchors the pair's OCR against the
whole transcription (htext.linepairs.book), gives each page its slice, and runs the page through the same aligner,
label rules, two-line check, crops and receipts as the Wikisource Index/Page pilot (htext.linepairs.wikisource).
Exclusion is page-only: a page listed as an exact test page is never processed.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import html
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from htext.linepairs import book as B
from htext.linepairs import rivok_align as A
from htext.linepairs import wikisource as W

UA = "htext-fetch/0.1 (https://github.com/HeOCR/htext)"


def fetch(url: str, dest: Path, sha256: str, local: Path | None = None) -> Path:
    """Download (or reuse a local copy) and verify sha256; back off politely on errors."""
    if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest() == sha256:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    if local and local.exists() and hashlib.sha256(local.read_bytes()).hexdigest() == sha256:
        dest.write_bytes(local.read_bytes())
        return dest
    for attempt in range(5):
        r = subprocess.run(["curl", "-sSfL", "-A", UA, "-o", str(dest), url], capture_output=True, text=True)
        if r.returncode == 0 and hashlib.sha256(dest.read_bytes()).hexdigest() == sha256:
            return dest
        time.sleep(30 * (attempt + 1))
    raise ValueError(f"{url}: could not fetch bytes matching sha256 {sha256}")


def transcription_text(path: Path, fmt: str) -> str:
    raw = path.read_bytes().decode("utf-8-sig")
    if "JSON" in fmt or path.suffix == ".json":
        from htext.sefaria import clean_segment, segments
        return " ".join(clean_segment(seg) for _, seg in segments(json.loads(raw).get("text")))
    if "HTML" in fmt or path.suffix in (".html", ".htm"):
        body = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", raw)
        return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body))).strip()
    return raw


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--local-copies", type=Path, default=None, help="optional json: pair id -> local scan/transcription paths")
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--tessdata", type=Path, required=True)
    ap.add_argument("--lang", default="heb_rivok")
    ap.add_argument("--unicharset", type=Path, default=None)
    ap.add_argument("--jobs", type=int, default=6)
    a = ap.parse_args()
    from concurrent.futures import ProcessPoolExecutor

    man = json.loads(a.manifest.read_text(encoding="utf-8"))
    local = json.loads(a.local_copies.read_text(encoding="utf-8")) if a.local_copies else {}
    model_sha256 = hashlib.sha256((a.tessdata / f"{a.lang}.traineddata").read_bytes()).hexdigest()
    ok_chars = sorted(W.L.allowed_chars(a.unicharset)) if a.unicharset else None
    out = a.work / "pilot"
    report: dict[str, Any] = {}
    jobs_all: list[dict[str, Any]] = []
    for pair in man["pairs"]:
        pid = pair["id"]
        s, t = pair["scan"], pair["transcription"]
        loc = local.get(pid, {})
        scan = fetch(s["url"], a.work / "scans" / f"{pid}.pdf", s["sha256"], Path(loc["scan"]) if loc.get("scan") else None)
        suffix = ".json" if "JSON" in t.get("format", "") else ".html" if "HTML" in t.get("format", "") else ".txt"
        tpath = fetch(t["url"], a.work / "texts" / f"{pid}{suffix}", t["sha256"], Path(loc["text"]) if loc.get("text") else None)
        text_words = A.tidy_ocr_words(transcription_text(tpath, t.get("format", "")).split())
        excluded = set(pair.get("exact_test_pages_excluded") or [])
        pages = [n for n in pair["pilot_pdf_ordinals_in_reading_order"] if n not in excluded]
        # pass 1: page images and hOCR (cached)
        W.A.TESSDATA = str(a.tessdata)
        hocr = {}
        for n in pages:
            png = W.page_image(scan, n, out / "pages" / pid / f"p{n:04d}.png")
            h = out / "hocr" / pid / f"p{n:04d}.hocr"
            if not h.exists():
                h.parent.mkdir(parents=True, exist_ok=True)
                tmp = h.parent / f".tmp_p{n:04d}"
                A.run_tesseract(png, tmp, 3, lang=a.lang)
                tmp.with_suffix(".hocr").replace(h)
            hocr[n] = [ln for ln in A.read_hocr(h) if W._hebrew_share(" ".join(ln[1])) >= 0.5]
        # pass 2: anchors and slices
        ocr_words, page_of = [], []
        for n in pages:
            for _, ws in hocr[n]:
                ocr_words += ws
                page_of += [n] * len(ws)
        chain = B.anchors(ocr_words, text_words)
        slices = {sl.page: sl for sl in B.page_slices(page_of, len(text_words), chain)}
        report[pid] = {"pages": len(pages), "pages_sliced": len(slices), "anchors": len(chain), "text_words": len(text_words)}
        for n in pages:
            if n not in slices:
                continue
            sl = slices[n]
            jobs_all.append({"out": str(out), "book": pid, "index": pid, "n": n, "page_id": None, "rev": t["sha256"][:12],
                             "quality": None, "tags": ["book_level", f"source:{t.get('provider', '')}"],
                             "scan": str(scan), "wikitext": " ".join(text_words[sl.start:sl.end]),
                             "tessdata": str(a.tessdata), "lang": a.lang, "ok_chars": ok_chars,
                             "scan_sha1": s.get("sha1"), "model_sha256": model_sha256})
    totals: collections.Counter = collections.Counter()
    per_pair: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    with ProcessPoolExecutor(a.jobs) as ex:
        for job, r in zip(jobs_all, ex.map(W.do_page, jobs_all, chunksize=1)):
            c = per_pair[job["book"]]
            c["ocr_lines"] += r["ocr_lines"]
            c["kept"] += len(r["kept"])
            for why, k in r["dropped"].items():
                c[f"dropped:{why}"] += k
            totals.update(c if False else {})
    for pid, c in per_pair.items():
        report[pid].update(dict(c))
        totals.update(c)
    report["_totals"] = dict(totals)
    W.atomic_write(a.work / "report.json", json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

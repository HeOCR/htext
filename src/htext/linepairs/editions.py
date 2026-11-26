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


def _digest(path: Path, algo: str) -> str:
    return hashlib.new(algo, path.read_bytes()).hexdigest()


def fetch(url: str, dest: Path, digest: str, local: Path | None = None, algo: str = "sha256") -> Path:
    """Download (or reuse a local copy) and verify the pinned digest; back off politely on errors."""
    if dest.exists() and _digest(dest, algo) == digest:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    if local and local.exists() and _digest(local, algo) == digest:
        dest.write_bytes(local.read_bytes())
        return dest
    for attempt in range(5):
        r = subprocess.run(["curl", "-sSfL", "-A", UA, "-o", str(dest), url], capture_output=True, text=True)
        if r.returncode == 0 and _digest(dest, algo) == digest:
            return dest
        time.sleep(30 * (attempt + 1))
    raise ValueError(f"{url}: could not fetch bytes matching {algo} {digest}")


def safe_id(pid: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", pid)[:40].strip("_") + "_" + hashlib.sha1(pid.encode()).hexdigest()[:8]


def _ocr(job: tuple[str, str, str, str]) -> str:
    png, hocr, tessdata, lang = Path(job[0]), Path(job[1]), job[2], job[3]
    if not hocr.exists():
        hocr.parent.mkdir(parents=True, exist_ok=True)
        A.TESSDATA = tessdata
        tmp = hocr.parent / f".tmp_{hocr.stem}"
        A.run_tesseract(png, tmp, 3, lang=lang)
        tmp.with_suffix(".hocr").replace(hocr)
    return str(hocr)


def pair_pages(pair: dict[str, Any], work: Path, out: Path, local: dict[str, Any]) -> tuple[list[int], dict[int, Path], str | None]:
    """The pair's pages in reading order and their grayscale page images (built and cached).
    Schemas: pilot (scan.sha256 + pilot_pdf_ordinals_in_reading_order); batch (scope.bound_native_pages with per-page
    JP2 URL + sha256, or scope.pdf_ordinal_ranges_inclusive over a PDF pinned by sha1)."""
    from PIL import Image
    sid, s, scope = safe_id(pair["id"]), pair["scan"], pair.get("scope", {})
    excluded = set(pair.get("exact_test_pages_excluded") or [])
    pngs: dict[int, Path] = {}
    if scope.get("bound_native_pages"):
        for bp in scope["bound_native_pages"]:
            n = int(bp["native_leaf"])
            if n in excluded:
                continue
            png = out / "pages" / sid / f"p{n:04d}.png"
            if not png.exists():
                jp2 = fetch(bp["url"], work / "jp2" / sid / f"{n:04d}.jp2", bp["sha256"])
                png.parent.mkdir(parents=True, exist_ok=True)
                Image.open(jp2).convert("L").save(png)
            pngs[n] = png
        order = [n for n in (scope.get("native_leaves_in_reading_order") or [int(b["native_leaf"]) for b in scope["bound_native_pages"]]) if n in pngs]
        return order, pngs, s.get("sha1")
    algo, digest = ("sha256", s["sha256"]) if s.get("sha256") else ("sha1", s["sha1"])
    loc = local.get(pair["id"], {})
    scan = fetch(s["url"], work / "scans" / f"{sid}.pdf", digest, Path(loc["scan"]) if loc.get("scan") else None, algo)
    if scope.get("pdf_ordinal_ranges_inclusive"):
        order = [n for a_, b_ in scope["pdf_ordinal_ranges_inclusive"] for n in range(a_, b_ + 1)]
    else:
        order = list(pair.get("pilot_pdf_ordinals_in_reading_order") or scope.get("pilot_pdf_ordinals_in_reading_order") or [])
    order = [n for n in order if n not in excluded]
    for n in order:
        pngs[n] = W.page_image(scan, n, out / "pages" / sid / f"p{n:04d}.png")
    return order, pngs, s.get("sha1")


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
    ap.add_argument("--skip-prefix", action="append", default=[], help="skip pairs whose id starts with this (e.g. multi-commentary pages)")
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
        if any(pid.startswith(x) for x in a.skip_prefix):
            report[pid] = {"skipped": "skip_prefix"}
            continue
        sid, t = safe_id(pid), pair["transcription"]
        loc = local.get(pid, {})
        fmt = t.get("format") or ("JSON" if t.get("source") == "Sefaria" else "text")
        suffix = ".json" if "JSON" in fmt else ".html" if "HTML" in fmt else ".txt"
        tpath = fetch(t["url"], a.work / "texts" / f"{sid}{suffix}", t["sha256"], Path(loc["text"]) if loc.get("text") else None)
        text_words = A.tidy_ocr_words(transcription_text(tpath, fmt).split())
        pages, pngs, scan_sha1 = pair_pages(pair, a.work, out, local)
        # pass 1: hOCR for every page (parallel, cached)
        with ProcessPoolExecutor(a.jobs) as ex:
            list(ex.map(_ocr, [(str(pngs[n]), str(out / "hocr" / sid / f"p{n:04d}.hocr"), str(a.tessdata), a.lang) for n in pages]))
        hocr = {n: [ln for ln in A.read_hocr(out / "hocr" / sid / f"p{n:04d}.hocr") if W._hebrew_share(" ".join(ln[1])) >= 0.5] for n in pages}
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
            jobs_all.append({"out": str(out), "book": sid, "index": pid, "n": n, "page_id": None, "rev": t["sha256"][:12],
                             "quality": None, "tags": ["book_level"], "scan": str(pngs[n]),
                             "wikitext": " ".join(text_words[sl.start:sl.end]),
                             "tessdata": str(a.tessdata), "lang": a.lang, "ok_chars": ok_chars,
                             "scan_sha1": scan_sha1, "model_sha256": model_sha256})
    totals: collections.Counter = collections.Counter()
    per_pair: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    with ProcessPoolExecutor(a.jobs) as ex:
        for job, r in zip(jobs_all, ex.map(W.do_page, jobs_all, chunksize=1)):
            c = per_pair[job["book"]]
            c["ocr_lines"] += r["ocr_lines"]
            c["kept"] += len(r["kept"])
            for why, k in r["dropped"].items():
                c[f"dropped:{why}"] += k
    for pid, c in per_pair.items():
        report[pid].update(dict(c))
        totals.update(c)
    report["_totals"] = dict(totals)
    W.atomic_write(a.work / "report.json", json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

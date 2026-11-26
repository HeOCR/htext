"""Real line pairs from Hebrew Wikisource proofread pages and their scans, by Rivok's method.

Credit: the method, the aligner (``rivok_align``) and the label rules (``rivok_labels``) are Rivok's
(RivoksLab/tesseract-heb-rivok, training/v2/lines, Apache-2.0). HeOCR's changes:

- books: every Index: book with proofread pages, from the Wikimedia dumps (a census, not a hand list); the page text
  is the dump's wikitext (``clean_wikitext``), since robots.txt disallows the API that serves rendered HTML;
- scans: the original file from upload.wikimedia.org (Commons or local), PDF or DjVu;
- line cutter: Tesseract with Rivok's model (heb_rivok 2.0 Full by default), psm 3, hOCR;
- validated (quality 4) pages are kept, tagged ``validated_page``, unless a benchmark draws its test pages from them;
- eval's exact test pages are excluded (any render or crop of them); other pages of the same books are tagged
  ``same_source_as_eval``; DEV pages eval names are excluded for DEV integrity;
- every drop is counted by reason, so the keep rate and the rejection reasons can be reported.

A line is kept when both its ends are anchored and its no-marks CER against the OCR is at most 0.25, and the label
rules do not reject it; the label is the proofread text cut at the OCR's line breaks.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from htext.linepairs import rivok_align as A
from htext.linepairs import rivok_labels as L

MAX_CER = 0.25


# ---------------------------------------------------------------- page images
def _pdf_page(pdf: Path, n: int, out: Path) -> None:
    r = subprocess.run(["pdfimages", "-list", "-f", str(n), "-l", str(n), str(pdf)], capture_output=True, text=True)
    imgs = [line.split() for line in r.stdout.splitlines()[2:]]
    imgs = [f for f in imgs if len(f) >= 14 and f[2] == "image"]
    with tempfile.TemporaryDirectory(dir=out.parent) as td:
        if len(imgs) == 1:
            subprocess.run(["pdfimages", "-png", "-f", str(n), "-l", str(n), str(pdf), f"{td}/x"], check=True, capture_output=True)
            got = sorted(Path(td).glob("x-*.png"))
            if len(got) == 1:
                shutil.move(got[0], out)
                return
        ppi = max([int(f[12]) for f in imgs if f[12].isdigit()] or [300]) or 300
        ppi = min(max(ppi, 200), 600)
        subprocess.run(["pdftoppm", "-r", str(ppi), "-gray", "-png", "-singlefile", "-f", str(n), "-l", str(n), str(pdf), f"{td}/r"],
                       check=True, capture_output=True)
        shutil.move(Path(td) / "r.png", out)


def _djvu_page(djvu: Path, n: int, out: Path) -> None:
    from PIL import Image
    with tempfile.TemporaryDirectory(dir=out.parent) as td:
        tif = Path(td) / "p.tif"
        subprocess.run(["ddjvu", "-format=tiff", f"-page={n}", str(djvu), str(tif)], check=True, capture_output=True)
        Image.open(tif).convert("L").save(out)


def page_image(scan: Path, n: int, out: Path) -> Path:
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        (_djvu_page if scan.suffix.lower() == ".djvu" else _pdf_page)(scan, n, out)
    return out


# ---------------------------------------------------------------- labels (Rivok's build_lines.label_of, HeOCR changes)
def label_of(r: dict[str, Any], ok_chars: set[str] | None) -> tuple[str | None, str | None]:
    if not r["gt"]:
        return None, "no_text"
    if not r["anchored"]:
        return None, "unanchored"
    if r["cer_nomarks"] > MAX_CER:
        return None, "cer_over_0.25"
    label = r["gt"]
    if prob := L.label_problem(label, r["ocr"]):
        return None, prob
    letters = len(re.findall(r"[א-ת]", label)) or 1
    if len(L.NIQ.findall(label)) >= 3 and len(L.NIQ.findall(label)) / letters >= 0.4 and not L.NIQ.search(r["ocr"]):
        label = L.COMB.sub("", label)  # editorial niqqud on an unvowelled print
    label = L.normalise(label, collections.Counter())
    if L.CANT.search(label):
        return None, "cantillation"
    if "mw-parser-output" in label or re.search(r"[{}]", label):
        return None, "markup"
    if not label:
        return None, "empty"
    label = label.replace("׃", ":").replace("‍", "")
    ocr = r["ocr"]
    if ok_chars is not None and set(label) - ok_chars:
        return None, "charset"
    if L.plene(label, ocr):
        return None, "plene"
    if len(L.ABBR.findall(ocr)) > len(L.ABBR.findall(label)) and len(label.split()) > len(ocr.split()):
        return None, "abbreviation"
    if (L.NOTE.search(label) and not L.NOTE.search(ocr)) or ("[" in label and "[" not in ocr):
        return None, "editor_note"
    return label, None


# ---------------------------------------------------------------- one page
def do_page(job: dict[str, Any]) -> dict[str, Any]:
    out = Path(job["out"])
    book, n = job["book"], job["n"]
    res: dict[str, Any] = {"book": book, "n": n, "page_id": job["page_id"], "rev": job["rev"], "quality": job["quality"],
                           "tags": job["tags"], "kept": [], "dropped": collections.Counter(), "ocr_lines": 0}
    try:
        png = page_image(Path(job["scan"]), n, out / "pages" / book / f"p{n:04d}.png")
        A.TESSDATA = job["tessdata"]
        hdir = out / "hocr" / book
        hdir.mkdir(parents=True, exist_ok=True)
        hocr = hdir / f"p{n:04d}.hocr"
        if not hocr.exists():
            A.run_tesseract(png, hdir / f"p{n:04d}", 3, lang=job["lang"])
        body, notes, seen = A.clean_wikitext(job["wikitext"])
        rows = A.align_page(A.read_hocr(hocr), (body + " " + notes).strip(), "wiki")
    except Exception as e:  # noqa: BLE001 - a page failure is a counted drop, never a crash
        res["error"] = f"{type(e).__name__}: {e}"[:200]
        return res
    res["ocr_lines"] = len(rows)
    ok_chars = set(job["ok_chars"]) if job.get("ok_chars") else None
    keep = []
    for r in rows:
        label, why = label_of(r, ok_chars)
        if why:
            res["dropped"][why] += 1
        else:
            keep.append(dict(r, gt=label))
    if keep:
        A.crop_lines(png, keep, out / "lines" / book / f"p{n:04d}", f"p{n:04d}")
    res["kept"] = [{"line": r["line"], "label": r["gt"], "ocr": r["ocr"], "cer_nomarks": r["cer_nomarks"], "bbox": r["bbox"]} for r in keep]
    res["dropped"] = dict(res["dropped"])
    return res


def book_key(index: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "_", Path(index).stem)[:40].strip("_") or "heb"
    return f"{stem}_{hashlib.sha1(index.encode()).hexdigest()[:8]}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Rivok-method real line pairs from Wikisource proofread pages")
    ap.add_argument("--pages", type=Path, required=True, help="pages.jsonl: proofread Page: pages from the dump")
    ap.add_argument("--scans", type=Path, required=True, help="scan_sizes.json: index -> url, and the local scan dir")
    ap.add_argument("--scan-dir", type=Path, required=True)
    ap.add_argument("--exclude", type=Path, action="append", default=[], help="eval page lists (wikisource_page titles)")
    ap.add_argument("--tessdata", type=Path, required=True)
    ap.add_argument("--lang", default="heb_rivok")
    ap.add_argument("--unicharset", type=Path, default=None)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--books", nargs="*", default=None)
    a = ap.parse_args()
    excluded: set[str] = set()
    for p in a.exclude:
        d = json.loads(p.read_text(encoding="utf-8"))
        excluded |= {r["wikisource_page"].split(":", 1)[-1] for r in d["pages"]}
    excluded_books = {t.rsplit("/", 1)[0] for t in excluded}
    scans = {s["index"]: s for s in json.loads(a.scans.read_text(encoding="utf-8")) if not s.get("error")}
    ok_chars = sorted(L.allowed_chars(a.unicharset)) if a.unicharset else None
    jobs, skipped = [], collections.Counter()
    for line in a.pages.read_text(encoding="utf-8").splitlines():
        p = json.loads(line)
        title = f"{p['index']}/{p['n']}"
        if a.books and p["index"] not in a.books:
            continue
        if title in excluded:
            skipped["eval_test_or_dev_page"] += 1
            continue
        if p["index"] not in scans:
            skipped["no_scan"] += 1
            continue
        tags = ["validated_page"] if p["quality"] == 4 else []
        if p["eval_reserved_book"] or p["index"] in excluded_books:
            tags.append("same_source_as_eval")
        scan = a.scan_dir / (book_key(p["index"]) + Path(p["index"]).suffix.lower())
        jobs.append({"out": str(a.out), "book": book_key(p["index"]), "index": p["index"], "n": p["n"], "page_id": p["page_id"],
                     "rev": p["rev"], "quality": p["quality"], "tags": tags, "scan": str(scan), "wikitext": p["wikitext"],
                     "tessdata": str(a.tessdata), "lang": a.lang, "ok_chars": ok_chars})
    print(f"{len(jobs)} pages; skipped {dict(skipped)}", flush=True)
    a.out.mkdir(parents=True, exist_ok=True)
    pages_out = (a.out / "pages.jsonl").open("w", encoding="utf-8")
    pool = (a.out / "pool.tsv").open("w", encoding="utf-8")
    pool.write("book\tindex\tpage\tline\tquality\ttags\tcer_nomarks\tlabel\n")
    totals = collections.Counter()
    index_of = {j["book"]: j["index"] for j in jobs}
    with ProcessPoolExecutor(a.jobs) as ex:
        for k, r in enumerate(ex.map(do_page, jobs, chunksize=1), 1):
            totals["pages"] += 1
            totals["ocr_lines"] += r["ocr_lines"]
            totals["kept"] += len(r["kept"])
            if "error" in r:
                totals["page_errors"] += 1
            for why, c in r["dropped"].items():
                totals[f"dropped:{why}"] += c
            for x in r["kept"]:
                pool.write(f"{r['book']}\t{index_of[r['book']]}\t{r['n']}\t{x['line']}\t{r['quality']}\t{','.join(r['tags'])}\t{x['cer_nomarks']}\t{x['label']}\n")
            pages_out.write(json.dumps({k2: v for k2, v in r.items() if k2 != "kept"} | {"kept": len(r["kept"])}, ensure_ascii=False) + "\n")
            if k % 50 == 0:
                print(f"{k}/{len(jobs)} pages, kept {totals['kept']}", flush=True)
    pages_out.close()
    pool.close()
    (a.out / "summary.json").write_text(json.dumps({"skipped": skipped, "totals": totals}, indent=1) + "\n", encoding="utf-8")
    print("DONE", dict(totals))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

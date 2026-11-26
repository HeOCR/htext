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
CODE_VERSION = "linepairs-wikisource-5"


def atomic_write(path: Path, data: str) -> None:
    """Write via a temp file in the same dir, fsync, rename: a crash leaves the old file or none, never half."""
    import os
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def input_key(job: dict[str, Any]) -> str:
    h = hashlib.sha256()
    for k in ("index", "n", "rev", "quality", "scan_sha1", "model_sha256", "lang", "wikitext"):
        h.update(f"{k}={job.get(k)}\n".encode("utf-8"))
    h.update(CODE_VERSION.encode())  # HeOCR: tags are not in the key; they are applied when the pool is written
    h.update(json.dumps(job.get("ok_chars")).encode())
    return h.hexdigest()


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


_HE_SECTION = re.compile(r"<\s*קטע\b[^>]*>")
_HEADING = re.compile(r"={2,}")
_RESIDUE = re.compile(r"[#=/<>\\*{}|]|[A-Za-z]{2,}")


def _pre_clean(wikitext: str) -> str:
    """HeOCR: he.wikisource markup Rivok's cleaner does not know: Hebrew section tags and in-text heading markers."""
    return _HEADING.sub(" ", _HE_SECTION.sub(" ", wikitext))


def _hebrew_share(s: str) -> float:
    heb = len(re.findall(r"[א-ת]", s))
    lat = len(re.findall(r"[A-Za-z]", s))
    return heb / (heb + lat) if heb + lat else 0.0


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
    if _RESIDUE.search(label) and not _RESIDUE.search(ocr):
        return None, "markup_residue"  # HeOCR: wikitext the cleaner missed; never let it into a label
    # HeOCR (QA v1): a pointed print whose label is only partly pointed teaches a model to drop niqqud.
    o_letters = len(re.findall(r"[א-ת]", ocr)) or 1
    o_niq = len(L.NIQ.findall(ocr)) / o_letters
    if o_niq >= 0.25 and len(L.NIQ.findall(label)) / letters < 0.5 * o_niq:
        return None, "printed_vowels_partial"
    # HeOCR (QA v1): printed digits (verse or note numbers) that the label renders otherwise or leaves out.
    if re.search(r"[0-9]", ocr) and not re.search(r"[0-9]", label):
        return None, "digits_missing"
    return label, None


def text_bands(crop) -> int:
    """Number of text lines in a crop, from its row ink profile: bands at least 40% as tall as the tallest.
    Niqqud and dots make thin bands, so they do not count; two printed lines make two comparable bands."""
    import numpy as np
    a = np.asarray(crop.convert("L"), dtype=np.float32)
    ink = (a < 128).mean(axis=1)
    on = ink > max(0.02, 0.15 * ink.max())
    bands, run = [], 0
    for v in list(on) + [False]:
        if v:
            run += 1
        elif run:
            bands.append(run)
            run = 0
    if not bands:
        return 0
    tall = max(bands)
    return sum(b >= 0.4 * tall for b in bands)


# ---------------------------------------------------------------- one page
def do_page(job: dict[str, Any]) -> dict[str, Any]:
    out = Path(job["out"])
    book, n = job["book"], job["n"]
    receipt = out / "receipts" / book / f"p{n:04d}.json"
    key_ = input_key(job)
    if receipt.exists():
        done = json.loads(receipt.read_text(encoding="utf-8"))
        if done.get("input_key") == key_:
            done["resumed"] = True
            return done
    res = _compute_page(job, out, book, n)
    res["input_key"] = key_
    if "error" not in res:  # a failed page is retried on the next run
        atomic_write(receipt, json.dumps(res, ensure_ascii=False, sort_keys=True))
    return res


def _compute_page(job: dict[str, Any], out: Path, book: str, n: int) -> dict[str, Any]:
    res: dict[str, Any] = {"book": book, "n": n, "page_id": job["page_id"], "rev": job["rev"], "quality": job["quality"],
                           "tags": job["tags"], "kept": [], "dropped": collections.Counter(), "ocr_lines": 0}
    try:
        png = page_image(Path(job["scan"]), n, out / "pages" / book / f"p{n:04d}.png")
        A.TESSDATA = job["tessdata"]
        hdir = out / "hocr" / book
        hdir.mkdir(parents=True, exist_ok=True)
        hocr = hdir / f"p{n:04d}.hocr"
        if not hocr.exists():
            import os
            tmpbase = hdir / f".tmp{os.getpid()}_p{n:04d}"
            A.run_tesseract(png, tmpbase, 3, lang=job["lang"])
            os.replace(tmpbase.with_suffix(".hocr"), hocr)  # a partial hOCR is never reused
        body, notes, seen = A.clean_wikitext(_pre_clean(job["wikitext"]))
        lines = A.read_hocr(hocr)
        # HeOCR: bilingual pages (Hebrew with an English translation): Latin-script OCR lines have no Hebrew text to
        # align with and break the anchors of the Hebrew lines around them, so they stay out of the alignment.
        heb = [ln for ln in lines if _hebrew_share(" ".join(ln[1])) >= 0.5]
        non_hebrew = len(lines) - len(heb)
        rows = A.align_page(heb, (body + " " + notes).strip(), "wiki")
    except Exception as e:  # noqa: BLE001 - a page failure is a counted drop, never a crash
        res["error"] = f"{type(e).__name__}: {e}"[:200]
        return res
    res["ocr_lines"] = len(rows) + non_hebrew
    if non_hebrew:
        res["dropped"]["non_hebrew_line"] += non_hebrew
    ok_chars = set(job["ok_chars"]) if job.get("ok_chars") else None
    keep = []
    for r in rows:
        label, why = label_of(r, ok_chars)
        if why:
            res["dropped"][why] += 1
        else:
            keep.append(dict(r, gt=label))
    if keep:
        from PIL import Image
        page_im = Image.open(png).convert("L")
        single = []
        for r in keep:
            x0, y0, x1, y1 = r["bbox"]
            if text_bands(page_im.crop((x0, y0, x1, y1))) > 1:
                res["dropped"]["multi_line_box"] += 1  # HeOCR (QA v1): the box holds two printed lines, the label one
            else:
                single.append(r)
        keep = single
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
    ap.add_argument("--scan-ledger", type=Path, required=True, help="jsonl: index, file, sha1 of each downloaded scan")
    ap.add_argument("--exclude-dev", type=Path, action="append", default=[], help="eval DEV page lists: excluded for DEV hygiene")
    ap.add_argument("--tag-index", action="append", default=[], help="INDEX=TAG: a reporting tag for every page of that Index (never an exclusion)")
    a = ap.parse_args()
    scan_sha1 = {}
    for line in a.scan_ledger.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("ok"):
            scan_sha1[r["index"]] = r["sha1"]
    model_sha256 = hashlib.sha256((a.tessdata / f"{a.lang}.traineddata").read_bytes()).hexdigest()
    def titles(paths: list[Path]) -> set[str]:
        out: set[str] = set()
        for path in paths:
            out |= {r["wikisource_page"].split(":", 1)[-1] for r in json.loads(path.read_text(encoding="utf-8"))["pages"]}
        return out
    test_pages, dev_pages = titles(a.exclude), titles(a.exclude_dev)
    excluded = test_pages | dev_pages  # exact pages only; books are never excluded
    test_books = {t.rsplit("/", 1)[0] for t in test_pages}
    dev_books = {t.rsplit("/", 1)[0] for t in dev_pages}
    scans = {s["index"]: s for s in json.loads(a.scans.read_text(encoding="utf-8")) if not s.get("error")}
    ok_chars = sorted(L.allowed_chars(a.unicharset)) if a.unicharset else None
    jobs, skipped = [], collections.Counter()
    for line in a.pages.read_text(encoding="utf-8").splitlines():
        p = json.loads(line)
        title = f"{p['index']}/{p['n']}"
        if a.books and p["index"] not in a.books:
            continue
        if title in test_pages:
            skipped["eval_test_page"] += 1
            continue
        if title in dev_pages:
            skipped["eval_dev_page"] += 1
            continue
        if p["index"] not in scans or p["index"] not in scan_sha1:
            skipped["no_scan"] += 1
            continue
        tags = ["validated_page"] if p["quality"] == 4 else []
        tags += [tg for ix, tg in (x.split("=", 1) for x in a.tag_index) if ix == p["index"]]
        if p["eval_reserved_book"] or p["index"] in test_books:
            tags.append("same_source_as_eval_test")
        if p["index"] in dev_books:
            tags.append("same_source_as_eval_dev")
        scan = a.scan_dir / (book_key(p["index"]) + Path(p["index"]).suffix.lower())
        jobs.append({"out": str(a.out), "book": book_key(p["index"]), "index": p["index"], "n": p["n"], "page_id": p["page_id"],
                     "rev": p["rev"], "quality": p["quality"], "tags": tags, "scan": str(scan), "wikitext": p["wikitext"],
                     "tessdata": str(a.tessdata), "lang": a.lang, "ok_chars": ok_chars,
                     "scan_sha1": scan_sha1[p["index"]], "model_sha256": model_sha256})
    print(f"{len(jobs)} pages; skipped {dict(skipped)}", flush=True)
    a.out.mkdir(parents=True, exist_ok=True)
    pages_out = (a.out / ".pages.jsonl.tmp").open("w", encoding="utf-8")
    pool = (a.out / ".pool.tsv.tmp").open("w", encoding="utf-8")
    pool.write("book\tindex\tpage\tline\tquality\ttags\tcer_nomarks\tlabel\n")
    totals = collections.Counter()
    index_of = {j["book"]: j["index"] for j in jobs}
    with ProcessPoolExecutor(a.jobs) as ex:
        for k, (job, r) in enumerate(zip(jobs, ex.map(do_page, jobs, chunksize=1)), 1):
            r["tags"] = job["tags"]
            totals["pages"] += 1
            totals["pages_resumed"] += bool(r.get("resumed"))
            totals["ocr_lines"] += r["ocr_lines"]
            totals["kept"] += len(r["kept"])
            if "error" in r:
                totals["page_errors"] += 1
            for why, c in r["dropped"].items():
                totals[f"dropped:{why}"] += c
            for x in r["kept"]:
                pool.write(f"{r['book']}\t{index_of[r['book']]}\t{r['n']}\t{x['line']}\t{r['quality']}\t{','.join(r['tags'])}\t{x['cer_nomarks']}\t{x['label']}\n")
            pages_out.write(json.dumps({k2: v for k2, v in r.items() if k2 not in ("kept", "resumed")} | {"kept": len(r["kept"])}, ensure_ascii=False, sort_keys=True) + "\n")
            if k % 50 == 0:
                print(f"{k}/{len(jobs)} pages, kept {totals['kept']}", flush=True)
    import os
    for f, name in ((pages_out, "pages.jsonl"), (pool, "pool.tsv")):
        f.flush()
        os.fsync(f.fileno())
        f.close()
        os.replace(a.out / f".{name}.tmp", a.out / name)
    (a.out / "summary.json").write_text(json.dumps({"skipped": skipped, "totals": totals}, indent=1) + "\n", encoding="utf-8")
    print("DONE", dict(totals))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

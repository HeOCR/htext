"""Package Rivok-method line pairs as a versioned dataset (Parquet shards), with per-line licence bases and tags.

Text: Wikisource proofread transcriptions, CC BY-SA 4.0 (credit: the Wikisource page and its history).
Images: crops of the scan, under the scan file's own licence (its Commons / Wikisource file description page). Each
line carries ``image_licence_basis``:

- ``pd_il``: public domain in Israel as well (PD-old*, PD-Israel, PD-scan of such a work, PD-author releases);
- ``pd_us_only``: public domain in the United States only (PD-US-*, PD-1996 without an old-work tag);
- ``cc0`` / ``cc_by`` / ``cc_by_sa``: the file's free licence;
- ``unclear``: none of the above, listed for a decision.

``--public-bases`` selects what goes into the public shards; every other line goes to internal shards (training only).
Exact eval test pages and DEV pages are refused if present (they are excluded upstream, page by page).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

PUBLIC_DEFAULT = ("pd_il", "cc0", "cc_by", "cc_by_sa")
SHARD_ROWS = 20000


def licence_basis(lic: dict[str, Any]) -> str:
    cats = " | ".join(lic.get("licence_categories", []))
    short = " | ".join(lic.get("licence_short", [])) + " | "  # separator: never glue the two lists
    if re.search(r"CC[- ]BY[- ]SA", short + cats, re.I):
        return "cc_by_sa"
    if re.search(r"CC[- ]BY(?![- ]SA)", short + cats, re.I):
        return "cc_by"
    if re.search(r"\bCC0\b", short + cats, re.I):
        return "cc0"
    old = re.search(r"PD[- ]old|PD-Israel|Public domain in Israel|PD-author|PD-self|PD-user|author died more than", cats, re.I)
    us = re.search(r"PD-US|PD-1996|not renewed|no notice|published in the United States", cats, re.I)
    if old:
        return "pd_il"
    if us:
        return "pd_us_only"
    if re.search(r"PD-scan", cats, re.I):
        return "unclear"  # PD-scan rests on the underlying work's status, which the page does not state
    return "unclear"


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    with tmp.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


CARD = """---
license: cc-by-sa-4.0
language:
- he
task_categories:
- image-to-text
pretty_name: Hebrew print line pairs
size_categories:
- 10K<n<100K
configs:
- config_name: default
  data_files:
  - split: train
    path: public/*.parquet
---

# Hebrew print line pairs ({version})

{public:,} printed Hebrew text lines from {books} public-domain books (16th to 20th century). Each line is an image crop from
the book's scan, with the proofread transcription of exactly that line. They are training data for Hebrew OCR.
They are built by HeOCR from Hebrew Wikisource's proofread pages and their scans, using Rivok's line-pairing method.

## How the pairs are made
- **Method:** Rivok's (RivoksLab/tesseract-heb-rivok, `training/v2/lines`, Apache-2.0); his aligner and label rules
  are ported with credit.
- **Line cutting:** Tesseract with Rivok's heb_rivok 2.0 model cuts each scanned page into lines. The OCR is used only
  for the line boxes and as an anchor.
- **Alignment:** the page's proofread Wikisource text is aligned word by word to the OCR (Needleman–Wunsch) and cut at
  the OCR's line breaks.
- **What is kept:** a line whose two ends are anchored, whose OCR-vs-label character error rate (without niqqud) is at
  most 0.25, and which passes the label rules. The rules drop lines whose transcription departs from the print:
  - expanded abbreviations;
  - editorial or partial niqqud;
  - plene spelling;
  - editors' notes;
  - cantillation;
  - missing printed digits;
  - wiki markup residue;
  - boxes holding two printed lines.
- **Label:** always the human-proofread text, never the OCR.

## Fields
`image` (PNG crop), `text` (label), `ocr_text`, `cer_nomarks`, `bbox`, `scan_file`, `scan_sha1`, `scan_url`,
`scan_page`, `image_sha256`, `wikisource_page`, `wikisource_page_id`, `wikisource_revid`, `wikisource_url`,
`quality` (3 proofread, 4 validated), `tags`, `image_licence_basis`, `image_licence`, `image_licence_page`,
`text_licence`.

## Evaluation hygiene
- **Exclusion:** HeOCR's exact evaluation test pages and development pages are excluded, page by page; no crop comes
  from them (checked by HeOCR's independent CLEAN). Other pages of the same books may be included.
- **Tags kept private:** which rows share a book with an evaluation set is kept in a private sidecar, so evaluations
  can report results both ways without naming the private sets here.

## Quality
- **Label noise:** a manual check of 120 random lines after the final rules found about 3% label defects. Most are
  text lost inside Wikisource templates (a citation or folio reference) or typos in Wikisource itself.
- **Fit:** treat the labels as high quality but not perfect.

## Licences and credit
- **Text:** Hebrew Wikisource contributors, CC BY-SA 4.0. Each line's `wikisource_url` points to the exact revision;
  its history lists the authors.
- **Images:** crops of scans that are in the public domain in Israel (`image_licence_basis = pd_il`). Each line links
  its scan's file description page.
- **Credit:** Rivok Labs (the line-pairing method and code), Hebrew Wikisource and its proofreaders, Wikimedia Commons
  and the scans' sources.
- **Dataset licence:** CC BY-SA 4.0.

Built by HeOCR (https://github.com/HeOCR). Code: https://github.com/HeOCR/htext (`htext.linepairs`).
"""


def write_card(out: Path, manifest: dict) -> None:
    text = CARD.format(version=manifest["version"], public=manifest["rows"]["public"], books=len(manifest["books"]["public"]))
    _atomic(out / "README.md", text.encode("utf-8"))


def main() -> int:
    import pyarrow as pa
    import pyarrow.parquet as pq

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pilot", type=Path, required=True)
    ap.add_argument("--pages", type=Path, required=True)
    ap.add_argument("--scan-ledger", type=Path, required=True)
    ap.add_argument("--licences", type=Path, required=True)
    ap.add_argument("--exclude", type=Path, action="append", default=[])
    ap.add_argument("--version", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--public-bases", nargs="*", default=list(PUBLIC_DEFAULT))
    ap.add_argument("--hold-index", action="append", default=[], help="an Index held from the public shards (rights question)")
    a = ap.parse_args()
    excluded = set()
    for p in a.exclude:
        excluded |= {r["wikisource_page"].split(":", 1)[-1] for r in json.loads(p.read_text(encoding="utf-8"))["pages"]}
    meta = {(p["index"], p["n"]): p for p in map(json.loads, a.pages.read_text(encoding="utf-8").splitlines())}
    scans = {r["index"]: r for r in map(json.loads, a.scan_ledger.read_text(encoding="utf-8").splitlines()) if r.get("ok")}
    lic = {r["index"]: r for r in json.loads(a.licences.read_text(encoding="utf-8"))}
    from htext.linepairs.wikisource import book_key
    index_of_book = {book_key(i): i for i in scans}
    rows: list[dict[str, Any]] = []
    for line in (a.pilot / "pages.jsonl").read_text(encoding="utf-8").splitlines():
        pg = json.loads(line)
        if not pg["kept"]:
            continue
        index = index_of_book[pg["book"]]
        title = f"{index}/{pg['n']}"
        if title in excluded:
            raise SystemExit(f"{title} is an excluded eval page and must not be packaged")
        receipt = json.loads((a.pilot / "receipts" / pg["book"] / f"p{pg['n']:04d}.json").read_text(encoding="utf-8"))
        m = meta[(index, pg["n"])]
        L = lic.get(index, {})
        basis = licence_basis(L)
        tags = list(pg["tags"]) + (["transclusion_resolved"] if m.get("transclusion_resolved") else [])
        for k in receipt["kept"]:
            crop = a.pilot / "lines" / pg["book"] / f"p{pg['n']:04d}" / f"p{pg['n']:04d}_l{k['line']:03d}.png"
            img = crop.read_bytes()
            rows.append({
                "id": f"{pg['book']}/p{pg['n']:04d}/l{k['line']:03d}",
                "image": {"bytes": img, "path": crop.name},
                "text": k["label"], "ocr_text": k["ocr"], "cer_nomarks": float(k["cer_nomarks"]), "bbox": list(map(int, k["bbox"])),
                "scan_file": index, "scan_sha1": scans[index]["sha1"], "scan_url": scans[index]["url"], "scan_page": pg["n"],
                "image_sha256": hashlib.sha256(img).hexdigest(),
                "wikisource_page": f"עמוד:{title}", "wikisource_page_id": m["page_id"], "wikisource_revid": m["rev"],
                "wikisource_url": f"https://he.wikisource.org/w/index.php?oldid={m['rev']}", "quality": m["quality"],
                "tags": tags, "image_licence_basis": basis, "image_licence": "; ".join(L.get("licence_short", [])),
                "image_licence_page": L.get("page_url"), "text_licence": "CC-BY-SA-4.0",
                "public": basis in a.public_bases and index not in a.hold_index,
            })
    rows.sort(key=lambda r: r["id"])
    counts: Counter = Counter()
    manifest: dict[str, Any] = {"version": a.version, "shards": {}, "rows": {}}
    for part in ("public", "internal"):
        sel = [r for r in rows if r["public"] == (part == "public")]
        manifest["rows"][part] = len(sel)
        for i in range(0, len(sel), SHARD_ROWS):
            chunk = sel[i:i + SHARD_ROWS]
            table = pa.Table.from_pylist([{k: v for k, v in r.items() if k != "public"} for r in chunk])
            buf = io.BytesIO()
            pq.write_table(table, buf, compression="zstd")
            name = f"{part}/train-{i // SHARD_ROWS:05d}.parquet"
            _atomic(a.out / name, buf.getvalue())
            manifest["shards"][name] = {"rows": len(chunk), "sha256": hashlib.sha256(buf.getvalue()).hexdigest()}
        for r in sel:
            counts[f"{part}:{r['image_licence_basis']}"] += 1
    manifest["by_licence_basis"] = dict(sorted(counts.items()))
    manifest["books"] = {part: sorted({r["scan_file"] for r in rows if r["public"] == (part == "public")}) for part in ("public", "internal")}
    _atomic(a.out / "manifest.json", (json.dumps(manifest, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    write_card(a.out, manifest)
    print(json.dumps({k: manifest[k] for k in ("rows", "by_licence_basis")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

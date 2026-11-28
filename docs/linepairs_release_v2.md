# hebrew-print-line-pairs v2: shared release layout (book-level parts)

v2 adds book-level pairs (an edition scan plus a whole-book transcription of the same edition) to the v1.1 Wikisource
pairs. Several builders produce **parts**: part 1 is heocr-ops #707 (htext), part 2 is #708 and #709 (opensrc). The
parts merge into **one** release with one card. Every part follows this layout so that the merge is mechanical.

## Part layout
```
v2/parts/<part_id>/            part_id: p1-ops707, p2-ops708-709, ...
  public/train-00000.parquet   rows that may be published (see Licences)
  internal/train-00000.parquet training-only rows (never published)
  private-tags.jsonl.gz        {"id", "tags"} for every row, eval-derived tags included (never published)
  manifest.json                {"part", "version": "v2", "rows": {"public", "internal"}, "shards": {path: {rows, sha256}},
                                "by_licence_basis", "builder": {"htext_commit", "driver"},
                                "inputs": {"manifest", "manifest_sha256"}, "report": <editions report.json>}
  qa/                          the visual QA sample: composites plus labels.tsv, with the defect count in qa/README.md
```
- **Shards:** rows sorted by `id`, at most 20,000 per shard, zstd, written atomically (temp file, fsync, rename).
- **Building:** with the editions driver (`htext.linepairs.editions`, HeOCR/htext#63) and its per-page receipts.

## Row schema (all parts, both shards)
| Field | Type | Notes |
|---|---|---|
| id | str | `<part_id>/<safe_id(pair id)>/p<page:04d>/l<line:03d>`, unique across parts |
| image | struct{bytes, path} | PNG crop (Rivok crop: box +6 px, +15% height) |
| text | str | label: the transcription cut at the OCR line; ׳׳ normalised to ״ |
| ocr_text, cer_nomarks, bbox | str, float, list[int] | line cutter output (heb_rivok 2.0) |
| source_id | str | pair id from the ops manifest |
| scan_url, scan_digest, scan_page | str, str, int | `scan_digest`: the pinned sha256 (else sha1); page = PDF ordinal or IA leaf |
| transcription_id, transcription_sha256 | str, str | e.g. `pby:6383`, `Sefaria:<title>|<versionTitle>` |
| image_sha256 | str | sha256 of the crop bytes |
| tags | list[str] | public rows: only `book_level`, `source:<pby|sefaria|wikisource>`, `columns_rtl2` |
| image_licence_basis | str | `pd_il`, `pd_us_only`, `cc0`, `cc_by`, `cc_by_sa`, `il_s6`, `unclear` |
| text_licence | str | the transcription's own licence: `PD`, `CC0`, `CC-BY`, `CC-BY-SA` |
| privacy_gate | str or null | gate id when the source needs one (Knesset plenary) |

## Licences (which rows are public)
- **Public:** the image basis is `pd_il`, `cc0`, `cc_by` or `cc_by_sa`, and the text licence is PD, CC0, CC-BY or CC-BY-SA.
  The release is CC BY-SA 4.0 overall (as v1/v1.1), which all of these are compatible with.
- **Internal:** everything else, including `pd_us_only`, `unclear` and §6 Knesset ≥1976 (train-only under the legal
  strategy). NC and ND are refused and never built.

## Evaluation hygiene
- **Page-only exclusion:** exact test pages (restricted-eval #1727 and later lists) and DEV pages are excluded by
  (scan identity, page). Nothing is excluded by book.
- **Private tags:** eval-derived tags go only to `private-tags.jsonl.gz`.
- **CLEAN:** each part gets its own CLEAN request (via lead to heocr-clean) on its manifest sha256. The merge needs every
  part signed.

## Merge (htext, one step)
1. Concatenate the public rows of all signed parts, and separately the internal rows.
2. Drop exact duplicates by `image_sha256` (first part wins, in part_id order) and log them.
3. Re-shard by `id`.
4. Write one manifest: the parts with their CLEAN records, totals and licence breakdown.
5. Write one card: per-part sections (sources, keep rates, QA defect rates) and the shared credit (Rivok Labs, Ben-Yehuda,
   Sefaria, Wikisource, IA/Commons and the scan holders).
6. Publish as HF tag `v2` and a new Zenodo version under concept 10.5281/zenodo.24571579, after lead's GO.

v1.1's Wikisource pairs are not repeated in v2's parts. The v2 card links v1.1, and a user who wants both loads both
tags.

## Niqqud in Ben-Yehuda labels (parts 1, 3, 4 and 4b)

Niqqud in these labels follows the Project Ben-Yehuda text; it has not been verified mark by mark against the printed scan.

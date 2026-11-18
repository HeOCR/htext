# Knesset laws (`knesset-laws`)

Enacted laws of the first eight Knessets, as published in Reshumot. Section 6 of the Israeli Copyright Act 2007
leaves laws unprotected, so the corpus goes to `htext-cc0` with the source licence
`Israel Copyright Act 2007 s.6 (not protected)`. This is source 2 of the
[sources plan](sources_plan.md).

This page covers the fetch step. The builder (`htext.knesset.laws`) follows in its own PR.

## What is fetched

| Step | Where | What |
| --- | --- | --- |
| Bills | Knesset OData `KNS_Bill` (`https://knesset.gov.il/Odata/ParliamentInfo.svc`, no key) | every bill of the chosen Knessets with a publication series (`PublicationSeriesID` not null): name, Knesset, publication date, series, booklet (`MagazineNumber`) and page |
| Documents | `KNS_DocumentBill`, group 9 only ("חוק - פרסום ברשומות", files `<k>_lsr_<n>`) | the law as published; first-reading bills (group 2, `_ls1_`) are out by plan decision 2 and never listed |
| Files | `fs.knesset.gov.il` | each group-9 DOC and PDF; TIF scans are not fetched |

- **DOC and PDF.** The PDFs are scans with an OCR text layer. Where the Knesset also gives a Word file, it holds the
  same OCR text in logical reading order, with margin notes as separate paragraphs. The builder reads the DOC where it
  exists and the PDF text otherwise, and marks both `text_quality: ocr_layer`. The PDF is kept for the eye check
  against the scan.
- **Booklets.** `MagazineNumber` of a Sefer HaChukim bill (series 6071) is its booklet number. Eval reserves booklets
  as `sefer_hachukim_<n>`, so the builder leaves out every law in a reserved booklet, whole.

## Running

```bash
python scripts/fetch_knesset_laws.py --knessets 1-8 \
  --inputs ../work/knesset-laws/inputs \
  --manifest data/knesset_laws/sources.v1.json
```

- The script refuses an `--inputs` directory inside a git work tree.
- `--catalogue-only` lists bills and files and downloads nothing.
- A rerun reuses files already on disk, hashes them again, and retries files that failed.

## Politeness

The fetcher sends one request at a time, at least one second apart (`--min-interval`, never less than 1), with the
generic client name `htext-fetch/0.1 (https://github.com/HeOCR/htext)`. Server errors and HTTP 429 are retried
three times with backoff; other errors are recorded in the manifest and are not retried. Every request goes to a
JSON-lines log (`<inputs>/fetch_log.jsonl` by default): time, URL, attempt, status, size and sha256.
`fs.knesset.gov.il` has no robots file, and no Knesset terms of use could be found (sources plan, sections 2-3).

## Manifest (`htext_knesset_laws_sources.v1`)

| Field | Contents |
| --- | --- |
| `source` | the OData root, the bill filter, the document group, formats, files host, client name, `fetched_at` |
| `knessets`, `counts` | the Knessets fetched; bills, files, files pinned or failed, and per Knesset the bills with a DOC, with a PDF, and with no file |
| `bills[]` | `bill_id`, `knesset`, `name`, `publication_date`, `publication_series_id`, `publication_series`, `magazine_number`, `page_number`, `odata_last_updated`, and `documents[]` |
| `documents[]` | `document_bill_id`, `format`, `url`, `file` (path under `--inputs`), `bytes`, `sha256`, `odata_last_updated`, and `error` when the download failed |
| `skipped_documents[]` | document rows not fetched, with a reason: `scan_only`, `format_not_fetched`, `unexpected_path`, or `not_group_9` if the service ever returns another group |

The manifest is the build's input list: the builder reads only files whose sha256 matches it.

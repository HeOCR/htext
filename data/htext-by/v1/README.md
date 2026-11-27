---
language:
- he
license: cc-by-4.0
tags:
- ocr
- hebrew
- htext
configs:
- config_name: default
  data_files:
  - split: train
    path: data/*.parquet
---

# htext-by: all CC BY 4.0 htext text releases in one dataset

1,409,213 Hebrew (and some Aramaic) text lines for OCR training: every published htext release under
CC BY 4.0, merged and de-duplicated. The per-source repositories stay as they are; this dataset is a convenience union.

## Columns

| Column | Meaning |
| --- | --- |
| `text` | the line |
| `variant` | `plain` or `niqqud` (pointed); for the Knesset plenary, `ocr` (the scans' text layer) or `transcription` |
| `lang` | `he`, or `arc` for Aramaic-heavy works (Talmud tractates, Targum, Zohar) |
| `source`, `source_release` | the component release the row was taken from |
| `sources` | every component release that has this exact line |
| `licence` | the source's own licence or rights basis for the line |
| `work_id`, `edition` | the work (and edition, where known) in the source's own ids |

Variants: niqqud 203,546, plain 1,205,667.

## Build

- Exact de-duplication on (`variant`, `text`) within this dataset. 1,409,213 input rows; 1,409,213 kept.
  The first row in the component order below is kept; the others are listed in `sources`. The Knesset plenary OCR and
  transcription lanes are separate variants, so a line in both is kept in both.
- Every component file was fetched from its pinned Hugging Face commit and checked against the SHA-256 on its htext
  card. Recipe: `recipe/` (fetch, build, stage); `build_manifest.json` lists every input file and hash.

## Components

| Release | Hugging Face | DOI | Rows kept here | CLEAN record (HeOCR, private) |
| --- | --- | --- | ---: | --- |
| `sefaria-v3-by` | [HeOCR/htext-sefaria-by@c55b5dcb](https://huggingface.co/datasets/HeOCR/htext-sefaria-by/tree/c55b5dcbc79b360b87031a1fa7aca029b62d25f0) | 10.5281/zenodo.24581347 | 1,376,917 | #1873 |
| `sefaria-v2-by` | [HeOCR/htext-sefaria-by@e28fae17](https://huggingface.co/datasets/HeOCR/htext-sefaria-by/tree/e28fae17d635f72ad6c9a628734252c1ea219e24) | 10.5281/zenodo.24521430 | 32,296 | #857 |

## Evaluation hygiene

No new CLEAN check was needed: every component is an already published release that passed HeOCR's independent
CLEAN check (records above), and this dataset as a whole passed a work-level screen against HeOCR's current
evaluation reservations (v14; record #1893). Lines that share text with material HeOCR uses for evaluation are tagged in private
sidecars of those checks, not dropped (contamination policy v2, amendment 1), and HeOCR evaluations report results
both with and without them. Works that an evaluation set holds out whole are not in any component.

## Rights and credit

Released under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). See NOTICE.md for the credit of every source.

Built by HeOCR (https://github.com/HeOCR) with htext (https://github.com/HeOCR/htext).

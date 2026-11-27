---
language:
- he
license: cc-by-sa-4.0
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

# htext-by-sa: all CC BY-SA 4.0 htext text releases in one dataset

4,462,291 Hebrew (and some Aramaic) text lines for OCR training: every published htext release under
CC BY-SA 4.0, merged and de-duplicated. The per-source repositories stay as they are; this dataset is a convenience union.

**v2** adds wikisource-v5 (3,703,412 lines from 130 public-domain works; CLEAN record #1896). About 39% of wikisource-v5's
content also appears in Sefaria with different line breaks or edition wording (census estimate); exact duplicates are removed, near
duplicates are kept on purpose.

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

Variants: niqqud 491,159, plain 3,971,132.

## Build

- Exact de-duplication on (`variant`, `text`) within this dataset. 4,463,188 input rows; 4,462,291 kept.
  The first row in the component order below is kept; the others are listed in `sources`. The Knesset plenary OCR and
  transcription lanes are separate variants, so a line in both is kept in both.
- Every component file was fetched from its pinned Hugging Face commit and checked against the SHA-256 on its htext
  card. Recipe: `recipe/` (fetch, build, stage); `build_manifest.json` lists every input file and hash.

## Components

| Release | Hugging Face | DOI | Rows kept here | CLEAN record (HeOCR, private) |
| --- | --- | --- | ---: | --- |
| `wikisource-v5` | [HeOCR/htext-wikisource@ea93b039](https://huggingface.co/datasets/HeOCR/htext-wikisource/tree/ea93b039a4d57234466d4c649ff83311069394a4) | 10.5281/zenodo.24584329 | 3,703,412 | #1896 |
| `wikisource-v4` | [HeOCR/htext-wikisource@a5ee2ac1](https://huggingface.co/datasets/HeOCR/htext-wikisource/tree/a5ee2ac15051447d571e027c87c9512317cce919) | 10.5281/zenodo.24580528 | 4,088 | #1714 |
| `wikisource-v3` | [HeOCR/htext-wikisource@b7766502](https://huggingface.co/datasets/HeOCR/htext-wikisource/tree/b7766502d9d297176925da620b01e357ad0f4ec6) | 10.5281/zenodo.24521419 | 79,429 | #857 |
| `wikisource-v2` | [HeOCR/htext-wikisource@efcf3e55](https://huggingface.co/datasets/HeOCR/htext-wikisource/tree/efcf3e55bedd7a17e6eef7db02afd4c5f6447144) | 10.5281/zenodo.24516892 | 12,953 | #785, #240 |
| `wikisource-v1` | [HeOCR/htext-wikisource@c2f4310c](https://huggingface.co/datasets/HeOCR/htext-wikisource/tree/c2f4310c16d194224458fc9efb17cf9342c875ed) | — | 72,219 | #785, #240 |
| `sefaria-v3-by-sa` | [HeOCR/htext-sefaria-by-sa@1d24204f](https://huggingface.co/datasets/HeOCR/htext-sefaria-by-sa/tree/1d24204f8bd53d3abc214619a2b73cd731552b5e) | 10.5281/zenodo.24581351 | 590,190 | #1873 |

## Evaluation hygiene

No new CLEAN check was needed: every component is an already published release that passed HeOCR's independent
CLEAN check (records above), and this dataset as a whole passed a work-level screen against HeOCR's current
evaluation reservations (v14; record #1893). Lines that share text with material HeOCR uses for evaluation are tagged in private
sidecars of those checks, not dropped (contamination policy v2, amendment 1), and HeOCR evaluations report results
both with and without them. Works that an evaluation set holds out whole are not in any component.

## Rights and credit

Released under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). See NOTICE.md for the credit of every source.

Built by HeOCR (https://github.com/HeOCR) with htext (https://github.com/HeOCR/htext).

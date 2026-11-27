---
language:
- he
license: cc0-1.0
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

# htext-cc0: all CC0 1.0 htext text releases in one dataset

74,347,024 Hebrew (and some Aramaic) text lines for OCR training: every published htext release under
CC0 1.0, merged and de-duplicated. The per-source repositories stay as they are; this dataset is a convenience union.

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

Variants: niqqud 2,787,245, ocr 10,521,382, plain 40,241,565, transcription 20,796,832.

## Build

- Exact de-duplication on (`variant`, `text`) within this dataset. 90,431,834 input rows; 74,347,024 kept.
  The first row in the component order below is kept; the others are listed in `sources`. The Knesset plenary OCR and
  transcription lanes are separate variants, so a line in both is kept in both.
- Every component file was fetched from its pinned Hugging Face commit and checked against the SHA-256 on its htext
  card. Recipe: `recipe/` (fetch, build, stage); `build_manifest.json` lists every input file and hash.

## Components

| Release | Hugging Face | DOI | Rows kept here | CLEAN record (HeOCR, private) |
| --- | --- | --- | ---: | --- |
| `tanakh-v1.1` | [HeOCR/htext-tanakh@082a6bc4](https://huggingface.co/datasets/HeOCR/htext-tanakh/tree/082a6bc4640922cce77d640aaa4613b43a76e664) | 10.5281/zenodo.24398530 | 115,320 | #164 |
| `sefaria-v3.1-cc0` | [HeOCR/htext-sefaria@afcf93c2](https://huggingface.co/datasets/HeOCR/htext-sefaria/tree/afcf93c24cda1ccbc80f3fe8fa49599b0ea5708b) | 10.5281/zenodo.24583313 | 28,994,342 | #1873, #1893 |
| `sefaria-v2-cc0` | [HeOCR/htext-sefaria@a92766c9](https://huggingface.co/datasets/HeOCR/htext-sefaria/tree/a92766c9fb4955b1f9fcb3766430cd5522af7614) | 10.5281/zenodo.24521423 | 58,093 | #857 |
| `sefaria-v1` | [HeOCR/htext-sefaria@2572e399](https://huggingface.co/datasets/HeOCR/htext-sefaria/tree/2572e399c910cbfe6410830cc93360b192c14728) | 10.5281/zenodo.24516961 | 6,328 | #785 |
| `pby-v3.1` | [HeOCR/htext-pby@e9743322](https://huggingface.co/datasets/HeOCR/htext-pby/tree/e9743322cffe783f7bad4e65236256baf111b990) | 10.5281/zenodo.24398596 | 13,528,270 | #164 |
| `pby-v2.1` | [HeOCR/htext-pby@2768cf84](https://huggingface.co/datasets/HeOCR/htext-pby/tree/2768cf84240a4b9677924f42d6c21da68ebc1c43) | — | 0 | #164 |
| `pby-v1.1` | [HeOCR/htext-pby@6ec05e10](https://huggingface.co/datasets/HeOCR/htext-pby/tree/6ec05e10a8d3d2a49bf20680a7cc665c6d57170c) | — | 98,878 | #164 |
| `tsel-haolam-v1` | [HeOCR/htext-tsel-haolam@c95c9a34](https://huggingface.co/datasets/HeOCR/htext-tsel-haolam/tree/c95c9a349a1f9a9d1972489c1b1d25b23fc24dbb) | 10.5281/zenodo.24521432 | 2,383 | #857 |
| `gutenberg-v1` | [HeOCR/htext-gutenberg@1f7432ee](https://huggingface.co/datasets/HeOCR/htext-gutenberg/tree/1f7432ee0240c0a23b44347cb1612c454fe78eed) | 10.5281/zenodo.24581353 | 5,292 | #1873 |
| `knesset-laws-v2` | [HeOCR/htext-knesset-laws@07019274](https://huggingface.co/datasets/HeOCR/htext-knesset-laws/tree/0701927460813ee6935c0e5811a65b731c3b248d) | 10.5281/zenodo.24384730 | 219,904 | #150 |
| `knesset-plenary-v1` | [HeOCR/htext-knesset-plenary@daf44afc](https://huggingface.co/datasets/HeOCR/htext-knesset-plenary/tree/daf44afc2737942acd57f77ea3299a6bc1b5e2e1) | — | 31,318,214 | #213 |

## Evaluation hygiene

No new CLEAN check was needed: every component is an already published release that passed HeOCR's independent
CLEAN check (records above), and this dataset as a whole passed a work-level screen against HeOCR's current
evaluation reservations (v14; record #1893). Lines that share text with material HeOCR uses for evaluation are tagged in private
sidecars of those checks, not dropped (contamination policy v2, amendment 1), and HeOCR evaluations report results
both with and without them. Works that an evaluation set holds out whole are not in any component.

## Rights and credit

Released under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). See NOTICE.md for the credit of every source.

Built by HeOCR (https://github.com/HeOCR) with htext (https://github.com/HeOCR/htext).

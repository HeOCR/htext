---
language:
- he
license: cc0-1.0
tags:
- ocr
- hebrew
- htext
---

# htext Gutenberg v1: public-domain Hebrew training lines

Hebrew text lines for OCR training from two public-domain Project Gutenberg ebooks (PG 43740, Bet Nekhot ha-Halakhot, responsa of the Geonim; PG 45252, Isaac Erter's Ha-Tsofeh le-Veit Yisrael), 5,316 lines. Only the text between Project Gutenberg's start and end markers is used, and the producers' electronic-edition notes are left out.

## Files

| Text file | Lines |
| --- | ---: |
| `gutenberg_lines_plain_v1.txt` | 5,315 |
| `gutenberg_lines_niqqud_v1.txt` | 1 |

`*_arc` files hold Aramaic-heavy works (Talmud tractates, Targum, Zohar); leave them out for a Hebrew-only fit.
The line index binds every line to its work, edition and segment; the rights index gives each edition's licence,
credit and source URL. SHA256SUMS covers the package files. CORPUS_CARD.md and corpus_card.json describe the build.

## Evaluation hygiene

HeOCR's independent CLEAN check (2026-11-27) kept every line. 19,073 lines of the Sefaria v3 and Gutenberg tranche share text with material HeOCR uses for evaluation; they are tagged in a private sidecar, not dropped (contamination policy v2, amendment 1), and HeOCR evaluations report results both with and without them. Works that an evaluation set holds out whole are not in this release.

## Rights and credit

Released under [CC0 1.0 / public domain](https://creativecommons.org/publicdomain/zero/1.0/). Transcriptions by Project Gutenberg volunteers (https://www.gutenberg.org); the works are in the public domain.

Built by HeOCR (https://github.com/HeOCR) with htext (https://github.com/HeOCR/htext).

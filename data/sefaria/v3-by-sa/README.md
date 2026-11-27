---
language:
- he
license: cc-by-sa-4.0
tags:
- ocr
- hebrew
- htext
---

# htext Sefaria v3 (by-sa): CC BY-SA Hebrew training lines

Hebrew and Aramaic text lines for OCR training from 84 CC BY-SA editions in Sefaria (591,087 lines), cut to printed-line lengths and de-duplicated against other htext releases. Each edition keeps its own credit; share-alike applies.

## Files

| Text file | Lines |
| --- | ---: |
| `sefaria_by-sa_lines_plain_he_v3.txt` | 210,770 |
| `sefaria_by-sa_lines_plain_arc_v3.txt` | 343,511 |
| `sefaria_by-sa_lines_niqqud_he_v3.txt` | 36,804 |
| `sefaria_by-sa_lines_niqqud_arc_v3.txt` | 2 |

`*_arc` files hold Aramaic-heavy works (Talmud tractates, Targum, Zohar); leave them out for a Hebrew-only fit.
The line index binds every line to its work, edition and segment; the rights index gives each edition's licence,
credit and source URL. SHA256SUMS covers the package files. CORPUS_CARD.md and corpus_card.json describe the build.

## Evaluation hygiene

HeOCR's independent CLEAN check (2026-11-27) kept every line. 19,073 lines of the Sefaria v3 and Gutenberg tranche share text with material HeOCR uses for evaluation; they are tagged in a private sidecar, not dropped (contamination policy v2, amendment 1), and HeOCR evaluations report results both with and without them. Works that an evaluation set holds out whole are not in this release.

## Rights and credit

Released under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Text from Sefaria (https://www.sefaria.org) and the editions it credits. Each edition is CC BY-SA; credit it as listed in NOTICE.md and share alike.

Built by HeOCR (https://github.com/HeOCR) with htext (https://github.com/HeOCR/htext).

---
language:
- he
license: cc0-1.0
tags:
- ocr
- hebrew
- htext
---

# htext Sefaria v3.1 (cc0): public-domain and CC0 Hebrew training lines

Hebrew and Aramaic text lines for OCR training from 4,695 public-domain and CC0 editions in Sefaria (28,994,342 lines), cut to printed-line lengths. HeOCR normalized, segmented, filtered and de-duplicated the text, and removed lines already in other htext releases. **v3.1 supersedes sefaria-v3-cc0**, which is withdrawn: a work held out for evaluation (Arukh HaShulchan, Choshen Mishpat, Vilna 1923-29) and the footnotes printed with another held-out work were found in it and are removed here (144,843 lines). v3.1 is otherwise a subset of v3.

## Files

| Text file | Lines |
| --- | ---: |
| `sefaria_cc0_lines_plain_he_v3.txt` | 28,003,015 |
| `sefaria_cc0_lines_plain_arc_v3.txt` | 27,131 |
| `sefaria_cc0_lines_niqqud_he_v3.txt` | 922,973 |
| `sefaria_cc0_lines_niqqud_arc_v3.txt` | 41,223 |

`*_arc` files hold Aramaic-heavy works (Talmud tractates, Targum, Zohar); leave them out for a Hebrew-only fit.
The line index binds every line to its work, edition and segment; the rights index gives each edition's licence,
credit and source URL. SHA256SUMS covers the package files. CORPUS_CARD.md and corpus_card.json describe the build.

## Evaluation hygiene

HeOCR's independent CLEAN check (2026-11-27) kept every line. 19,073 lines of the Sefaria v3 and Gutenberg tranche share text with material HeOCR uses for evaluation; they are tagged in a private sidecar, not dropped (contamination policy v2, amendment 1), and HeOCR evaluations report results both with and without them. Works that an evaluation set holds out whole are not in this release. Works held out whole by an evaluation set are dropped from every lane, matched by title, by the part named in the edition, and by notes printed with them (HeOCR work-level screen against reservations v14, record #1893).

## Rights and credit

Released under [CC0 1.0 / public domain](https://creativecommons.org/publicdomain/zero/1.0/). Text from Sefaria (https://www.sefaria.org) and the editions it credits.

Built by HeOCR (https://github.com/HeOCR) with htext (https://github.com/HeOCR/htext).

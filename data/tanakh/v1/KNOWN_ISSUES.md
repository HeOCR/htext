# Known issues in `tanakh-v1`

The `v1` files are frozen as published: their sha256s in
[`SHA256SUMS`](SHA256SUMS) still check. Issues found later are listed here
and fixed in later builds.

## Verse ranges now reserved by HeOCR's evaluation (fixed in later builds)

`v1` was built with `eval_reservations_v3.json` (sha256 `969618a8…`), which
reserved no biblical text. HeOCR's evaluation then reserved four verse ranges
for its pointed-print test set (`niqqud_print_v1`), in
`eval_reservations_v5.json` (sha256 `8a869b0f…`):

| Range | Why | Verses in `v1` | Lines per file |
| --- | --- | ---: | ---: |
| Nehemiah 3:1–15 | test text | 15 of 15 | 51 |
| Ezekiel 40:5–19 | test text | 14 of 15 | 45 |
| Ezra 2:1–28 | test text | 28 of 28 | 39 |
| Nehemiah 7:6–32 | the near-verbatim parallel of Ezra 2 | 23 of 27 | 30 |
| **Total** | | **80** | **165** |

Each file, `tanakh_lines_niqqud_v1.txt` and `tanakh_lines_plain_v1.txt`, has
165 lines from these ranges. The other five verses (Ezekiel 40:11 and
Nehemiah 7:9, 12, 14, 27) have no lines in `v1`. The likely reason is the
build's duplicate drop; in Nehemiah 7 these verses repeat Ezra 2.

A model trained on these lines has seen text that HeOCR uses to evaluate
modern pointed print, so its scores on that set are not clean. Later tanakh
builds leave these ranges out. To filter `v1`, use `tanakh_line_index.v1.jsonl.gz`
(one row per line, in file order, with its `ref` as `Book.chapter.verse`) to
drop every line whose `ref` falls in a range above.

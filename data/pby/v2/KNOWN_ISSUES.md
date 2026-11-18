# Known issues in `pby-v2`

The `v2` files are frozen as published: their sha256s in
[`SHA256SUMS`](SHA256SUMS) still check. Issues found later are listed here
and fixed in later builds.

## Works now held out by HeOCR's evaluation (fixed in `v3`)

`v2` was built with `eval_reservations_v2.json` (sha256 `2abce5ea…`). Since
then, HeOCR's evaluation has reserved the P-hist eval hold-out v1 and its
top-up, in `eval_reservations_v4.json` (sha256 `c8842a90…`). Fifteen
works with lines in `v2` are in those hold-outs:

| Set | Works | `v2` lines |
| --- | ---: | ---: |
| P-hist eval hold-out v1 | 9 | 16,729 |
| P-hist eval hold-out v1 top-up | 6 | 23,506 |
| **Total** | **15** | **40,235** |

By file, that is 40,205 lines of `pby_lines_il_plain_v2.txt` and 30 lines of
`pby_lines_il_niqqud_v2.txt`. No line in either `il_us` file comes from these
works.

A model trained on these lines has seen text that HeOCR uses to evaluate old
printed Hebrew (P-hist), so its P-hist scores are not clean. Use `v3`, which leaves these works out
whole. To filter `v2` instead, use `pby_line_index.v1.jsonl.gz` (one row per line,
with its `pby_work_id`) to keep only the lines of works listed in
[`data/pby/v3/pby_excluded_works.v1.json`](../v3/pby_excluded_works.v1.json).
The two builds list the same works, except these 15.

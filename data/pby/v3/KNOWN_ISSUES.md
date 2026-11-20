# Known issues in `pby-v3`

The `v3` files are frozen as published: their sha256s in
[`SHA256SUMS`](SHA256SUMS) still check. Issues found later are listed here
and fixed in later builds.

## Works now reserved by HeOCR's evaluation

`v3` was built with `eval_reservations_v4.json` (sha256 `c8842a90…`). HeOCR's
evaluation then chose its pointed-print test set (`niqqud_print_v1`) and
reserved its works, in `eval_reservations_v7.json` (sha256
`91fd1ea5099d9b1cc3cd5cbaf22ab93158c8357dda03d266e17b1ef44c3caf34`). Thirteen
works with lines in `v3` are now reserved: twelve prose works of the test set,
and PBY 1733, another PBY edition of a reserved book.

| PBY work | `il_plain` lines | `il_us_plain` lines |
| ---: | ---: | ---: |
| 1733 | 6,196 | 0 |
| 2631 | 136 | 0 |
| 2670 | 123 | 0 |
| 4642 | 53 | 53 |
| 5370 | 237 | 0 |
| 16428 | 139 | 0 |
| 17349 | 80 | 0 |
| 21962 | 73 | 0 |
| 31790 | 252 | 0 |
| 37918 | 84 | 0 |
| 38447 | 197 | 0 |
| 41638 | 47 | 0 |
| 47645 | 117 | 0 |
| **Total** | **7,734** | **53** |

These are lines of `pby_lines_il_plain_v3.txt` and
`pby_lines_il_us_plain_v3.txt`. No line in either `niqqud` file comes from these
works.

A model trained on these lines has seen text that HeOCR uses to evaluate
pointed print, so its scores on that set are not clean. The
[Hugging Face](https://huggingface.co/datasets/HeOCR/htext-pby/tree/pby-v3) and
[Zenodo](https://doi.org/10.5281/zenodo.24384745) copies of `pby-v3` already
leave these works out; the next GitHub build will too. Those copies were also
filtered against HeOCR's evaluation text, but a corrected check (2026-11-20)
found that some overlap remains in them. A decontaminated version is coming. To filter these `v3` files
yourself, use `pby_line_index.v1.jsonl.gz` (one row per line, with its
`pby_work_id`) to drop the lines of the works above.

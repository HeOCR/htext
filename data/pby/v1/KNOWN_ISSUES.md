# Known issues in `pby-v1`

**Withdrawn 2026-11-20.** This release's files were removed from GitHub, and
its filtered copies on Hugging Face and Zenodo were taken down: a corrected check
by HeOCR's evaluation found overlap with its evaluation text (see the
[README](../../../README.md#downloads)). The files here stay as the record of what
was published. HeOCR keeps a private, checksum-verified backup. Decontaminated
versions will follow.

The `v1` files are frozen as published: their sha256s in
[`SHA256SUMS`](SHA256SUMS) still check. Issues found later are listed here
and fixed in later builds.

## Verse-break marks (fixed in `v2`)

Project Ben-Yehuda writes a verse break inside a running line as a lone `/`.
Print never shows this mark, but the `v1` builder kept it as text.

| File | Lines with ` / ` | Lines |
| --- | ---: | ---: |
| `pby_lines_il_plain_v1.txt` | 1,943 | 1,627,470 |
| `pby_lines_il_niqqud_v1.txt` | 43,176 | 401,492 |
| `pby_lines_il_us_plain_v1.txt` | 56 | 70,251 |
| `pby_lines_il_us_niqqud_v1.txt` | 3 | 10,050 |

A model trained on these lines may learn to output `/` where a printed page
has a line break or a wide space. To use `v1` anyway, split each line at a
lone `/` or `//` and drop the mark, as the `v2` builder does
(`source_lines_split:verse_break_mark`). Better, use `v2`.

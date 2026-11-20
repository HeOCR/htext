# Known issues in `knesset-laws-v1`

**Withdrawn 2026-11-20.** The corpus file and the line index were removed from the
[`knesset-laws-v1` release](https://github.com/HeOCR/htext/releases/tag/knesset-laws-v1)
because of the overlap below. HeOCR keeps a private backup, verified against
[`SHA256SUMS`](SHA256SUMS). Use
[`knesset-laws-v2`](https://github.com/HeOCR/htext/releases/tag/knesset-laws-v2).

The `v1` files are frozen as published: their sha256s in
[`SHA256SUMS`](SHA256SUMS) still check. Issues found later are listed here
and fixed in later builds.

## Lines that overlap HeOCR's evaluation text (fixed in `v2`)

`v1` left out every law from a Reshumot booklet that HeOCR's evaluation
reserves. Some evaluation sets, though, are reserved by page, not by booklet,
and `v1` did not check its lines against their text. HeOCR's official overlap
check (shared 6-word sequences against the evaluation targets), run on
2026-11-20 on `knesset_laws_lines_plain_v1.txt` (sha256 `67c7a86b…`), found:

- more than a thousand lines that share at least one 6-word sequence with
  evaluation text. Most of these are short legal formulas;
- several dozen lines that repeat a whole printed line of an evaluation page,
  mostly the mid-century test pages, which are scans of laws this corpus also
  holds.

A model trained on `v1` has seen text that HeOCR uses for evaluation, so its
scores on those sets are not clean. [`knesset-laws-v2`](https://github.com/HeOCR/htext/releases/tag/knesset-laws-v2)
drops every line with any overlap and every law with a long overlap; the
same check found 0 overlap in it. `v2` is now the default. Do not train on
`v1` if you score on HeOCR's evaluation sets.

# Hebrew Wikisource proofread text

`htext wikisource build` prepares the `wikisource` corpus for `htext-by-sa`.
The registry entry describes an unreleased corpus. The build writes files to a
new local directory, and publication requires a separate release decision.

The source is Wikimedia's [2026-11-01 Hebrew Wikisource dump][dump], the single
`hewikisource-20261101-pages-articles.xml.bz2` file (469,082,606 bytes).
The build verifies its compressed SHA-256,
`15a731d70154941afec2a616d538434573a4e068f94c8ea91b659ac64b833fe1`, before
opening it. Wikimedia's [dump status][status] gives SHA-1
`82f0704066e81d69ff9ee53be3a2f00de8d1bdb5`. The builder works offline.

```sh
python -m pip install -e '.[fit]'
htext wikisource build \
  --dump /local/hewikisource-20261101-pages-articles.xml.bz2 \
  --reserved /local/eval_reservations_v7.json \
  --eval-overlap-drop /local/wikisource_eval_overlap_drop.json \
  --output /local/wikisource-v1
```

By default, the build uses the hocrsyngen S10b training length profile and
no-loss wrap check. `--length-profile` accepts a local file with one sample
line per row. `--no-fit-check` skips wrapping and is recorded in the card.

## What enters the corpus

- Page namespace revisions with ProofreadPage quality 3 (proofread) or 4
  (validated). An article can identify which work a scan belongs to. The
  emitted lines and attribution come from individual Page revisions.
- A Page must explicitly mark its underlying work with a recognized public
  domain or compatible free licence template or category, or a qualifying
  author death year in a recognized rights template. A plain assertion in
  prose, a scan or image licence, or an unspecified licence does not qualify.
  The builder records the exact marking used. It does not infer rights from a
  neighbouring Page or expand a template to resolve licensing claims.
- ProofreadPage headers and footers, templates, references, navigation, tables,
  and other non-body markup are omitted. Transclusions are never expanded.
  The shared htext segmenter cuts at words using the target lengths. The PBY
  niqqud threshold (0.5 by default) sends a line to the niqqud file when it
  has enough points, otherwise the plain file receives the stripped form.

## Evaluation exclusions

Both evaluation inputs are required. `--reserved` loads the HeOCR reservation
manifest with `htext.reservations`, including its v7 Wikisource units.
The XML metadata pass maps an Index ID to its scan name and the paired
`Page:<scan>/<number>` titles in the ProofreadPage pagelist. It also collects
article `<pages index=…>` and direct Page transclusion targets. This ties
reserved scans to the main work and its subpages, including other scan volumes
referenced within that work. The XML reader skips excluded Page payloads
before handing text to the wikitext parser. Index revisions do not contribute
text and their bodies are skipped. An unresolved reserved Index ID stops the
build so a wrong snapshot cannot silently turn off the reservation.
The scan-title mapping covers PDF and DjVu Indexes. A reservation on a different
kind of Index stops the build so its explicit Page list can be mapped by eval.

`--eval-overlap-drop` accepts `htext_eval_overlap_drop.v1` with
`"corpus": "wikisource"`, `line_sha256`, and `units`. Units can be Index IDs
(`ws_index_123`), page IDs (`ws_page_456` or `456`), or dump titles. The latter
use the dump's namespace spelling when present. Whole units are excluded
before corpus parsing. Line hashes are compared in pointed and plain forms,
and the repository's standard leakage fixtures also run. The card reports
counts without the overlap IDs or line hashes. Other editions of the same
work are outside the title mapping in v1. Before any release, the official
HeOCR eval check must find zero remaining overlaps.

## Outputs and credit

The builder produces plain and niqqud UTF-8 text files, `corpus_card.json`,
`CORPUS_CARD.md`, `SHA256SUMS`, `NOTICE.md`, and
`wikisource_rights_index.v1.jsonl.gz`. Each index row credits **Hebrew Wikisource
contributors** and gives the page title, permanent revision URL, page history,
quality level and rights basis. Its `line_ranges` locate each page's lines by
file, with 1-based `first_line` and a `lines` count. The output is adapted text
under [CC BY-SA 4.0][licence]. Redistributors must keep attribution and indicate
changes, following [Wikimedia's terms][terms]. Character counts are Unicode
code points, including niqqud and spaces and excluding trailing newlines.

[dump]: https://dumps.wikimedia.org/hewikisource/20261101/
[status]: https://dumps.wikimedia.org/hewikisource/20261101/dumpstatus.json
[licence]: https://creativecommons.org/licenses/by-sa/4.0/
[terms]: https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use#7._Licensing_of_Content

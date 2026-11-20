# Hebrew Wikisource proofread text

**Status: parked (heocr-lead, 2026-11-20).** A measuring build of the pinned dump gave no lines. Most proofread Pages
are eval-reserved, and none of the rest carries an explicit rights marking on the Page. The next design, for
main-namespace works, is in [`wikisource_main_namespace_design.md`](wikisource_main_namespace_design.md). Nothing has
been published.

`htext wikisource build` prepares the `wikisource` corpus for `htext-by-sa`.
The build writes files to a new local directory; publication is a separate
release PR. The pinned dump is recorded in
[`data/wikisource/sources.v1.json`](../data/wikisource/sources.v1.json).

The source is Wikimedia's [2026-11-01 Hebrew Wikisource dump][dump], the single
`hewikisource-20261101-pages-articles.xml.bz2` file (469,082,606 bytes).
The build verifies its compressed SHA-256,
`15a731d70154941afec2a616d538434573a4e068f94c8ea91b659ac64b833fe1`, before
opening it. Wikimedia's [dump status][status] gives SHA-1
`82f0704066e81d69ff9ee53be3a2f00de8d1bdb5`. The builder works offline.

```sh
python -m pip install -e '.[fit,wikisource]'
htext wikisource build \
  --dump /local/hewikisource-20261101-pages-articles.xml.bz2 \
  --reserved /local/eval_reservations_v7.json \
  --eval-overlap-drop /local/wikisource_eval_overlap_drop.json \
  --output /local/wikisource-v1
```

By default, the build uses the hocrsyngen S10b training length profile and
no-loss wrap check. `--length-profile` accepts a local file with one sample
line per row. `--no-fit-check` skips wrapping and is recorded in the card.

## Main-namespace build (option B)

Add these arguments to the same command to build unproofread article
transcriptions for `htext-by-sa`:

```sh
--works data/wikisource/works.v1.json \
  --law-sources data/wikisource/law_sources.v1.json \
  --knesset-laws-v2 /local/knesset_laws_lines_plain_v2.txt
```

The builder admits reviewed root titles and their slash subpages. It checks
the dump's reservation graph before parsing article text. If a reserved scan
links to a reviewed work through the graph, that work is excluded whole.
Namespace 106, redirects, OCR conversions and automatically converted
articles are excluded.

Open Law Book entries are pinned to an article ID and a revision ID. Each
entry lists the Reshumot series and booklet numbers for the enactment and
all amendments represented in that revision. Leave articles with incomplete
provenance out of the list. If any listed booklet is reserved, the builder
skips the whole article. For admitted entries, it takes statutory clause text
and omits publication notes and signatures. It compares candidate output lines
with the published knesset-laws-v2 text after stripping Hebrew marks, using
the release file's pinned SHA-256. The older ProofreadPage mode below is used
when the article arguments are absent.

The rights index credits the source article revision and records the reviewed
work or the law's booklet provenance. Before releasing article text, check 100
sampled lines against the source editions and run the official evaluation
overlap check on the exact output files. Rebuild with the resulting drop list
if it finds any overlap.

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
HeOCR eval check must find zero remaining overlaps. The drop list is made from
a build's own lines, so the first build takes an empty one
(`"line_sha256": [], "units": []`); the release build takes the real list.

## Outputs and credit

The builder produces plain and niqqud UTF-8 text files, `corpus_card.json`,
`CORPUS_CARD.md`, `SHA256SUMS`, `NOTICE.md`,
`wikisource_rights_index.v1.jsonl.gz` and `wikisource_line_index.v1.jsonl.gz`
(one row per line, in file order: its file, page unit `ws_page_<id>`, scan and
sha256). Exact duplicate lines are dropped across the corpus. Each index row credits **Hebrew Wikisource
contributors** and gives the page title, permanent revision URL, page history,
quality level and rights basis, with `pd_israel` (from the Page's explicit
marking), `pd_us` (not assessed) and `as_of`. Its `line_ranges` locate each page's lines by
file, with 1-based `first_line` and a `lines` count. The output is adapted text
under [CC BY-SA 4.0][licence]. Redistributors must keep attribution and indicate
changes, following [Wikimedia's terms][terms]. Character counts are Unicode
code points, including niqqud and spaces and excluding trailing newlines.

[dump]: https://dumps.wikimedia.org/hewikisource/20261101/
[status]: https://dumps.wikimedia.org/hewikisource/20261101/dumpstatus.json
[licence]: https://creativecommons.org/licenses/by-sa/4.0/
[terms]: https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use#7._Licensing_of_Content

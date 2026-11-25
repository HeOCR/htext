# Project Gutenberg Hebrew texts (`gutenberg`)

Project Gutenberg's Hebrew-language texts that are public domain in Israel, in `htext-cc0`. The source tag is
`gutenberg`, so the lines stay separable inside a release tranche.

## Sources

[`data/gutenberg/sources.v1.json`](../data/gutenberg/sources.v1.json) pins the following:

- the catalogue, `pg_catalog.csv.gz` (sha256 and row count), fetched from PG's own mirror `gutenberg.pglaf.org`;
- every Hebrew-language catalogue row: its PG number, title and contributors with death years, plus, for a work that
  enters, the mirror URL and the sha256 of the fetched plain-text file.

The fetch used the mirror only (its robots.txt returns 404, so nothing is restricted), one request at a time, a few
seconds apart, with a generic client name. No gutenberg.org pages were scraped.

A work enters only when **every contributor** (author, translator, compiler, editor) died at least 71 years before the
build year: the PBY rule for Israel. PG's US public-domain status is recorded too. A work with an unknown death year is
left out, and the card lists it with its reason. In the 2026-11-25 catalogue (79,769 rows, 7 Hebrew-language), the
results are:

| PG | Work | |
| ---: | --- | --- |
| 43740 | Horowitz (d. 1905), בית נכות ההלכות | in |
| 45252 | Erter (d. 1851), הצופה לבית ישראל | in |
| 5139, 18291 | translations whose translators' death years are unknown | out |
| 4778 | a living author | out |
| 20676 | audio only | out |
| 61024 | already released as `tsel-haolam-v1` | out |

## Build

```bash
htext gutenberg build --inputs <dir with pg<N>.txt> --output out/gutenberg-v1 \
  --reserved <eval_reservations_v13.json> [--dedup-against <other corpus lines file> ...]
```

- **Boilerplate:** only the text between PG's `*** START OF` and `*** END OF` markers is read, so the PG licence text
  never reaches the corpus. PG is credited on the card.
- **Dropped:** footnote blocks, emphasis markup, footnote marks and blocks with no Hebrew (title-page imprints).
- **Headings:** centred lines are headings of their own.
- **Lines:** paragraphs are cut by the S10b profile and the PBY character and niqqud rules, into plain and pointed
  files.
- **Duplicates:** exact duplicates are dropped, and so are lines already in the `--dedup-against` corpora.

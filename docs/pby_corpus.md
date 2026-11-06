# PBY public-domain corpus (`S15b`)

This is the offline intake builder for Project Ben-Yehuda (PBY) public-domain
Hebrew text. It implements the `hocrsyngen` plan
[`docs/pby_public_domain_text_intake_plan.md`](https://github.com/HeOCR/hocrsyngen/blob/main/docs/pby_public_domain_text_intake_plan.md)
(`S15a`) under
[ADR 0007](https://github.com/HeOCR/hocrsyngen/blob/main/docs/decisions/0007-third-party-public-domain-training-text.md).
Section numbers below (§1–§7) refer to that plan.

Credit: [Project Ben-Yehuda volunteers](https://benyehuda.org), as PBY's dump
README asks of reusers who give credit. Every corpus card carries it.

## Inputs

| Input | Where | Pinned by |
| --- | --- | --- |
| PBY dump | a local checkout of `projectbenyehuda/public_domain_dump`; only `pseudocatalogue.csv`, `txt/` and `txt_stripped/` are read | commit `5e4277fead7b565f32cc4b352abd3565023a77d8` (VERSION `2026-03`) |
| Creator death years | [`data/pby/creators.json`](../data/pby/creators.json) | Wikidata revision id per creator; the dump commit |
| Leakage fixtures | [`data/leakage/`](../data/leakage/) | the source commit of each protected file |
| Wrap check and length profile | `hocrsyngen`, installed with the `fit` extra | `hocrsyngen` commit `88c61af4c12cc4a462fc1f57a1c4027b3459366d` |

The dump is not in this repository. A sparse checkout of the text is enough:

```bash
git clone --filter=blob:none --no-checkout https://github.com/projectbenyehuda/public_domain_dump.git dumps/pby
git -C dumps/pby sparse-checkout set --no-cone '/*.csv' '/LICENSE' '/README*' '/VERSION' '/txt/' '/txt_stripped/'
git -C dumps/pby checkout 5e4277fead7b565f32cc4b352abd3565023a77d8
```

## Building

```bash
python -m pip install --no-binary Pillow -C raqm=enable "Pillow>=10"
python -m pip install -e ".[fit]"
htext pby build --dump dumps/pby --output out/pby-v1
```

The build reads no network. Defaults: `--as-of 2026`, `--seed 15`,
`--niqqud-threshold 0.5`, `--max-lines-per-work 200`, the §7.5 genre
allowlist, and the S10b training text in `hocrsyngen` as the length profile.
`--no-fit-check` skips the wrap check (for experiments only). The card records
that the check did not run.

### Creator death years

`scripts/fetch_pby_creators.py` is the only step that uses the network. It runs
once per pin, outside the build, and writes `data/pby/creators.json`. That
file holds every distinct author and translator QID in the catalogue (903),
with each item's P570 and P569 years and its Wikidata revision id. The year
rules are conservative:

- deprecated claims are ignored;
- a decade or century gives the latest year it allows;
- several death claims give the latest.

The catalogue writes `Q0` for "no item"; that is treated as no QID. The
`manual` list resolves a creator without a QID by name. Each manual row needs
a death year and a citable source, and it ships empty.

## What a build writes

| File | Contents |
| --- | --- |
| `pby_lines_il_plain_v1.txt`, `pby_lines_il_niqqud_v1.txt` | lines from works with `pd_israel` true |
| `pby_lines_il_us_plain_v1.txt`, `pby_lines_il_us_niqqud_v1.txt` | the subset whose works also have `pd_us` true |
| `pby_rights_index.v1.jsonl` | §1, one row per catalogue work (all 26,455), with `as_of` |
| `pby_line_index.v1.jsonl` | one row per `il` line: `sha256`, `pby_work_id`, `subset`, `genre`, `period` (decade of the latest creator death), `il_us` |
| `pby_excluded_works.v1.json` | §6, every work with a line in any variant, with title, creator QIDs and the corpus sha256s |
| `corpus_card.json`, `CORPUS_CARD.md` | provenance, parameters, rights tallies, per-file counts, sha256 and length profile, pipeline counts, niqqud density histogram |
| `SHA256SUMS` | sha256 of every file above |

Every file is in the S10b format: UTF-8, LF, one line per row, NFC, and no
blank lines. Each corpus file is a separate `--text-corpus` input for
`hocrsyngen`, which records it as `external:sha256:<hex>`.

**One file per subset.** The plan's §3 lists one `pby_lines_<variant>_v1.txt`
per variant. The build writes plain and niqqud lines to separate files, as the
packaged S10b corpora do, so a training run can pick either subset without
filtering. The line index still records `subset` for every line.

## Rights (§1, §2)

Rights are computed per work against `as_of`:

- **`pd_israel`:** every author and every translator has a sourced death year
  of `as_of − 71` or earlier. Otherwise the basis is `creator_in_term`,
  `anonymous_unresolved` (`אלמוני/ת`) or `creator_death_year_unknown`.
- **`pd_us`:** `true` when the year of the edition PBY transcribed is before
  `as_of − 95`. That year is an upper bound on first publication. Otherwise
  `pd_us` is `"unknown"`. No first-publication years are sourced yet, so
  `published_in_term` and `uraa_candidate` are implemented but never occur.
- **Edition years:** these come from `source_edition`. The parser reads
  Gregorian years, and Hebrew years such as `תרנ"ג` or `ה'תש"ח` with values of
  500 and up. `ת"א` (Tel Aviv) and other short abbreviations are not years.
  The latest year in a note is used.
- **PBY's own flag:** `pby_public_domain` is true for every row, with the
  dump LICENSE as its basis. It never sets `pd_israel` on its own.

The rights fields are the project's reading of the law, not legal advice.

## Lines (§7)

1. **Clean.**
   - Drop the title line, the PBY credit footer and the footnote block. The
     block starts at the run of blank lines before the first `↩` back-link, so
     multi-line notes go too. A work whose notes have no blank-line gap is
     dropped.
   - In works with notes, digits glued to a word are footnote references and
     are removed. In other works such lines are dropped.
   - Remove variation selectors, bidi controls and zero-width characters, then
     normalise spacing and apply NFC.
   - Drop lines with entities, URLs or Latin letters.
2. **Character set.**
   - Keep Hebrew letters, digits, the S10b punctuation (without Latin) and the
     S13b typographic marks.
   - Maqaf is kept when it passes the S13b glyph check in both packaged fonts.
     It passes at `hocrsyngen` 88c61af.
   - Lines with any other character, a medial final form or a run of seven or
     more digits are dropped.
3. **Cut.**
   - Poetry keeps its verse lines, and a verse over 55 characters is split in
     balance at spaces.
   - Other genres are packed: each line draws a target length from the S10b
     profile and ends at the word boundary closest to it. It may end earlier
     at a sentence end, once it reaches 80% of the target. A paragraph's last
     line under 12 characters joins the one before it.
   - Every line then passes the S10b no-loss rule with `hocrsyngen`'s
     `_wrap_hebrew_text` and packaged fonts:
     - no word is wider than any body (`printed_letter` and `handwritten_note`
       at 968 px, `archive_card` at 498 px, the ledger details cell at 206 px);
     - an `archive_card` line takes at most 2 rows, and a ledger cell at most
       10.

     `tests/test_fit.py` checks this region table against `hocrsyngen`'s own.
4. **Niqqud split.**
   - `txt/` and `txt_stripped/` lines are cut at the same word boundaries.
   - A segment whose pointed form has a density of 0.5 or more, and no
     cantillation, meteg, rafe or other mark outside the S10b set, goes to the
     niqqud subset in its pointed form.
   - Every other segment goes to the plain subset in its stripped form.
     Leftover marks in `txt_stripped/` (qamats qatan, rafe) are removed.
5. **Register.**
   - The genre allowlist is prose, article, memoir, letters, fables and poetry.
   - Lines are deduplicated on their plain form across the whole build.
   - A per-work cap (200 by default, sampled deterministically) keeps long
     works from dominating.
   - The content screen (`--screen-terms`) drops lines containing any listed
     term. No list ships yet, so a default build screens nothing; the card
     says so.
6. **Leakage.**
   - No line may share its NFC text, or any word 3-gram, with protected
     evaluation text. Both the pointed and the stripped forms are checked.
   - The protected text is the `hocrsyngen` packaged evaluation files at
     88c61af (`hebrew_lines.txt`, which is the seed-101 text, and the S10b,
     S10b niqqud, S13a and S13b eval files), plus the `hocrgen` bidi synthetic
     corpus at c8fb74e.
   - The fixtures are hash-only, so tests stay offline. They also hash each
     protected line's niqqud-stripped form. The `hocrgen` hashes are a superset
     of `hocrsyngen`'s S13a fixture.

## Open items

- **Content screen term list:** needs a maintainer-reviewed list.
- **Manual creator rows:** 2,781 works lack a usable death year. The largest
  groups are medieval and early-modern poets without a QID in the catalogue.
- **First-publication years:** sourcing these would widen `il_us`.
- **Hosting of large outputs:** see the S15b PR.

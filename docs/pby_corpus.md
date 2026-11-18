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
htext pby build --dump dumps/pby --output out/pby-v2 \
  --reserved ~/clones/heocr-restricted-eval/reservations/eval_reservations_v2.json \
  --leakage <dir with data/leakage/*.hashes.json and eval's fixtures>
```

The build reads no network. Defaults: `--as-of 2026`, `--seed 15`,
`--niqqud-threshold 0.5`, `--corpus-version v2`, no per-work cap
(`--max-lines-per-work 0`), the v2 genre allowlist, and the S10b training text in `hocrsyngen` as the length profile.
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
`manual` list resolves, by name, a creator without a QID or whose Wikidata item
has no death year; a Wikidata death year always wins. Each manual row needs a
death year and a citable source. Since v2 it holds 139 reviewed rows, for the
creators who blocked the most works. 138 died by 1955 and one in 1970. Most
sources are the creator's PBY author page. A creator known only by period
gets the latest year the period allows. Rerunning the fetch script keeps the
manual rows.

## What a build writes

| File | Contents |
| --- | --- |
| `pby_lines_il_plain_<version>.txt`, `pby_lines_il_niqqud_<version>.txt` | lines from works with `pd_israel` true |
| `pby_lines_il_us_plain_<version>.txt`, `pby_lines_il_us_niqqud_<version>.txt` | the subset whose works also have `pd_us` true |
| `pby_rights_index.v1.jsonl.gz` | §1, one row per catalogue work (all 26,455), with `as_of` |
| `pby_line_index.v1.jsonl.gz` | one row per `il` line: `sha256`, `pby_work_id`, `subset`, `genre`, `period` (decade of the latest creator death), `il_us` |
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

- **Release fields** (decision 0022, from builds after `v1`): every rights
  row also carries `source_licence: "Public Domain"`, `htext_release: "cc0"`,
  the PBY `credit` and `text_quality: "transcription"`. The build passes every
  work with lines through `htext.release.ReleaseGuard("cc0")`, and the card
  records the guard's summary under `release`. A work with no line in the build
  (not public domain in Israel, reserved, another genre, or every line
  dropped) has `htext_release: null`: it is in no release, whatever PBY's
  label. The card lists the creators in term (died after `as_of − 71`), with
  their works and how many have lines, which is always 0. The published `v1` files predate
  these fields; [`data/releases.json`](../data/releases.json) records `v1` as
  `htext-cc0`.

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
   - PBY writes a verse break inside a running line as a lone `/` (or `//`).
     Print never shows it, so since v2 it ends a line and the mark is dropped
     (`source_lines_split:verse_break_mark`). The published `v1` corpus still
     has these marks: 43,176 of its 401,492 niqqud lines contain one.
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
   - The genre allowlist is prose, article, memoir, letters, fables and poetry
     (v1), plus reference and drama (v2). Lexicon entries stay out.
   - Lines are deduplicated on their plain form across the whole build.
   - A per-work cap (`--max-lines-per-work`, sampled deterministically) can
     keep long works from dominating. v1 used 200. Since v2 there is no
     build-time cap: the line index keeps `pby_work_id`, so a per-work share
     is a mix-time choice.
   - The content screen (`--screen-terms`) drops lines containing any listed
     term. By maintainer decision no list ships and a default build screens
     nothing: HeOCR has to read real historical text as written. The card says
     so.
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
   - **Eval reservations.** `--reserved FILE` (repeatable) loads eval's
     `reservations/eval_reservations_v1.json` from heocr-restricted-eval
     (schema `heocr_eval_reservations.v1`), or an `htext_reservations.v1`
     file (`htext.reservations`). Every reserved PBY work is left out whole,
     whatever its rights or genre, and counted as `works_skipped:eval_reserved`.
     A CLI build refuses to run without `--reserved`, unless `--no-reservations`
     is given; that is for experiments only, and the card then records that no
     reservations were loaded. The card records each set's name, the file's
     sha256 and per-source counts, but never the reserved ids.
   - **Scope of the exclusion list.** `pby_excluded_works` lists the works
     with lines in *this* corpus. Other HeOCR training lists also draw on PBY
     works, for example lines aligned to NLI scans of the same books. So a set
     meant to be safe for evaluation must also be checked against those
     training lists, not only against htext.

## Open items

- **Manual creator rows:** in v1, 2,781 works lacked a usable death year.
  v2 adds rows for the top 150 creators: 139 are settled, and 11 are living,
  unknown or unsure. Rows for the remaining 225 creators can follow.
- **First-publication years:** sourcing these would widen `il_us`.

## Published build (`v2`)

The pinned `v2` build is in [`data/pby/v2/`](../data/pby/v2/): the corpus card,
`SHA256SUMS`, the exclusion list and the gzipped rights index. The four
corpus files and the gzipped line index are assets of the
[`pby-v2` release](https://github.com/HeOCR/htext/releases/tag/pby-v2).
It supersedes `v1`.

| File | Lines | Works |
| --- | ---: | ---: |
| `pby_lines_il_plain_v2.txt` | 12,318,857 | 16,424 |
| `pby_lines_il_niqqud_v2.txt` | 1,680,295 | 15,742 |
| `pby_lines_il_us_plain_v2.txt` | 407,456 | 564 |
| `pby_lines_il_us_niqqud_v2.txt` | 18,613 | 325 |

**Length profile.** The plain files meet every S10b target. Splitting at verse
marks leaves more short verse lines, so `pby_lines_il_niqqud_v2.txt` has 17.6%
of its lines at 31–55 characters, just under the 18% floor; its median (21) and
36–47 share (10.2%) pass. `il_us` niqqud missed in `v1` too. These files are
inputs to a training mix, and the profile targets apply to the mix, so v2 does
not reshape real verse lines to meet them.

25,282 works have lines. All of them are `htext-cc0`, and every other work has
`htext_release: null`. `tests/test_published_v2.py` checks the committed files.
It checks that each work with lines is `pd_israel` true and every other work is
in no release, and that the creator who died in 1970 has 7 works, all
`creator_in_term`, none with lines.

## Published build (`v1`)

Superseded by `v2`. Known issues found after publication are in
[`data/pby/v1/KNOWN_ISSUES.md`](../data/pby/v1/KNOWN_ISSUES.md); the `v1` files
and their sha256s stay as published.

The pinned `v1` build is in [`data/pby/v1/`](../data/pby/v1/): the corpus card
(`CORPUS_CARD.md`, `corpus_card.json`), `SHA256SUMS`, the exclusion list and
the gzipped rights index. The four corpus files and the gzipped line index
are assets of the [`pby-v1` release](https://github.com/HeOCR/htext/releases/tag/pby-v1).
Check them with `sha256sum -c` against `data/pby/v1/SHA256SUMS`. Gzip bytes
depend on the zlib version, so a rebuild elsewhere should compare the
decompressed indexes if their `.gz` sha256 differs.

# htext

Open Hebrew text corpora for HeOCR recognizer training. Each corpus entry
carries its own rights record: `pd_israel` and `pd_us`, each with the
basis it was computed from and the `as_of` year.

The corpora feed the HeOCR synthetic page generator,
[`hocrsyngen`](https://github.com/HeOCR/hocrsyngen), through its
`--text-corpus` option. The generator records each corpus as
`external:sha256:<hex>`, so it needs no change to use one.

## Status

The first corpus is public-domain text from
[Project Ben-Yehuda](https://benyehuda.org) (PBY). The `htext pby build`
command builds it offline, from a pinned checkout of PBY's
`public_domain_dump`. How to build it, what a build writes, and the rights and
line rules are in [`docs/pby_corpus.md`](docs/pby_corpus.md). The design is the
`hocrsyngen` plan
[`docs/pby_public_domain_text_intake_plan.md`](https://github.com/HeOCR/hocrsyngen/blob/main/docs/pby_public_domain_text_intake_plan.md)
(`S15a`), and the maintainer decisions are in
[ADR 0007](https://github.com/HeOCR/hocrsyngen/blob/main/docs/decisions/0007-third-party-public-domain-training-text.md):

1. Outside public-domain text is allowed for training.
2. Public domain in Israel is enough. US status is recorded per entry, so a
   corpus that is also public domain in the US can be built.
3. The share of outside text in a training mix is a hyperparameter.
4. A translation is public domain only if both its author and its translator
   are.

The second corpus is the enacted laws of the first eight Knessets, as
published in Reshumot (section 6 of the Copyright Act, `htext-cc0`). Its text is
the scans' OCR layer, filtered against a lexicon and checked by eye. The current version is `v2`, which also leaves out every line that overlaps HeOCR's evaluation text. How it is
fetched and built, and the published `v1`, are in
[`docs/knesset_laws.md`](docs/knesset_laws.md). The `htext tanakh build` command
builds the Hebrew Bible from the public-domain Westminster Leningrad Codex,
pointed and plain; see [`docs/tanakh.md`](docs/tanakh.md).
The Knesset plenary records (K1–8 to 1975, and K13–25) are next: how they are
fetched, with eval-reserved sittings never downloaded, and how they are built
(the privacy gate, OCR and transcription files), is in
[`docs/knesset_plenary.md`](docs/knesset_plenary.md).
`htext wikisource build` prepares Hebrew Wikisource text for `htext-by-sa`,
with reviewed main-namespace works and laws or proofread Pages, attribution by
page revision and required eval exclusions.
The builder is documented in [`docs/wikisource.md`](docs/wikisource.md).

## Downloads

| Corpus | GitHub release | Hugging Face | Zenodo |
| --- | --- | --- | --- |
| Knesset laws | `knesset-laws-v2` | [`HeOCR/htext-knesset-laws`](https://huggingface.co/datasets/HeOCR/htext-knesset-laws) | [10.5281/zenodo.24384730](https://doi.org/10.5281/zenodo.24384730) |
| Project Ben-Yehuda | withdrawn (`pby-v1`, `pby-v2`, `pby-v3`) | withdrawn | withdrawn |
| Tanakh | withdrawn (`tanakh-v1`) | withdrawn | withdrawn |

**Withdrawn 2026-11-20.** HeOCR's evaluation first reported that the filtered
pby and Tanakh copies on Hugging Face and Zenodo share no text with its
evaluation sets. That check was faulty: it did not normalise pointed target
text. The corrected check found remaining overlap in them (and the GitHub
release files, which were never filtered, overlap more). On the maintainer's
decision, the files were taken down:

- the GitHub release assets were removed; the release pages, cards, rights
  indexes and checksums stay as the record of what was published;
- the Hugging Face datasets `HeOCR/htext-pby` and `HeOCR/htext-tanakh` are
  private;
- the Zenodo records were deleted: `10.5281/zenodo.24384745` (pby-v3) and
  `10.5281/zenodo.24384726` (tanakh-v1) now resolve to tombstones that keep the
  citation. The decontaminated versions will get new Zenodo records with new
  concept DOIs.

HeOCR keeps a private, checksum-verified backup. Decontaminated versions, which
must pass the corrected check with zero overlap, will be published as new
versions. Knesset laws `v2` passed the corrected check and stays.

## Plan

[`docs/sources_plan.md`](docs/sources_plan.md) lists the sources htext will add, their rights basis, estimated
sizes and build order. htext ships three releases split by licence (heocr-engine decision 0022): `htext-cc0`
(public domain, CC0 and §6 official texts; the default), `htext-by` (CC BY) and `htext-by-sa` (CC BY-SA). NC and
ND text is in none of them, and no line crosses releases.

## Rules for this repository

- **No source dumps in git.** Builders read pinned local inputs. Only the
  outputs a corpus card lists are published.
- **No network in tests.** Tests use small synthetic fixtures. Lookups that
  need the network (for example creator death years) run once, offline from
  the build, and their results are committed as pinned, reviewed files.
- **Leakage checks.** Corpus lines must not overlap HeOCR evaluation text.
  Each corpus card says which checks ran.
- **One release per licence** (decision 0022). Every entry records its
  `source_licence` (the source's exact label), the `htext_release` that label
  maps to (`cc0`, `by` or `by-sa`), its `credit` and its `text_quality`
  (`transcription` or `ocr_layer`). `htext.release` holds the label map and
  the guard every corpus writer calls; NC, ND, unknown and unlisted labels are
  refused, and a build admits only entries of its own release.
  [`data/releases.json`](data/releases.json) lists each published corpus
  version and its release. Lines with `text_quality: ocr_layer` never feed
  word lists, lexicons or dawgs.
- **Rights are per entry.** A corpus variant includes an entry only if its
  rights record passes that variant's rule. The rights fields are the
  project's reading of the law, not legal advice.

## Licensing

This repository has two licence scopes:

| Scope | What it covers | Licence |
| --- | --- | --- |
| Code | `src/`, `tests/`, `scripts/`, `.github/`, and build configuration | MIT, see [`LICENSE`](LICENSE) |
| Data | `htext-cc0` processed text, rights and line indexes, exclusion lists, corpus cards and checksums | CC0-1.0, see [`LICENSE-DATA`](LICENSE-DATA) |
| Processed Wikisource text | text for `htext-by-sa`, with NOTICE and per-page attribution in the rights index | CC BY-SA 4.0, see [`docs/wikisource.md`](docs/wikisource.md) |

The `htext-cc0` source texts are in the public domain or unprotected by law. PBY's own dump licence says
"Public domain". HeOCR's processing, selections and indexes are dedicated to
the public domain under CC0-1.0 too, so the data can be used without
conditions.

**Attribution.** PBY asks for credit but does not require it. HeOCR gives it
anyway, in the form PBY's dump README asks for:

> Credit: [Project Ben-Yehuda volunteers](https://benyehuda.org)

Every PBY corpus card carries this credit with the link, and so should any
dataset or model card that uses a PBY corpus.

## Development

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[test]"
python -m pytest
```

The fit tests (`tests/test_fit.py`) also need `hocrsyngen` and Pillow built
with libraqm. They skip without them. CI runs them in its `fit` job, against
`hocrsyngen` at the pinned commit.

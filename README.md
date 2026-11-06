# htext

Public-domain Hebrew text corpora for HeOCR recognizer training. Each corpus
entry carries its own rights record: `pd_israel` and `pd_us`, each with the
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

## Rules for this repository

- **No source dumps in git.** Builders read a local checkout of each source at
  a pinned commit. Only the outputs a corpus card lists are published.
- **No network in tests.** Tests use small synthetic fixtures. Lookups that
  need the network (for example creator death years) run once, offline from
  the build, and their results are committed as pinned, reviewed files.
- **Leakage checks.** Corpus lines must not overlap HeOCR evaluation text.
  Each corpus card says which checks ran.
- **Rights are per entry.** A corpus variant includes an entry only if its
  rights record passes that variant's rule. The rights fields are the
  project's reading of the law, not legal advice.

## Licensing

This repository has two licence scopes:

| Scope | What it covers | Licence |
| --- | --- | --- |
| Code | `src/`, `tests/`, `scripts/`, `.github/`, and build configuration | MIT, see [`LICENSE`](LICENSE) |
| Data | everything under `data/`, and every corpus build output: processed text, rights and line indexes, exclusion lists, corpus cards and checksums | CC0-1.0, see [`LICENSE-DATA`](LICENSE-DATA) |

The source texts are in the public domain. PBY's own dump licence says
"Public domain". HeOCR's processing, selections and indexes are dedicated to
the public domain under CC0-1.0 too, so the data can be used without
conditions.

**Attribution.** PBY asks for credit but does not require it. HeOCR gives it
anyway: "Text from Project Ben-Yehuda (https://benyehuda.org), prepared by
Project Ben-Yehuda volunteers". Every PBY corpus card carries this line, and
so should any dataset or model card that uses a PBY corpus.

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

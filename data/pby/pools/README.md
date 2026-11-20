# pby-v3 prose pool v1.1

A CC0 pool of paragraph-sized prose chunks for the `hdocsyngen` pilot, cut from
the published `pby-v3` release (`pby_lines_il_us_plain_v3.txt` and
`pby_line_index.v1.jsonl.gz`). The pool files are not in git; this page pins
them so they can be rebuilt.

```bash
python scripts/build_pby_prose_pool.py <dir with the pby-v3 assets> htext_pby_v3_il_us_prose_pool.v1.jsonl
```

The script checks both inputs against their sha256 first and is seeded (15).
It writes pool `v1`: 4,000 entries. Pool `v1.1` is `v1` with 19 entries
removed for overlap with HeOCR's private evaluation sets. HeOCR's evaluation
keeps that list, and its official check found `v1.1` clean.

| File | Entries | sha256 |
| --- | ---: | --- |
| `htext_pby_v3_il_us_prose_pool.v1.1.jsonl` | 3,981 | `1ac260b59b41195d3919d5b8ef1993433bc34c465adcc89f66ddd6e563f0b917` |
| `htext_pby_v3_il_us_prose_pool.v1.1.meta.jsonl` | 3,981 | `37f8bc2757c5ecc7c84d922da7186b565d51de83d563a03a47fc7aa998b63ede` |

Checked on 2026-11-20: a rebuild of `v1`, minus the 19 entries, gives these
sha256s byte for byte.

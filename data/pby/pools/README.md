# pby-v3 prose pool v1.2

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

## v1.2 (2026-11-20)

A corrected overlap check by HeOCR's evaluation (pointed target text normalised) found 3 entries of `v1.1` that share
text with its evaluation sets. `v1.2` is `v1.1` without them: 3,978 entries. HeOCR's evaluation checked it and found
it clean. Use `v1.2`; `v1.1` is superseded.

| File | Entries | sha256 |
| --- | ---: | --- |
| `htext_pby_v3_il_us_prose_pool.v1.2.jsonl` | 3,978 | `63ca1f9708111f361ca6959a5576e584392b11171b3f56d28a1e79f49d18926a` |
| `htext_pby_v3_il_us_prose_pool.v1.2.meta.jsonl` | 3,978 | `d611434e5e859aff1a5abdcb1b88bbec132cae105126ed596a2d1a51a58c5a2e` |

The pool is built from the pby-v3 release files, which have since been withdrawn. HeOCR keeps them in a private backup.


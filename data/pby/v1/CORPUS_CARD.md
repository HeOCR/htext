# PBY public-domain Hebrew lines

Text from Project Ben-Yehuda (https://benyehuda.org), prepared by Project Ben-Yehuda volunteers.

Credit: [Project Ben-Yehuda volunteers](https://benyehuda.org).

- Source: `projectbenyehuda/public_domain_dump` at `5e4277fead7b565f32cc4b352abd3565023a77d8` (VERSION `2026-03`), 26455 catalogue rows.
- Rights computed for `as_of` 2026. `pd_israel` and `pd_us` are this build's reading of the law, not legal advice; see `pby_rights_index.v1.jsonl.gz`.
- Outputs are CC0-1.0. Source text: Public domain (public_domain_dump LICENSE); PBY requests credit, which this card gives.
- Builder: `htext` 0.1.0.

## Files

| File | Variant | Subset | Lines | Works | Bytes | sha256 |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `pby_lines_il_plain_v1.txt` | il | plain | 1627470 | 13857 | 74372961 | `4cedcd0a882c1a7fbab93fb2efb55b26d9b2b34a92be77129cf78288ef4fbade` |
| `pby_lines_il_niqqud_v1.txt` | il | niqqud | 401492 | 12911 | 30797418 | `a1b78dc5b467189ed431b7daf8f044f1aa03b1f0389dc7320109dfbf0bb2285f` |
| `pby_lines_il_us_plain_v1.txt` | il_us | plain | 70251 | 559 | 3263817 | `05983a2088e8da4ed6855f3bb52c97a727a2d31ed952b9422c2e23de42cf8161` |
| `pby_lines_il_us_niqqud_v1.txt` | il_us | niqqud | 10050 | 290 | 738977 | `ead01b4247123b10bd47007540a1a542d44c727335ae7bd77595a01a18d7adef` |

`il`: every line is from a work that is public domain in Israel. `il_us`: also public domain in the US.
`niqqud` lines are pointed (density at or above the threshold); `plain` lines carry no points.

## Length profile

Characters per line; niqqud lines are measured without their points.

| File | Max | Median | 31-55 | 36-47 | Passes |
| --- | ---: | ---: | ---: | ---: | --- |
| `pby_lines_il_plain_v1.txt` | 55 | 23.0 | 21.0% | 11.9% | all |
| `pby_lines_il_niqqud_v1.txt` | 55 | 23.0 | 22.7% | 11.9% | all |
| `pby_lines_il_us_plain_v1.txt` | 55 | 23 | 22.4% | 13.5% | all |
| `pby_lines_il_us_niqqud_v1.txt` | 55 | 24.0 | 15.6% | 6.2% | fails: share_31_55, share_36_47 |

Targets (S10b): at most 55 characters; 18%-35% of lines at 31-55; at least 10% at 36-47; median 18-30.

## Rights

| `pd_israel_basis` | Works |
| --- | ---: |
| `all_creators_died_by:1955` | 23302 |
| `anonymous_unresolved` | 164 |
| `creator_death_year_unknown` | 2781 |
| `creator_in_term` | 208 |

| `pd_us_basis` | Works |
| --- | ---: |
| `published_before:1931` | 715 |
| `unknown` | 25740 |

Works with lines in this build: 21799 (`il`), 668 (`il_us`).

## Build parameters and checks

- Genres: prose, article, memoir, letters, fables, poetry.
- Niqqud threshold: 0.5. Seed: 15. Max lines per work: 200.
- Maqaf allowed: True.
- Content screen: none applied. No words are filtered by default: HeOCR has to read real historical text as written. `--screen-terms` exists for builds that need a screen.
- No-loss wrap check: {"ran": true, "hocrsyngen_version": null, "hocrsyngen_commit": "88c61af4c12cc4a462fc1f57a1c4027b3459366d", "bodies": [{"template_id": "printed_letter", "font_file": "Alef-Regular.ttf", "size": 42, "width": 968, "rows_per_line": null}, {"template_id": "handwritten_note", "font_file": "GveretLevin-Regular.ttf", "size": 46, "width": 968, "rows_per_line": null}, {"template_id": "archive_card", "font_file": "Alef-Regular.ttf", "size": 38, "width": 498, "rows_per_line": 2}, {"template_id": "ledger", "font_file": "Alef-Regular.ttf", "size": 30, "width": 206, "rows_per_line": 10}], "maqaf_glyph_check": true}.
- Length profile source: hocrsyngen texts/hebrew_lines_train_v1.txt.
- Leakage: no line, and no word 3-gram, is shared with these protected texts (pointed and stripped forms):
  - `HeOCR/hocrgen` `docs/evaluation-fixtures/bidi-synthetic-corpus.txt` @ `c8fb74eb5d0a`
  - `HeOCR/hocrsyngen` `src/hocrsyngen/data/synthetic/texts/hebrew_lines.txt` @ `88c61af4c12c`
  - `HeOCR/hocrsyngen` `src/hocrsyngen/data/synthetic/texts/hebrew_lines_eval_v1.txt` @ `88c61af4c12c`
  - `HeOCR/hocrsyngen` `src/hocrsyngen/data/synthetic/texts/hebrew_lines_niqqud_eval_v1.txt` @ `88c61af4c12c`
  - `HeOCR/hocrsyngen` `src/hocrsyngen/data/synthetic/texts/hebrew_mixed_lines_eval_v1.txt` @ `88c61af4c12c`
  - `HeOCR/hocrsyngen` `src/hocrsyngen/data/synthetic/texts/hebrew_typographic_lines_eval_v1.txt` @ `88c61af4c12c`

## Pipeline counts

| Step | Count |
| --- | ---: |
| `segments` | 10206495 |
| `segments_dropped:charset` | 58791 |
| `segments_dropped:duplicate` | 335407 |
| `segments_dropped:fit:archive_card:too_many_rows` | 4940 |
| `segments_dropped:fit:archive_card:word_too_wide` | 28 |
| `segments_dropped:fit:ledger:word_too_wide` | 5668 |
| `segments_dropped:fit:printed_letter:word_too_wide` | 1 |
| `segments_dropped:leak_line` | 43 |
| `segments_dropped:leak_word3` | 1180 |
| `segments_dropped:long_digit_run` | 6 |
| `segments_dropped:medial_final_form` | 1200 |
| `segments_dropped:per_work_cap` | 7726087 |
| `segments_dropped:too_few_letters` | 43019 |
| `segments_dropped:too_long` | 1163 |
| `source_lines` | 3634797 |
| `source_lines_dropped:entity` | 5535 |
| `source_lines_dropped:latin` | 21627 |
| `source_lines_dropped:letter_digit` | 4482 |
| `source_lines_plain_only:word_mismatch` | 119 |
| `works_read` | 22049 |
| `works_skipped:genre` | 1361 |
| `works_skipped:not_pd_israel` | 3045 |
| `works_with_lines` | 21799 |

## Niqqud density histogram

Segments that had a pointed form, by the share of Hebrew letters carrying a point.

| Density | Segments |
| --- | ---: |
| 0.0-0.1 | 8255288 |
| 0.1-0.2 | 399111 |
| 0.2-0.3 | 158525 |
| 0.3-0.4 | 30807 |
| 0.4-0.5 | 11406 |
| 0.5-0.6 | 139347 |
| 0.6-0.7 | 623881 |
| 0.7-0.8 | 410063 |
| 0.8-0.9 | 66734 |
| 0.9-1.0 | 6170 |

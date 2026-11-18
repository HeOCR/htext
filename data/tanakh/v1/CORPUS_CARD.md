# Tanakh: the Westminster Leningrad Codex, pointed and plain

- **Release:** `htext-cc0` (decision 0022). Source licence: `Public Domain`. Outputs: CC0-1.0.
- **Credit:** [Westminster Leningrad Codex (public domain), via the Open Scriptures Hebrew Bible](https://github.com/openscriptures/morphhb).
- **Source:** [`openscriptures/morphhb`](https://github.com/openscriptures/morphhb) @ `db6c5c9b46b8f39346f10915ddb1a70dcd429901`, `wlc/`. Edition: Westminster Leningrad Codex (WLC), not UXLC; the files name WLC version 4.20.
- **Public domain.** The Leningrad Codex is about a thousand years old, and the WLC text is in the public domain:
  - README.md: "The text of the WLC remains in the Public Domain."
  - LICENSE.md: "This work is based on The Westminster Leningrad Codex, which is in the public domain."
  - wlc/*.xml <work osisWork="WLC">: "<rights>Public Domain</rights>"
- **Not used:** OSHB's lemma, morphology and n attributes (CC BY 4.0) and its / morpheme dividers; marginal readings (qere) and notes.
- **Books:** 39 of 39 with lines; 23,213 verses read.
- **Eval reservations:** 8 sets loaded.
- **Leakage check:** line and word 3-grams, in either form, against 8 fixtures.
- **Fit check:** ran.

## Notes

- Biblical verses are quoted in many printed Hebrew pages, including pages in HeOCR's evaluation sets. The leakage check drops lines that match evaluation text, but a quotation can still match a line here; run the training-time overlap check (CLEAN) against your evaluation set before training on this corpus.
- Every line exists in both files. A repeated verse is kept once per file, so the two files can differ slightly in length.

## Files

| File | Form | Lines | Median chars | 31-55 share | 36-47 share | Profile |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `tanakh_lines_niqqud_v1.txt` | niqqud | 58,120 | 23.0 | 21.9% | 10.9% | pass |
| `tanakh_lines_plain_v1.txt` | plain | 58,074 | 23.0 | 21.9% | 10.9% | pass |

## Pipeline

| Counter | Value |
| --- | ---: |
| `books:with_lines` | 39 |
| `lines_deduplicated:plain` | 46 |
| `marks_removed:paseq` | 2,273 |
| `marks_removed:pe` | 1,181 |
| `marks_removed:reversednun` | 9 |
| `marks_removed:samekh` | 1,981 |
| `marks_removed:sof-pasuq` | 23,192 |
| `notes_skipped:alternative` | 119 |
| `notes_skipped:editorial` | 3,099 |
| `notes_skipped:exegesis` | 21 |
| `notes_skipped:variant` | 1,260 |
| `segments` | 59,589 |
| `segments_dropped:duplicate` | 1,262 |
| `segments_dropped:fit:archive_card:too_many_rows` | 194 |
| `segments_dropped:fit:ledger:word_too_wide` | 6 |
| `segments_dropped:leak_word3` | 6 |
| `segments_dropped:medial_final_form` | 1 |
| `verses` | 23,213 |
| `words:ketiv` | 1,268 |

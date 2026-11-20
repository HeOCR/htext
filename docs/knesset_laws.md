# Knesset laws (`knesset-laws`)

Enacted laws of the first eight Knessets, as published in Reshumot. Section 6 of the Israeli Copyright Act 2007
leaves laws unprotected, so the corpus goes to `htext-cc0` with the source licence
`Israel Copyright Act 2007 s.6 (not protected)`. This is source 2 of the
[sources plan](sources_plan.md).

The intake has three steps: fetch (network, once per pin), extract (local tools), and build (no network).

## What is fetched

| Step | Where | What |
| --- | --- | --- |
| Bills | Knesset OData `KNS_Bill` (`https://knesset.gov.il/Odata/ParliamentInfo.svc`, no key) | every bill of the chosen Knessets with a publication series (`PublicationSeriesID` not null): name, Knesset, publication date, series, booklet (`MagazineNumber`) and page |
| Documents | `KNS_DocumentBill`, group 9 only ("חוק - פרסום ברשומות", files `<k>_lsr_<n>`) | the law as published; first-reading bills (group 2, `_ls1_`) are out by plan decision 2 and never listed |
| Files | `fs.knesset.gov.il` | each group-9 DOC and PDF; TIF scans are not fetched |

- **DOC and PDF.** The PDFs are scans with an OCR text layer. Where the Knesset also gives a Word file, it holds the
  same OCR text in logical reading order, with margin notes as separate paragraphs. The builder reads the DOC where it
  exists and the PDF text otherwise, and marks both `text_quality: ocr_layer`. The PDF is kept for the eye check
  against the scan.
- **Booklets.** `MagazineNumber` of a Sefer HaChukim bill (series 6071) is its booklet number. Eval reserves booklets
  as `sefer_hachukim_<n>`, so the builder leaves out every law in a reserved booklet, whole.

## Running

```bash
python scripts/fetch_knesset_laws.py --knessets 1-8 \
  --inputs ../work/knesset-laws/inputs \
  --manifest data/knesset_laws/sources.v1.json
```

- The script refuses an `--inputs` directory inside a git work tree.
- `--catalogue-only` lists bills and files and downloads nothing.
- A rerun reuses files already on disk, hashes them again, and retries files that failed.

## Politeness

The fetcher sends one request at a time, at least one second apart (`--min-interval`, never less than 1), with the
generic client name `htext-fetch/0.1 (https://github.com/HeOCR/htext)`. Server errors and HTTP 429 are retried
three times with backoff; other errors are recorded in the manifest and are not retried. Every request goes to a
JSON-lines log (`<inputs>/fetch_log.jsonl` by default): time, URL, attempt, status, size and sha256.
`fs.knesset.gov.il` has no robots file, and no Knesset terms of use could be found (sources plan, sections 2-3).

## Manifest (`htext_knesset_laws_sources.v1`)

| Field | Contents |
| --- | --- |
| `source` | the OData root, the bill filter, the document group, formats, files host, client name, `fetched_at` |
| `knessets`, `counts` | the Knessets fetched; bills, files, files pinned or failed, and per Knesset the bills with a DOC listed, with a PDF listed, with no file, and the files pinned |
| `bills[]` | `bill_id`, `knesset`, `name`, `publication_date`, `publication_series_id`, `publication_series`, `magazine_number`, `page_number`, `odata_last_updated`, and `documents[]` |
| `documents[]` | `document_bill_id`, `format`, `url`, `file` (path under `--inputs`), `bytes`, `sha256`, `odata_last_updated`, and `error` when the download failed |
| `skipped_documents[]` | document rows not fetched, with a reason: `scan_only`, `format_not_fetched`, `unexpected_path`, or `not_group_9` if the service ever returns another group |

The manifest is the build's input list: the builder reads only files whose sha256 matches it.

## Catalogue (K1–8, measured 2026-11-18)

A catalogue-only run made 166 requests, all answered 200.

| | Count |
| --- | ---: |
| Bills with a publication series | 2,146 |
| of which Sefer HaChukim (series 6071) | 2,070 |
| of which budget laws, חוקי תקציב (series 6075) | 76 |
| Group-9 files listed (DOC and PDF) | 4,228 |
| Bills with one DOC, two DOCs, no DOC | 2,060 / 3 / 83 |
| TIF scans skipped | 2,066 |

Budget laws are in their own Reshumot series, so their `MagazineNumber` is not a Sefer HaChukim booklet. The
builder maps only series 6071 to `sefer_hachukim_<n>`, and checks eval's reservations for how budget-law booklets
are named before it admits any.

## Extract

```bash
htext knesset-laws extract --manifest data/knesset_laws/sources.v1.json \
  --inputs ../work/knesset-laws/inputs --output ../work/knesset-laws/texts.v1.jsonl.gz
```

Each pinned DOC is checked against its manifest sha256 and converted to UTF-8 text with `textutil` (macOS), or
LibreOffice elsewhere. The card records the extractor and the sha256 of the texts file. PDFs are not extracted: their
text layer comes out of `pdftotext` in visual order, with mirrored brackets and margin notes mixed into the columns.
So `v1` leaves out the laws that have no DOC: all 76 budget laws and 7 others.

## Build

```bash
htext knesset-laws build --manifest data/knesset_laws/sources.v1.json \
  --texts ../work/knesset-laws/texts.v1.jsonl.gz --output out/knesset-laws-v1 \
  --lexicon-corpus <pby v2>/pby_lines_il_plain_v2.txt --lexicon-corpus <pby v2>/pby_lines_il_niqqud_v2.txt \
  --reserved ~/clones/heocr-restricted-eval/reservations/eval_reservations_v2.json \
  --leakage <dir with data/leakage/*.hashes.json and eval's fixtures>
```

1. **Booklets and reservations.**
   - A Sefer HaChukim law (series 6071) is in booklet `sefer_hachukim_<MagazineNumber>`, and a budget law (series
     6075) in `chukei_taktziv_<MagazineNumber>`. These are eval's ids (2026-11-18).
   - Ids are matched in full, never by number alone: `kovetz_hatakanot_6075` is a Kovetz HaTakanot booklet, and it
     says nothing about budget booklet 6075 or Sefer HaChukim booklet 6075.
   - A law in a reserved booklet is left out whole. A law in any other series (`series_unmapped`), or with no booklet
     number in OData (`no_booklet_number`, one K1–8 law), is held out, because its reservation cannot be checked.
2. **Paragraphs** (`htext.knesset.text`).
   - Each printed line is one line of the DOC's text.
   - Running headers (`ספר החוקים <n>` with a date), footnotes (from a line opening with `*` or with a citation such
     as `1 ס"ח`, to the next blank line) and the printer's line are dropped.
   - A line with fewer than two Hebrew letters (a number or a label alone) is a table cell. It is dropped and cuts the
     paragraph, so table rows are never glued together.
   - Paragraphs are cut at blank lines, headers and section openings. A paragraph's body runs to its last long line
     (30 characters or more) or its last line that ends a sentence. Short lines after that are a margin note, kept
     as a paragraph of its own, so a heading is never glued into running text.
3. **OCR fixes.** Each fix is counted on the card:
   - an apostrophe after a word of three or more letters, before a space or the end of the line, becomes a comma
     (`ישראל' סכום`);
   - a doubled apostrophe between letters becomes gershayim (`בה''ח`);
   - a lone one- or two-digit footnote reference after a law's year is removed;
   - the section number that opens a paragraph is removed, because the OCR often misreads its punctuation (`3,`,
     `.4 .`);
   - a word hyphenated at a line end (`הנס־` / `פחים`) is mended when the joined word is in the lexicon. Otherwise the
     break may be a compound (`במקח־אגב`) or a word the lexicon lacks, and the line is dropped
     (`unresolved_line_break`).
4. **Lines.**
   - Paragraphs are packed to the S10b length profile, as PBY prose is, and pass the PBY character rules.
   - **Lexicon filter** (plan decision 3): every word must be in a lexicon built from transcription corpora only,
     where it occurs at least twice (`--lexicon-min-count`). Hebrew numerals (`תשי"ט`, `בתשל"ג`) are checked by
     rule instead. The card reports the drop rate.
   - **Look-alike words:** a line is also dropped when one of its words becomes a word at least 20 times more common
     (seen at least 50 times) by one OCR confusion: ב/כ, ב/נ, ס/מ, ג/נ, ד/ר, ה/ח, ו/ז, ו/י, ם/ס or ס/פ. Examples are
     `זבאי` for `זכאי` and `באמור` for `כאמור`. These misreadings are rare but real words, so the lexicon alone keeps
     them. The first eye-check pass found them to be the most common error.
   - **Two-corpus rule** (heocr-lead, 2026-11-18). A look-alike is suspect only if the variant is also at least 10
     times more common in the laws being built. PBY is literary, so legal words it rarely uses (`ברשומות` beside
     `ברשימות`, `ציוד` beside `ציור`, `ערר` beside `עדר`) were dropping in build 2: the rule dropped 6.1% of lines,
     most of them correct. The laws' counts only veto a suspicion, and a word still needs the lexicon.
     Reserved laws are never read for these counts.
   - **Blind spot.** A misreading the OCR makes consistently can be common in the laws and veto its own suspicion. So
     the card counts the lines rescued this way per pair, and lists the 30 most frequent rescued words with both
     counts, for review. Build 3's review found `לסי` for `לפי` (263 occurrences, rescued against `למי`), so ס/פ
     joined the pairs.
   - **Number lists:** a comma between digits that is not a thousands separator means the OCR reversed a list
     (`75,74` for `74, 75`), and the line is dropped.
   - **Leakage** by line only. Legal formulas repeat, so word 3-grams would drop far too much; reserved booklets are
     left out whole instead.
   - Lines are deduplicated across the build and pass the hocrsyngen wrap check.
5. **Release fields.** Every law carries `source_licence` `Israel Copyright Act 2007 s.6 (not protected)`,
   `htext_release` `cc0` (null for a law with no lines), and `text_quality` `ocr_layer`, with the Knesset as credit.
   Its lines never feed a lexicon (`htext.release.lexicon_eligible`).

### Eye check

The build writes `knesset_laws_eye_check_sample.v1.jsonl`, a seeded random sample of lines (100 by default). Each
line is read against the page scan, and the results go in an `htext_eye_check.v1` file. The file holds the sample
file's sha256, who checked it, when, the method, and per line a list of errors, each with a `kind` and a count of
`words`. A line printed where the scan is damaged can be marked `unverifiable`; it is counted, but left out of the
rates. Rebuilding with `--eye-check FILE` puts the measured line and word error rates on the card. The build refuses
a check made on another sample.

**Fresh samples.** `--eye-exclude FILE` (repeatable) names earlier sample files whose lines must not be drawn
again. The published card's check is made on lines the rules were never tuned on, and the card lists the excluded
samples. A line is marked `unverifiable` only where the scan itself is damaged, never because it is hard to read. If
more than 5 in 100 are unverifiable, the sample is enlarged.

The card also counts look-alike drops per confusion pair. A line whose suspects come from two pairs counts once
under each.

**Not counted as errors:** the OCR writes the em dash as `-` and typographic quotes as `"`. Those are shape
normalisations, not misreadings.

### Outputs

| File | Contents |
| --- | --- |
| `knesset_laws_lines_plain_v1.txt` | the corpus, in the S10b format |
| `knesset_laws_line_index.v1.jsonl.gz` | per line: `sha256`, `bill_id`, `knesset`, `booklet`, `kind` (`body` or `note`), source `file` |
| `knesset_laws_rights_index.v1.jsonl.gz` | per law: the OData fields, booklet, files with sha256, `pd_israel` (`s6_official_text`), release fields, `text_source` and the reason it was `skipped` |
| `knesset_laws_excluded.v1.json` | every law with lines and its booklet: booklets to keep out of real-scan evaluation |
| `knesset_laws_eye_check_sample.v1.jsonl` | the eye-check sample |
| `corpus_card.json`, `CORPUS_CARD.md`, `SHA256SUMS` | card and checksums |

## Published build (`v2`, the default)

The pinned `v2` build is in [`data/knesset_laws/v2/`](../data/knesset_laws/v2/), with the same files as `v1`. The
corpus file and the gzipped line index are assets of the
[`knesset-laws-v2` release](https://github.com/HeOCR/htext/releases/tag/knesset-laws-v2). It was built from `e48d0bc`
with `v1`'s inputs, eval's reservations v7 and the overlap drop list (see below). HeOCR's evaluation then ran its
official check on the lines file and found 0 overlap.

| File | Lines | Laws |
| --- | ---: | ---: |
| `knesset_laws_lines_plain_v2.txt` | 223,617 | 1,972 |

`v2` is `v1` minus two kinds of line: those that share text with HeOCR's evaluation sets, and every line of the
32 laws (`skipped: eval_overlap`) where a line shares a long run with them. Every other line is the same as in `v1`.
The file meets every S10b length target.

**Eye check (inherited).** `v2` only removes lines, so its card reuses `v1`'s verdicts for the 94 of `v1`'s 100
sample lines that are still in `v2` (`--eye-check-inherited`): 9 have an error (9.6%), and 9 of 428 words are
wrong (2.1%). `v2`'s own seeded sample, `knesset_laws_eye_check_sample.v1.jsonl` in `data/knesset_laws/v2/`, has
not been checked.

`tests/test_published_knesset_laws_v2.py` checks the committed files.

## Earlier build (`v1`, superseded)

`v1` is superseded by `v2`; see the known issue below.

The pinned `v1` build is in [`data/knesset_laws/v1/`](../data/knesset_laws/v1/): the corpus card, `SHA256SUMS`, the
exclusion list, the gzipped rights index and the eye-check sample. The corpus file and the gzipped line index are
assets of the [`knesset-laws-v1` release](https://github.com/HeOCR/htext/releases/tag/knesset-laws-v1). It was built
from `b9c2923` with eval's reservations, the pby v2 plain and niqqud files as the lexicon, and the fit check.

| File | Lines | Laws |
| --- | ---: | ---: |
| `knesset_laws_lines_plain_v1.txt` | 234,821 | 2,004 |

Of the 2,146 laws in the manifest, 2,004 have lines and are `htext-cc0`; the others have `htext_release: null`
(59 eval-reserved, 82 with no DOC file, 1 with no booklet number). The file meets every S10b length target.

**Filters.** The lexicon drops 10.1% of the lines that pass the character rules, and the look-alike rule another
1.3% (3,882 lines). The two-corpus test keeps 15,143 lines whose word is a look-alike only by the PBY counts. The card
gives both thresholds, the counts per confusion pair and the 30 most frequent kept look-alikes. 24,676 printed lines
were dropped as table cells.

**Eye check.** [`eye_check/`](../data/knesset_laws/v1/eye_check/) holds the verdicts:

- `eye_check_build4.json`: the fresh sample on the card, 100 lines none of which the rules were tuned on.
  9 lines have an error (9%), and 9 of 454 words are wrong (2.0%). By kind: punctuation 5, letter 1, look-alike 1,
  digit for letter 1, garbled margin note 1. No line was unverifiable. The look-alike rate (1%) is within the 2% bar.
- `eye_sample_build1.jsonl` and `eye_check_build1_tuning.json` (**tuning**): the build-1 sample the rules were
  tuned on. 11 of its 99 verifiable lines had an error in build 1. Under the v1 rules, 76 of its lines are still in
  the corpus and 1 of them has an error (a ס/מ look-alike), 1.3%. This rate is not an unbiased estimate.

`tests/test_published_knesset_laws.py` checks the committed files. It checks that the card pins the corpus, the
manifest and the exclusion list, that every law is §6, `ocr_layer` and in `htext-cc0` exactly when it has lines,
and that the card's eye check recomputes from the committed verdict and sample and excludes the tuning sample.

## Known issue in `v1`

Some `v1` lines overlap HeOCR's evaluation text, which is reserved by page and
not by booklet, so the booklet check did not catch it. See
[`data/knesset_laws/v1/KNOWN_ISSUES.md`](../data/knesset_laws/v1/KNOWN_ISSUES.md).
`v2` fixes it.

## Overlap with evaluation text (`v2` on)

HeOCR's evaluation targets are restricted, so the overlap check runs outside the
build, on the lines of the previous build. It writes a drop list
(`htext_eval_overlap_drop.v1`) that holds only sha256s and law ids, never text:

- every line that shares a word 6-gram with any evaluation target;
- every law in which a line shares a run of 5 or more consecutive 6-grams.

```bash
htext knesset-laws build ... --corpus-version v2 --eval-overlap-drop drop.json
```

The build drops the listed lines and leaves the listed laws out
(`skipped: eval_overlap`). Their lines are still made and then discarded, so
they count in deduplication and in the corpus word counts as before. Every
other line comes out exactly as in the previous build. The card records the
drop list's sha256 and counts. A build is published only after HeOCR's
evaluation reruns its official check on the new lines file and finds 0 hits.

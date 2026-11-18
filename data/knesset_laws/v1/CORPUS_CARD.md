# Knesset laws as published (K1-8), OCR text layer

- **Release:** `htext-cc0` (CC0-1.0); source licence `Israel Copyright Act 2007 s.6 (not protected)`.
- **Text quality:** `ocr_layer`. These lines are the Knesset's OCR of the printed page, not a transcription. They never feed word lists, lexicons or dawgs.
- **Credit:** The Knesset of Israel (Knesset database, laws as published in Reshumot) (https://main.knesset.gov.il).
- **Source:** https://knesset.gov.il/Odata/ParliamentInfo.svc, Knessets 1-8, fetched 2026-11-18T08:45:40Z (manifest sha256 `9e04189f115e7452d86b99040a3491457ebec6b82913e78c198259065d1a45a1`).
- **Text extraction:** textutil (macOS 15.7.4); texts sha256 `6e656762b0671f2bdce6f8f2876eb9deedf49180259ca21d5f8695825bc57c35`.

## Laws

| | Laws |
| --- | ---: |
| In the catalogue | 2,146 |
| With lines in this build | 2,004 |
| Left out: `eval_reserved` | 59 |
| Left out: `no_booklet_number` | 1 |
| Left out: `no_doc` | 82 |

## Line quality

- **Lexicon filter:** a line is kept only when every word is in a lexicon of 584,232 words that occur at least 2 times in transcription corpora:
  - `pby_lines_il_plain_v2.txt` (sha256 `ab69e94eb4f038fc1845d4c79a9d6301df2acddf54557d7661f2bee35ae3bf9a`, 12,318,857 lines)
  - `pby_lines_il_niqqud_v2.txt` (sha256 `a149c5e5e8eb14e2862a89f45d678518de5e6ef3c3b23ed8824baf5b81ed1b28`, 1,680,295 lines)
- **Drop rate:** 31,212 of 307,877 lines that passed the character rules (10.1%) had a word outside the lexicon.
- **Table cells:** 24,676 printed lines with fewer than two Hebrew letters were dropped as table cells.
- **Look-alike words:** 3,882 more (1.3%) had a word that one OCR confusion (ב/כ, ב/נ, ס/מ, ג/נ, ד/ר, ה/ח, ו/ז, ו/י, ם/ס, ס/פ) turns into a word at least 20 times more common in the lexicon (and seen there at least 50 times) and at least 10 times more common in this corpus.
  - Rescued by the corpus counts (look-alike in the lexicon, but not in this corpus): 15,143 lines kept. By pair: ב/כ 1,025, ב/נ 2,092, ג/נ 78, ד/ר 2,866, ה/ח 846, ו/ז 887, ו/י 7,280, ם/ס 131, ס/מ 487, ס/פ 345.

Most frequent rescued look-alikes (counts: lexicon, this corpus):

| Word | Variant | Word counts | Variant counts | Lines kept |
| --- | --- | ---: | ---: | ---: |
| ברשומות | ברשימות | 8 / 1,198 | 208 / 12 | 1,131 |
| ציוד | ציור | 83 / 902 | 2,308 / 22 | 788 |
| בפסקה | נפסקה | 23 / 837 | 646 / 11 | 750 |
| מקומית | מקומות | 209 / 809 | 5,130 / 106 | 728 |
| שזר | שור | 58 / 640 | 2,258 / 1 | 606 |
| ערר | עדר | 25 / 476 | 825 / 1 | 429 |
| סביר | סבור | 37 / 412 | 2,091 / 182 | 366 |
| היטל | הוטל | 3 / 396 | 1,027 / 81 | 339 |
| הערר | העדר | 18 / 342 | 1,582 / 32 | 299 |
| מעביד | מעביר | 35 / 282 | 740 / 2 | 258 |
| חישוב | הישוב | 58 / 270 | 11,704 / 21 | 225 |
| תחולת | תחילת | 2 / 232 | 431 / 831 | 215 |
| נעברה | בעברה | 18 / 230 | 420 / 8 | 205 |
| הסעד | הסער | 37 / 221 | 1,130 / 0 | 201 |
| הצינור | הציבור | 104 / 208 | 2,333 / 443 | 188 |
| ייקרא | ויקרא | 182 / 194 | 7,700 / 2 | 174 |
| אגרה | אגדה | 34 / 194 | 2,330 / 0 | 170 |
| המדד | המרד | 2 / 187 | 1,490 / 2 | 168 |
| סבירה | סבורה | 14 / 180 | 481 / 34 | 159 |
| סדיר | סדור | 40 / 163 | 1,083 / 2 | 154 |
| קטין | קטון | 7 / 175 | 392 / 0 | 152 |
| הסיפה | הסופה | 4 / 181 | 369 / 0 | 141 |
| האישום | האישים | 2 / 159 | 565 / 3 | 138 |
| הארצית | הארצות | 233 / 148 | 5,461 / 12 | 131 |
| קבלתו | קבלתי | 80 / 133 | 2,847 / 0 | 129 |
| מסי | מפי | 246 / 134 | 13,347 / 8 | 124 |
| סבירים | סבורים | 2 / 142 | 881 / 7 | 123 |
| מצרך | מצדך | 10 / 132 | 206 / 1 | 119 |
| הליך | הלוך | 4 / 139 | 5,794 / 1 | 118 |
| הנכה | חנכה | 10 / 130 | 279 / 0 | 113 |

  - Dropped by pair: ב/כ 1,631, ב/נ 631, ג/נ 152, ד/ר 284, ה/ח 199, ו/ז 41, ו/י 439, ם/ס 104, ס/מ 93, ס/פ 430.
- **Fresh sample:** the eye-check sample excludes the lines of earlier samples the rules were tuned on: `eye_sample_build1.jsonl` (sha256 `b46e3d7a71ce34168673188939294ba5f2528105d8f46deac8289bc98d9c562d`, 100 lines).
- **Eye check:** 100 lines sampled at random, checked against the scans by htext[claude/claude-code#shay-macbook-m4]@heocr/opensource on 2026-11-18 (fresh random sample (excludes the build-1 tuning sample); each line located on its PDF page scan by OCR word boxes (full page where the crop was ambiguous) and compared character by character with the corpus line's raw text; dash and quote shapes not counted).
  - Lines checked: 100 (0 could not be verified on a damaged scan and are left out of the rates).
  - Lines with at least one error: 9 (9.0%).
  - Words wrong: 9 of 454 (1.98%).
  - `digit_for_letter`: 1
  - `letter`: 1
  - `look_alike`: 1
  - `margin_note_garbled`: 1
  - `punctuation`: 5

## Files

| File | Lines | Laws | sha256 |
| --- | ---: | ---: | --- |
| `knesset_laws_lines_plain_v1.txt` | 234,821 | 2,004 | `67c7a86bc8c8bb6b591b454900dbd5d6884099f4f2b94da937ead0505e0af01a` |

## Leakage and reservations

- **Mode:** line (word 3-grams not used: legal formulas repeat; reserved booklets are left out whole).
- Fixture: `HeOCR/heocr-restricted-eval` `dbench/synth/text_pool.json (sentences)` at `e56d79e`
- Fixture: `HeOCR/heocr-restricted-eval` `preregistration/print_scan_PS-v1_2026-11-18/PS-v1_all_text.txt` at `prereg/print`
- Fixture: `HeOCR/hocrgen` `docs/evaluation-fixtures/bidi-synthetic-corpus.txt` at `c8fb74eb5d0a`
- Fixture: `HeOCR/hocrsyngen` `src/hocrsyngen/data/synthetic/texts/hebrew_lines.txt` at `88c61af4c12c`
- Fixture: `HeOCR/hocrsyngen` `src/hocrsyngen/data/synthetic/texts/hebrew_lines_eval_v1.txt` at `88c61af4c12c`
- Fixture: `HeOCR/hocrsyngen` `src/hocrsyngen/data/synthetic/texts/hebrew_lines_niqqud_eval_v1.txt` at `88c61af4c12c`
- Fixture: `HeOCR/hocrsyngen` `src/hocrsyngen/data/synthetic/texts/hebrew_mixed_lines_eval_v1.txt` at `88c61af4c12c`
- Fixture: `HeOCR/hocrsyngen` `src/hocrsyngen/data/synthetic/texts/hebrew_typographic_lines_eval_v1.txt` at `88c61af4c12c`
- Reservations: set `print_scan_PS-v1`, file sha256 `2abce5ea8083ae7527461776bbeb70c5e4eecf3e52910e7b607bd94a68ed2a1e`, units {'pby': 4, 'reshumot': 20}
- Reservations: set `midcentury (test, dev, retired dev units; v0-v2 union)`, file sha256 `2abce5ea8083ae7527461776bbeb70c5e4eecf3e52910e7b607bd94a68ed2a1e`, units {'plenary': 60, 'reshumot': 125}
- Reservations: set `P-mod eval and holdout units (v6-v7 union, incl. exposed units)`, file sha256 `2abce5ea8083ae7527461776bbeb70c5e4eecf3e52910e7b607bd94a68ed2a1e`, units {'knesset_protocol': 7, 'plenary': 138, 'reshumot': 157}
- Reservations: set `D-bench synthetic text pool (sets A, B, C and the gate's fresh set)`, file sha256 `2abce5ea8083ae7527461776bbeb70c5e4eecf3e52910e7b607bd94a68ed2a1e`, units {'reshumot': 83}
- Reservations: set `P-hist audit2 (Hebrew Wikisource proofread pages)`, file sha256 `2abce5ea8083ae7527461776bbeb70c5e4eecf3e52910e7b607bd94a68ed2a1e`, units {'wikisource_he_proofread': 14}
- Reservations: set `line_verify scored lines (units held out whole)`, file sha256 `2abce5ea8083ae7527461776bbeb70c5e4eecf3e52910e7b607bd94a68ed2a1e`, units {'benyehuda_nli_aligned': 2, 'pby': 10, 'wikisource_he_proofread': 23}
- Reservations: set `h_eval_v1 (handwriting)`, file sha256 `2abce5ea8083ae7527461776bbeb70c5e4eecf3e52910e7b607bd94a68ed2a1e`, units {'hash': 34}

## Pipeline

| Step | Count |
| --- | ---: |
| `laws:eval_reserved` | 59 |
| `laws:no_booklet_number` | 1 |
| `laws:no_doc` | 82 |
| `laws:with_lines` | 2,004 |
| `rescued_pair:ב/כ` | 1,025 |
| `rescued_pair:ב/נ` | 2,092 |
| `rescued_pair:ג/נ` | 78 |
| `rescued_pair:ד/ר` | 2,866 |
| `rescued_pair:ה/ח` | 846 |
| `rescued_pair:ו/ז` | 887 |
| `rescued_pair:ו/י` | 7,280 |
| `rescued_pair:ם/ס` | 131 |
| `rescued_pair:ס/מ` | 487 |
| `rescued_pair:ס/פ` | 345 |
| `segments` | 310,629 |
| `segments_dropped:charset` | 1,166 |
| `segments_dropped:duplicate` | 36,274 |
| `segments_dropped:fit:archive_card:too_many_rows` | 543 |
| `segments_dropped:fit:ledger:word_too_wide` | 558 |
| `segments_dropped:leak_line` | 587 |
| `segments_dropped:lexicon` | 31,212 |
| `segments_dropped:lexicon_suspect` | 3,882 |
| `segments_dropped:medial_final_form` | 13 |
| `segments_dropped:number_list_order` | 257 |
| `segments_dropped:too_few_letters` | 633 |
| `segments_dropped:too_long` | 2 |
| `segments_dropped:unresolved_line_break` | 681 |
| `segments_rescued:lexicon_suspect` | 15,143 |
| `suspect_pair:ב/כ` | 1,631 |
| `suspect_pair:ב/נ` | 631 |
| `suspect_pair:ג/נ` | 152 |
| `suspect_pair:ד/ר` | 284 |
| `suspect_pair:ה/ח` | 199 |
| `suspect_pair:ו/ז` | 41 |
| `suspect_pair:ו/י` | 439 |
| `suspect_pair:ם/ס` | 104 |
| `suspect_pair:ס/מ` | 93 |
| `suspect_pair:ס/פ` | 430 |
| `text:line_breaks:mended` | 1,345 |
| `text:line_breaks:unresolved` | 681 |
| `text:lines_dropped:footnote` | 8,347 |
| `text:lines_dropped:page_header` | 5,819 |
| `text:lines_dropped:printer` | 30 |
| `text:lines_dropped:table_cell` | 24,676 |
| `text:ocr_fix:apostrophe_comma` | 8,182 |
| `text:ocr_fix:double_apostrophe` | 807 |
| `text:ocr_fix:footnote_reference` | 1,406 |
| `text:paragraphs:body` | 30,813 |
| `text:paragraphs:note` | 42,624 |
| `text:section_labels_removed` | 23,397 |

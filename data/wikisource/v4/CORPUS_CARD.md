# Hebrew Wikisource main-namespace text, v4

The v4 build, in `htext-by-sa`, under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Credit [Hebrew Wikisource contributors](https://he.wikisource.org). See [NOTICE](NOTICE.md) and `wikisource_rights_index.v1.jsonl.gz` for attribution by revision.

The source is the [Wikimedia dump dated 20261101](https://dumps.wikimedia.org/hewikisource/20261101/hewikisource-20261101-pages-articles.xml.bz2), SHA-256 `15a731d70154941afec2a616d538434573a4e068f94c8ea91b659ac64b833fe1`. These are unproofread transcriptions.

v4 folds two Wikisource B candidates, v4 (2 pages, 55 lines) and v5 (14 pages, 5,077 lines). All 16 pages are TRAIN CLEAN under contamination policy v2 amendment 1 (HeOCR/heocr-restricted-eval#1714). Text matches to evaluation material are tags kept in a private sidecar; they do not drop lines.

| Work | Page | Lines | Author's death (PD-Israel basis) |
| --- | ---: | ---: | ---: |
| קורא הדורות | 1720064 | 31 | ancient |
| אל הציפור (ביאליק) | 3736 | 19 | 1934 |
| מאמר הדור | 171517 | 684 | 1935 |
| דברי אגרת (מענדל שטיינהארט) | 257461 | 3,329 | 1825 |
| מעשה שמשון | 268108 | 25 | 1944 |

| File | Lines |
| --- | ---: |
| `wikisource_plain_v4.txt` | 4,088 |
| `wikisource_niqqud_v4.txt` | 0 |

Corpus-quality steps (not contamination):
- 11 pages (741 lines) are root or landing pages: tables of contents, title stubs, modern editorial introductions, or text with holes where wiki links were removed. One of them, חיי מוהר"ן, also carries a third-party permission notice. Reasons per page are in `recipe/exclude_pages.json`.
- 303 lines already in a live htext release (Wikisource v1–v3, PBY v1.1/v2.1/v3.1, Sefaria, Tanakh v1.1, Tsel HaOlam, Knesset laws v2) or in the pending Sefaria v3 and Gutenberg tranche were dropped. The match is exact after removing marks.
- In-corpus duplicates: 0.

Recipe: `recipe/fold.py` with `recipe/exclude_pages.json`. Inputs and hashes are in `corpus_card.json`.

No paired scans are included. Spacing before punctuation in older prints is kept as transcribed.

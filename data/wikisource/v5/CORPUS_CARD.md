# htext Wikisource B v5: Hebrew Wikisource main-namespace training lines

`htext-by-sa`, [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Credit Hebrew Wikisource contributors; see NOTICE.md and the rights index for attribution by revision.

130 public-domain works from the [Wikimedia dump of 2026-11-01](https://dumps.wikimedia.org/hewikisource/20261101/hewikisource-20261101-pages-articles.xml.bz2) (SHA-256 `15a731d7…`), unproofread transcriptions: rabbinic, Hasidic, kabbalistic and modern Hebrew works whose authors all died by 1955 (works.v3.json).

| File | Lines |
| --- | ---: |
| `wikisource_plain_v5.txt` | 3,292,731 |
| `wikisource_niqqud_v5.txt` | 410,681 |

- **De-duplication:** 357,054 lines already in a published htext release (PBY included) and 7,143 in-corpus duplicates removed; exact match after removing marks.
- **Near duplicates:** About 39% of this corpus's content (sampled 4-word phrases, census estimate) also appears in Sefaria or other htext releases, mostly Talmud commentaries (Rishonim) and halakhic works; 36 of the 130 works overlap by 50% or more. Exact duplicate lines are removed, but the same text with different line breaks or edition wording is kept on purpose (lead ruling, 2026-11-27).
- **Evaluation hygiene:** HeOCR's CLEAN check kept every line (record #1896); 1,113 lines share text with evaluation material and are tagged in a private sidecar, reported both ways. A work-level screen against the evaluation reservations found no reserved work and no transclusion of a reserved scan.
- **Rights:** translations only with a proven translator; other editions of evaluation hold-out books are left out.

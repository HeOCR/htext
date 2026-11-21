# Knesset plenary records v1

- **Release** `knesset-plenary-v1`, in `htext-cc0` (CC0-1.0). The source is an official text under section 6 of the Israel Copyright Act 2007.
- **Credit** The Knesset of Israel, Knesset database, plenary records and Divrei ha-Knesset. [Source](https://main.knesset.gov.il)
- **Scope** K1–8 through 1975 use the OCR layer of the printed record. K13–25 use born-digital transcriptions. Keep the OCR-layer file out of word lists, lexicons and DAWGs. [Builder and pinned fetch](../../../docs/knesset_plenary.md)

## Files

| File | Text quality | Lines | Sittings | Bytes | SHA-256 |
| --- | --- | ---: | ---: | ---: | --- |
| `knesset_plenary_lines_ocr_v1.txt` | `ocr_layer` | 10,521,382 | 3,513 | 494,392,084 | `04671359681dd633d05fe5aae3aeb3b8e474719b2c23b33a7ece856e81bd33c9` |
| `knesset_plenary_lines_transcription_v1.txt` | `transcription` | 20,796,832 | 3,331 | 992,225,164 | `85d24964ef03a22db8c2971ddf07069bc12f30190fdca86296c20ce94fbebeda` |

The release assets include the line and rights indexes. The line index provides source and line provenance. The rights index identifies the source document and records its rights per sitting. Verify the release assets against [SHA256SUMS](SHA256SUMS).

## Private-name filtering

The `plenary_private_names_v1` gate used a Hebrew named-entity tagger, public-official roster and contextual rules before any candidate line entered a corpus file. 848,303 distinct lines were dropped at this stage. A line can be counted under more than one reason.

| Gate reason | Lines flagged under this reason |
| --- | ---: |
| `not_public` · detected name classified as private | 745,240 |
| `surname_namesake` · detected name shares a public official's surname | 134,660 |
| `empty_mention` · detected span lacks usable name tokens | 2,068 |

See [the machine-readable card](corpus_card.json) for per-Knesset privacy counts. The filter reduces private-name exposure and its output depends on the tagger and rules.

## Source and overlap checks

The fetch excluded 109 reserved sittings and 2 sittings without a sitting number. The release contains lines from 6,844 sittings. The final line-only pass removed 24 OCR lines and 18 transcription lines across 41 sittings. The independent release check on 2026-11-21 found **zero shared six-word sequences** across 16 evaluation pools on the two exact text files above.

I collated 100 retained K1–8 OCR sample lines against the pinned PDF scans. 4 lines contained an error, with 4 word substitutions in 471 checked words. This is a source text quality check.

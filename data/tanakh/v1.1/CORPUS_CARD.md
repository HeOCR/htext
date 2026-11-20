# htext tanakh-v1.1

Public-domain Westminster Leningrad Codex text, cut into plain and pointed Hebrew lines.

The text files are filtered derivatives of [the original tanakh-v1 build](https://github.com/HeOCR/htext/blob/main/data/tanakh/v1/corpus_card.json).
HeOCR's corrected independent check found zero shared 6-grams across 16 evaluation pools for these exact files.
This check describes text overlap, not OCR performance.

| Text file | Lines | Bytes |
| --- | ---: | ---: |
| `tanakh_lines_plain_v1.txt` | 57,637 | 2,656,873 |
| `tanakh_lines_niqqud_v1.txt` | 57,683 | 4,589,508 |

Each text file has a matching line index. [SHA256SUMS](SHA256SUMS) pins both.
Download the tagged revision on [Hugging Face](https://huggingface.co/datasets/HeOCR/htext-tanakh/tree/tanakh-v1.1).
Credit [Westminster Leningrad Codex (public domain), via the Open Scriptures Hebrew Bible](https://github.com/openscriptures/morphhb). The release is CC0 1.0.

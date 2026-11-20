# htext pby-v1.1

Public-domain Hebrew literature from Project Ben-Yehuda, cut into plain and pointed lines.

The text files are filtered derivatives of [the original pby-v1 build](https://github.com/HeOCR/htext/blob/main/data/pby/v1/corpus_card.json).
HeOCR's corrected independent check found zero shared 6-grams across 16 evaluation pools for these exact files.
This check describes text overlap, not OCR performance.

| Text file | Lines | Bytes |
| --- | ---: | ---: |
| `pby_lines_il_plain_v1.txt` | 1,619,558 | 74,004,102 |
| `pby_lines_il_niqqud_v1.txt` | 400,665 | 30,725,433 |
| `pby_lines_il_us_plain_v1.txt` | 68,086 | 3,167,355 |
| `pby_lines_il_us_niqqud_v1.txt` | 9,991 | 735,651 |

Each text file has a matching line index. [SHA256SUMS](SHA256SUMS) pins both.
Download the tagged revision on [Hugging Face](https://huggingface.co/datasets/HeOCR/htext-pby/tree/pby-v1.1).
Credit [Project Ben-Yehuda volunteers](https://benyehuda.org). The release is CC0 1.0.

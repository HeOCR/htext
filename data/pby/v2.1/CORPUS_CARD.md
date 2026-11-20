# htext pby-v2.1

Public-domain Hebrew literature from Project Ben-Yehuda, cut into plain and pointed lines.

The text files are filtered derivatives of [the original pby-v2 build](https://github.com/HeOCR/htext/blob/main/data/pby/v2/corpus_card.json).
HeOCR's corrected independent check found zero shared 6-grams across 16 evaluation pools for these exact files.
This check describes text overlap, not OCR performance.

| Text file | Lines | Bytes |
| --- | ---: | ---: |
| `pby_lines_il_plain_v2.txt` | 11,937,313 | 543,360,350 |
| `pby_lines_il_niqqud_v2.txt` | 1,672,686 | 119,280,915 |
| `pby_lines_il_us_plain_v2.txt` | 371,068 | 17,243,627 |
| `pby_lines_il_us_niqqud_v2.txt` | 18,557 | 1,322,452 |

Each text file has a matching line index. [SHA256SUMS](SHA256SUMS) pins both.
Download the tagged revision on [Hugging Face](https://huggingface.co/datasets/HeOCR/htext-pby/tree/pby-v2.1).
Credit [Project Ben-Yehuda volunteers](https://benyehuda.org). The release is CC0 1.0.

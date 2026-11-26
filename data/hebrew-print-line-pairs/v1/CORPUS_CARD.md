---
license: cc-by-sa-4.0
language:
- he
task_categories:
- image-to-text
pretty_name: Hebrew print line pairs
size_categories:
- 10K<n<100K
configs:
- config_name: default
  data_files:
  - split: train
    path: data/*.parquet
---

# Hebrew print line pairs (v1)

43,435 printed Hebrew text lines from 42 public-domain books (16th to 20th century). Each line is an image crop from
the book's scan, with the proofread transcription of exactly that line. They are training data for Hebrew OCR.
They are built by HeOCR from Hebrew Wikisource's proofread pages and their scans, using Rivok's line-pairing method.

## How the pairs are made
- **Method:** Rivok's (RivoksLab/tesseract-heb-rivok, `training/v2/lines`, Apache-2.0); his aligner and label rules
  are ported with credit.
- **Line cutting:** Tesseract with Rivok's heb_rivok 2.0 model cuts each scanned page into lines. The OCR is used only
  for the line boxes and as an anchor.
- **Alignment:** the page's proofread Wikisource text is aligned word by word to the OCR (Needleman–Wunsch) and cut at
  the OCR's line breaks.
- **What is kept:** a line whose two ends are anchored, whose OCR-vs-label character error rate (without niqqud) is at
  most 0.25, and which passes the label rules. The rules drop lines whose transcription departs from the print:
  - expanded abbreviations;
  - editorial or partial niqqud;
  - plene spelling;
  - editors' notes;
  - cantillation;
  - missing printed digits;
  - wiki markup residue;
  - boxes holding two printed lines.
- **Label:** always the human-proofread text, never the OCR.

## Fields
`image` (PNG crop), `text` (label), `ocr_text`, `cer_nomarks`, `bbox`, `scan_file`, `scan_sha1`, `scan_url`,
`scan_page`, `image_sha256`, `wikisource_page`, `wikisource_page_id`, `wikisource_revid`, `wikisource_url`,
`quality` (3 proofread, 4 validated), `tags`, `image_licence_basis`, `image_licence`, `image_licence_page`,
`text_licence`.

## Evaluation hygiene
- **Exclusion:** HeOCR's exact evaluation test pages and development pages are excluded, page by page; no crop comes
  from them (checked by HeOCR's independent CLEAN). Other pages of the same books may be included.
- **Tags kept private:** which rows share a book with an evaluation set is kept in a private sidecar, so evaluations
  can report results both ways without naming the private sets here.

## Quality
- **Label noise:** a manual check of 120 random lines after the final rules found about 3% label defects. Most are
  text lost inside Wikisource templates (a citation or folio reference) or typos in Wikisource itself.
- **Fit:** treat the labels as high quality but not perfect.

## Licences and credit
- **Text:** Hebrew Wikisource contributors, CC BY-SA 4.0. Each line's `wikisource_url` points to the exact revision;
  its history lists the authors.
- **Images:** crops of scans that are in the public domain in Israel (`image_licence_basis = pd_il`). Each line links
  its scan's file description page.
- **Credit:** Rivok Labs (the line-pairing method and code), Hebrew Wikisource and its proofreaders, Wikimedia Commons
  and the scans' sources.
- **Dataset licence:** CC BY-SA 4.0.

Built by HeOCR (https://github.com/HeOCR). Code: https://github.com/HeOCR/htext (`htext.linepairs`).

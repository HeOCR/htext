# Real line pairs by Rivok's method (`htext.linepairs`)

Image and text line pairs for Hebrew OCR training: a scan's line crop plus the human-proofread text of that line.
The method, aligner and label rules are Rivok's (RivoksLab/tesseract-heb-rivok, Apache-2.0; see NOTICE).

- `wikisource`: Hebrew Wikisource Index/Page books (proofread quality 3 or 4) and their scans.
  - Page text comes from the Wikimedia dump's wikitext; robots.txt disallows the API. Labelled-section transclusions are
    resolved from the same dump.
  - Scans are original files from upload.wikimedia.org.
  - Incremental: per-page receipts, atomic writes, and a resumed run gives byte-identical output.
- `book`: whole-book alignment. Unique 4-gram anchors plus a longest increasing chain give each scanned page its slice of
  a whole-edition transcription; Rivok's page aligner then runs on the slice. Checked against page-split truth on two
  books: 95–99% of the lines found, labels ≥99.7% identical.
- `editions`: the book-level pilot over edition pairs (scan + PBY, Sefaria or Wikisource transcription of the same
  edition) from a heocr-ops manifest.
- `release`: Parquet shards with per-line provenance, tags and an image-licence basis.
  - Public shards: pd_il / cc0 / cc_by / cc_by_sa. Everything else goes to internal (training-only) shards.
  - Exclusion is page-only: eval's exact test pages and DEV pages.

HeOCR rules on top of Rivok's (each found in a visual QA sample):
- Latin-script OCR lines stay out of the alignment, because they are bilingual pages.
- Hebrew section tags, in-text headings and horizontal rules are stripped.
- A label with markup residue is dropped.
- A pointed print whose label is only partly pointed is dropped.
- A label missing printed digits is dropped.
- A box with two comparable ink bands (two printed lines) is dropped.

## Edition-pair manifests (`python -m htext.linepairs.editions`)
A manifest is JSON with `pairs`. Each pair needs:
- `id`: unique; it is also hashed into the work folder name.
- `transcription`: `url` and `sha256`, plus a `format`. `JSON` is a Sefaria named-version tree, `HTML` a Wikisource
  snapshot, `Word` a `.doc` read with macOS `textutil`, and anything else plain UTF-8 text. When `format` is absent,
  `source: "Sefaria"` means JSON.
- `scan` and `scope`, in one of three shapes:
  - per-page images: `scope.bound_native_pages`, a list of `{native_leaf, url, sha256}` (for example IA JP2 leaves).
    `scope.native_leaves_in_reading_order` sets the order;
  - a PDF, `scan.url` plus `scan.sha256` (or `scan.sha1`), with either `scope.pdf_ordinals` (an explicit list),
    `scope.pdf_ordinal_ranges_inclusive`, or the pilot field `pilot_pdf_ordinals_in_reading_order`.
- Optional:
  - `exact_test_pages_excluded`: page numbers never processed (page-only exclusion);
  - `columns: "rtl2"`: two-column Hebrew pages. Full-width lines split the page into bands; each band is read right
    column first, then left.

Run with `--work <dir> --tessdata <dir with heb_rivok.traineddata> --jobs N`. `--skip-prefix` skips pairs by id prefix,
for example multi-commentary pages. Every input is checked against its pinned digest, and pages are OCR'd in parallel
and cached. Each page writes an atomic receipt, so a rerun resumes. The per-pair `report.json` gives pages, pages
sliced, anchors, OCR lines, kept lines and drop reasons.

Knesset plenary text must also pass the privacy gate (hocrgen `plenary_private_names_v1`) before intake. A line that
names a private person is dropped whole.

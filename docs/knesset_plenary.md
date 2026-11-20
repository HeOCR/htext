# Knesset plenary records (`knesset-plenary`)

The plenary protocols of the Knesset ("דברי הכנסת") are official texts that the
Israeli Copyright Act does not protect (section 6), so they go into
`htext-cc0`. This page covers the fetch and the builder. The published build
comes in a later PR.

## Scope

The scope follows decision 1 of the [sources plan](sources_plan.md) (heocr-lead,
2026-11-18). htext uses hocrgen's publishability flags as they are, with no
judgment of its own:

| Knessets | Sittings | Text |
| --- | --- | --- |
| K1–8 | those that started before 1976-01-01 | the OCR text layer of the scans (`text_quality: ocr_layer`) |
| K13–25 | all | born-digital DOC/DOCX protocols (`text_quality: transcription`) |

K8 sittings from 1976, and all of K9–12, are out because no hocrgen flag covers
them. Committee protocols are out of every period.

## Fetching

```bash
python scripts/fetch_knesset_plenary.py \
  --reserved <eval_reservations_v4.json from HeOCR's evaluation> \
  --inputs ../work/knesset-plenary/inputs \
  --manifest ../work/knesset-plenary/sources.v1.json
```

The fetcher runs once per pin, outside the build. It uses the same polite client
as the laws fetcher: one request at a time, at least a second apart, a generic
client name, a log of every request, and downloads outside git. A rerun reuses
the files already on disk.

1. `KNS_PlenumSession` lists the sittings of the Knessets in scope, and the
   date rule is applied.
2. **Reserved sittings.** HeOCR's evaluation reserves some plenary sittings as
   unit ids `K<knesset>_<sitting number>`. The fetcher drops every sitting
   whose unit id is reserved **before any document is listed or file
   fetched**, so their text never reaches disk. If two sittings share a unit
   id, both are dropped. A sitting with no sitting number has no unit id, so
   its reservation cannot be checked and it is held out too. `--reserved` is required, and the fetcher refuses to
   run on a file with no plenary units.
3. `KNS_DocumentPlenumSession`, group 28 ("דברי הכנסת", files named
   `<k>_ptm_<n>`), gives each remaining sitting's protocol. The DOC or DOCX is
   fetched for every sitting. The PDF is fetched only for a seeded sample of
   K1–8 sittings (`--eye-check-pdfs`, default 100), for the eye check against
   the scan. Scans (PIC), video and other groups are not fetched.

**Why K1–8 needs only the DOC.** For K1–8, the DOC holds the same OCR text as
the PDF's text layer. A probe of three sittings (K1 1949, K4 1960, K8 1974)
found every Hebrew word of each DOC in its PDF.

## Manifest (`htext_knesset_plenary_sources.v1`)

- **`source`:** the OData service, entities, filter, scope, document group and
  client name, and the fetch time.
- **`eval_reservations`:** each reservations file, by set, unit counts and
  sha256.
- **`counts.selection`:** sittings listed, out of scope, in scope, held out
  for having no unit id, reserved unit ids, reserved sittings, kept, and
  eye-check sittings. The manifest
  records how many sittings were reserved, never which.
- **`sessions`:** one row per kept sitting, with its OData fields and its
  files (URL, local path, size, sha256).
- **`skipped_documents`:** the group-28 rows of kept sittings that were not
  fetched, with a reason each.

## Pinned fetch (2026-11-19)

The fetch of 2026-11-19 is pinned in
[`data/knesset_plenary/sources.v1.json`](../data/knesset_plenary/sources.v1.json)
(sha256 `fa8524f5297ffa0765b37705c112b638451353460435b4db7dc234d352806ee4`):
6,846 sittings, 6,947 files, all with size and sha256, no failures. The
downloads (about 3.3 GB) stay outside git. A rerun of the fetcher with this
manifest's reservations refetches them, and any file the Knesset has changed
since will show up as a sha256 mismatch.

## Measured size (2026-11-19)

| Files | Count | Size |
| --- | ---: | ---: |
| K1–8 DOC | 3,545 | about 1.6 GB |
| K13–25 DOC/DOCX | 3,413 | about 1.9 GB |
| K1–8 PDF, eye-check sample | 100 | about 0.2 GB |

The scope is 6,957 sittings. Eval's reservations v4 reserve 109 of them, and
two K18 sittings have no sitting number, leaving 6,846. At one request a second, the fetch takes about two hours.

## Building

The design is heocr-lead's of 2026-11-20. It produces one release, `knesset-plenary-v1`, with two files, each with its
own `text_quality`:

| File | Knessets | Text quality |
| --- | --- | --- |
| `knesset_plenary_lines_ocr_v1.txt` | K1–8 | `ocr_layer`: the Knesset's OCR of the printed record. Its lines never feed word lists, lexicons or dawgs |
| `knesset_plenary_lines_transcription_v1.txt` | K13–25 | `transcription`: the born-digital protocols |

The builder needs the `plenary` extra (`pip install -e ".[plenary]"`), which pins hocrgen. hocrgen supplies two
things: the K13–25 paragraph rules and the private-names gate. The tagger runs in its own venv.

```bash
htext knesset-plenary extract --manifest data/knesset_plenary/sources.v1.json \
  --inputs ../work/knesset-plenary/inputs --output ../work/knesset-plenary/texts.v1.jsonl.gz
htext knesset-plenary candidates --manifest data/knesset_plenary/sources.v1.json \
  --texts ../work/knesset-plenary/texts.v1.jsonl.gz --work ../work/knesset-plenary/work \
  --lexicon-corpus pby_lines_il_plain_v2.txt --lexicon-corpus pby_lines_il_niqqud_v2.txt
HF_HUB_OFFLINE=1 ~/.venvs/heocr-ner/bin/python -I <hocrgen>/src/hocrgen/privacy/ner_stream.py \
  ../work/knesset-plenary/work/ner_input.jsonl ../work/knesset-plenary/work/spans.jsonl
htext knesset-plenary build --manifest data/knesset_plenary/sources.v1.json --work ../work/knesset-plenary/work \
  --spans ../work/knesset-plenary/work/spans.jsonl --output out/knesset-plenary-v1 \
  --reserved <eval_reservations_v7.json> \
  --lexicon-corpus pby_lines_il_plain_v2.txt --lexicon-corpus pby_lines_il_niqqud_v2.txt \
  [--eval-overlap-drop drop.json] [--eye-check eye_check.json]
```

1. **Extract.** textutil reads every pinned DOC or DOCX, the same as for the laws. LibreOffice's text export loses the
   OCR text of the K1–8 files, and textutil keeps the K24–25 speaker markers.
2. **Candidates.** Each sitting's paragraphs are cut into lines by the S10b length profile and the PBY character
   rules.
   - **K1–8:** paragraphs are rebuilt from the printed lines. Footnotes (`•)`) and lines with no text (page and
     column numbers) are dropped. Words hyphenated at a line end are mended against the transcription lexicon;
     otherwise the line is dropped. Speaker headings (a short line ending in `:`) are paragraphs of their own.
   - **K13–25:** hocrgen's plenary rules apply. The markers are removed and prove a heading, and the front matter
     (masthead, table of contents, agenda) goes.
   - This step writes the candidate lines and each sitting's tagger stream. Both are private work files: they
     still hold every line.
3. **Tag.** `dicta-il/dictabert-ner` runs over each stream, offline. It is a filter only.
4. **Build.**
   - **Privacy:** the gate `plenary_private_names_v1` runs per sitting before anything is written. A line that
     names a private person is dropped whole. A sitting the tagger never saw is dropped whole too.
     - In K13–25, the markers prove speaker headings. K1–8 has only the roster shapes.
     - `refuse_ungated_plenary_lines` checks every kept row.
   - **K1–8 filters:** the lexicon filter and the look-alike rule, as for the laws. The lexicon is built from
     transcription entries only: the corpora given, plus the gated K13–25 lines.
   - **Reservations:** the build refuses a manifest that holds a reserved sitting. It checks the written corpus
     again.
   - **Overlap with evaluation text:** a drop list (`htext_eval_overlap_drop.v1`, with sitting ids as units) is
     made outside the build, against HeOCR's evaluation targets. It drops lines and whole sittings. The card gives
     a count of the targets only.
   - Exact duplicates are dropped across the corpus.
   - **Eye check:** the sample is drawn from the K1–8 sittings whose PDF was fetched for it.

`tests/test_knesset_plenary.py` exercises each step on invented text with a fake roster and a fake tagger. CI runs
it in the `plenary` job.


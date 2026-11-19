# Knesset plenary records (`knesset-plenary`)

The plenary protocols of the Knesset ("דברי הכנסת") are official texts that the
Israeli Copyright Act does not protect (section 6), so they go into
`htext-cc0`. This page covers the fetch. The builder and the published build
come in later PRs.

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

## Measured size (2026-11-19)

| Files | Count | Size |
| --- | ---: | ---: |
| K1–8 DOC | 3,545 | about 1.6 GB |
| K13–25 DOC/DOCX | 3,413 | about 1.9 GB |
| K1–8 PDF, eye-check sample | 100 | about 0.2 GB |

The scope is 6,957 sittings. Eval's reservations v4 reserve 109 of them, and
two K18 sittings have no sitting number, leaving 6,846. At one request a second, the fetch takes about two hours.

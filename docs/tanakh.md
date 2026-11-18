# Tanakh (`tanakh`)

The Hebrew Bible, as the Westminster Leningrad Codex (WLC) gives it, cut into lines in two forms: pointed and plain.
It is source 4 of the [sources plan](sources_plan.md), and part of `htext-cc0`.

## Source and rights

- **Source:** [`openscriptures/morphhb`](https://github.com/openscriptures/morphhb), the OSIS files in `wlc/`, at
  the commit pinned in `htext.tanakh.WLC_COMMIT`. The files carry WLC 4.20.
- **Not UXLC.** tanach.us's Unicode/XML Leningrad Codex was the plan's first choice. Its robots file disallows
  automated fetching, so htext does not fetch it (heocr-lead, 2026-11-18). The WLC is the same codex; UXLC is its
  corrected successor, so a few readings differ.
- **Public domain.** The Leningrad Codex is about a thousand years old, and the WLC text is in the public domain. OSHB's
  README says the WLC text "remains in the Public Domain", and every file's `<work osisWork="WLC">` record says
  `Public Domain`. Every book carries the source licence `Public Domain`, `htext_release` `cc0` and `text_quality`
  `transcription`. Both `pd_israel` and `pd_us` are true, on the basis `ancient_text_public_domain_edition`.
- **What is not used:** OSHB's `lemma`, `morph` and `n` attributes, which are CC BY 4.0, and its `/` morpheme
  dividers. The builder reads only each word's letters and marks. Marginal readings (qere), alternative accents and
  editorial notes, which sit in `<note>` elements, are skipped too.
- **Credit:** "Westminster Leningrad Codex (public domain), via the Open Scriptures Hebrew Bible".

## Fetch

One download, outside the build. GitHub serves the tarball of the pinned commit:

```bash
curl -L -o morphhb.tar.gz https://codeload.github.com/openscriptures/morphhb/tar.gz/<WLC_COMMIT>
mkdir morphhb && tar -xzf morphhb.tar.gz -C morphhb --strip-components=1
```

## Build

```bash
htext tanakh build --wlc morphhb/wlc --source-commit <WLC_COMMIT> --output out/tanakh-v1 \
  --reserved <eval_reservations_v2.json> --leakage <dir with *.hashes.json>
```

The build reads no network and refuses a `--source-commit` other than the pinned one.

Per verse:

1. **Words.** The written text (ketiv). Maqaf joins two words into one token. Sof pasuq, paseq, the reversed nun and
   the open and closed section markers (pe, samekh) are removed. Large, small and suspended letters stay as letters.
2. **Two forms.** `niqqud` keeps the S10b vowel points, removing cantillation (U+0591–U+05AF), meteg, rafe and the
   upper and lower dots. `plain` removes every mark.
3. **Lines.** Each verse is packed to the S10b length profile at word boundaries, as PBY prose is. No line crosses a
   verse, and both forms are cut at the same words.
4. **Checks.** Each line passes the PBY character rules and the leakage check (line and word 3-grams, in either
   form), and both forms pass the hocrsyngen wrap check. A line dropped in one form is dropped in the other.
   Deduplication is per file. A book that eval reserves (source `tanakh`, unit the OSIS book name) is left out whole.

**Biblical quotations.** Verses are quoted in many printed Hebrew pages, HeOCR's evaluation pages among them. The
leakage check drops lines that match evaluation text, but run the training-time overlap check (CLEAN) against your
evaluation set before training on this corpus. The card says so too.

## Outputs

| File | Contents |
| --- | --- |
| `tanakh_lines_niqqud_v1.txt` | the pointed form, in the S10b format |
| `tanakh_lines_plain_v1.txt` | the plain form |
| `tanakh_line_index.v1.jsonl.gz` | per line: `subset`, `sha256`, `ref` (`Book.chapter.verse`), `part` and `parts` |
| `tanakh_rights_index.v1.jsonl.gz` | per book: OSIS name, Hebrew name, section, verse count, source file and sha256, rights and release fields |
| `corpus_card.json`, `CORPUS_CARD.md`, `SHA256SUMS` | card and checksums |

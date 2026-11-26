# Sefaria v3: open-licence Hebrew versions at scale

v1 and v2 were hand-picked editions (7 works). v3 takes every Sefaria work that has a Hebrew version under an open
licence and passes the rights rule, in the three htext releases (decision 0022).

## Acquisition
- **Bulk export first.** Version files come from Sefaria's public bulk export (`gs://sefaria-export`, listed by
  `Sefaria/Sefaria-Export` `books.json` at a pinned commit). That is one reproducible fetch instead of thousands of API calls.
- **API only for gaps.** Versions the export lacks come from the v3 texts API, at 1 request/s with a generic UA (robots.txt
  allows `/api`). Each API reply is kept raw, and rewritten into the export's file shape with the raw reply's sha256 recorded.
- **Metadata.** Authors and composition dates come from the export's `schemas/`. Author death years come from Sefaria's
  topic pages (API).

## Rights rule
- **Licence grants:** a version labelled CC0, CC-BY or CC-BY-SA needs nothing more. NC, ND, copyright and unknown labels
  are refused (`htext.release`).
- **"Public Domain" labels** also need every author dead by 1955 (Israel: 70 years after death, so ≤ 1955 for 2026). Where
  the death year is missing, the author must be born by 1860 or belong to a pre-modern era (Tannaim, Amoraim, Geonim, Rishonim).
- **Anonymous works** need a pre-modern era or a composition date by 1860.
- **Everything else** is out, and the card lists it with the reason.

## Selection
- **Main version:** the most permissive lane first (cc0, then by, then by-sa), then Sefaria's priority.
- **Pointed version:** added when the main version is unpointed and another passing version is pointed (at least 0.25
  pointing marks per letter).
- **Ownership:** families shared with Wikisource are owned by htext-sefaria (lead ruling 2026-11-25). Works opensrc owns
  in Wikisource B are left out (status `out:owned_by_opensrc`).

## Text and lines
- **Segments:** walked in order. Footnotes (`footnote-marker` and `footnote` elements) are removed together with their
  text, and other markup is dropped.
- **Lines:** cut by the S10b length profile and the PBY character and niqqud rules, as in PBY and Gutenberg.
- **Aramaic-heavy works:** Bavli and Yerushalmi tractates (not their commentaries), Targum and Zohar go to the `*_arc`
  files. Leave those files out for a Hebrew-only fit.
- **Tags, not drops** (contamination policy v2, amendment 1): eval-reserved works and protected-text matches are tagged
  in the line index.
- **Removed:** only in-corpus duplicates and lines already in other htext releases (`--dedup-against`), as a
  corpus-quality step.

## Outputs (per lane)
- **Lines:** `sefaria_<lane>_lines_{plain,niqqud}_{he,arc}_v3.txt`.
- **Line index:** `sefaria_line_index.v3.tsv.gz`, with columns subset, lang, work, version, segment and tags.
- **Rights index:** `sefaria_rights_index.v3.jsonl.gz`, one row per version with its licence, credit, rights basis and sha256.
- **Card and checksums:** `corpus_card.json`, `CORPUS_CARD.md` and `SHA256SUMS`.

```
htext sefaria build --sources data/sefaria/v3/sources.v3.json --inputs <export dir> --output out/sefaria-v3-cc0 \
  --lane cc0 --reserved <eval_reservations.json> --dedup-against <other htext lines> --length-profile <S10b lines>
```

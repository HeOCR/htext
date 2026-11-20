# Wikisource main-namespace works: design note (option B)

Status: proposal for heocr-lead and the maintainer. Nothing in it is built or published.
Author: `htext[claude/claude-code#shay-macbook-m4]@heocr/opensource`, 2026-11-20.

**2026-11-20 decision and implementation status.** The lead approved option B and
Shay approved including Open Law Book laws. Namespace 106 and OCR-converted
articles remain excluded. The initial [works list](../data/wikisource/works.v1.json)
records exact root titles and the source revision for each rights review. The
initial roots did not occur in the live Wikisource backlink and transclusion
metadata for the reserved Indexes. The builder must still apply the pinned
dump's whole-work reservation mapping. It must also exclude reserved booklets
and deduplicate laws against knesset-laws-v2, in addition to line decontamination.

## Why this note

`htext wikisource build` ([`wikisource.md`](wikisource.md)) reads only ProofreadPage revisions (namespace 104). It takes
a Page only when the Page itself carries an explicit public-domain or free-licence marking. Lead's pre-approved fallback
was to take that marking from the same scan's Index instead. A measuring build of the pinned 2026-11-01 dump
(`data/wikisource/sources.v1.json`) produced **no lines**:

| Page namespace (104) | Records |
| --- | ---: |
| All Page records | 6,835 |
| Excluded by eval reservations: all 51 v7 units resolve to Indexes, which pulls in 37 works and 55 scan families | 4,947 |
| Not proofread (quality below 3) | 1,199 |
| Redirects | 11 |
| Left, all without an explicit marking on the Page | **678** |

The 133 Index pages carry `מחבר`, `כותרת`, `שנה`, `מוציא לאור`, `מקור`, `דפים`, `הערות`, `מתרגם`, `עורך` and
similar fields. **None carries a licence or PD field**, so the fallback also gives nothing. heocr-lead parked
Wikisource `v1` on 2026-11-20 (option C) and asked for this note.

## Where the text is

All figures are counts from the same dump. Character counts are of the raw wikitext, before any filter.

| Main namespace (0) and namespace 106 | Pages | Characters (M) |
| --- | ---: | ---: |
| Articles that are not redirects | 243,663 | 996.7 |
| Articles with an explicit PD template | 2 | 0.6 |
| Articles linking to any author page (namespace 108) | 604 | 4.2 |
| ...whose linked authors all died by 1955 (death year from the author page) | 59 | 0.6 |
| Articles whose work root names a pre-modern classic (Talmud, Mishna, Midrash, Rambam, Tur and Shulchan Aruch, Rishonim, Tanakh with commentaries, responsa ...) | 92,324 | 363.5 |
| Laws (category `בוט חוקים`, or roots starting `חוק`, `פקודת`, `תקנות`): the Open Law Book | 6,191 | 103.8 |
| Bavli and Mishneh Torah roots (the overlap with the planned `sefaria-by-sa`) | 17,125 | 11.3 |
| Namespace 106: Wikisource's own commentary, written by contributors | 32,766 | 395.5 |

Author pages: 784. A death year could be read from 315 of them, and 84 died in or before 1955. Almost no article links
to an author page: **99.75% of the articles link to none**. So the PBY rule ("every creator died at least 71 years
before the build year") cannot be applied through Wikisource's own author links. The few that qualify hold
0.6M characters.

Some articles carry the templates `המרת או.סי.אר` (4,819, OCR conversion) or `הוסב אוטומטית מהקלדה` (10,103,
converted automatically from typed text). They mark text whose quality is not a human transcription.

## Proposal

The volume is in the **pre-modern classics**. Their public-domain status follows from their age, not from an author
page. The proposal reuses PBY's offline, reviewed-pin approach:

1. **A reviewed works list** (`data/wikisource/works.v1.json`), committed like PBY's `creators.json`. One row per
   work root, with:
   - the root title;
   - the work, its author or authors, and their death year or era;
   - a `pd_israel` basis: `ancient` for a work whose last author died before 1800, or a death year at least 71 years
     before the build year;
   - a reviewer note.

   Only roots on the list enter, and every subpage of a root inherits its row. The list starts with the large rabbinic
   corpora, about 364M characters across their roots. It is built offline and reviewed by hand. No rights are inferred
   at build time.
2. **Out of v1:**
   - **Laws (104M characters).** `knesset-laws` already covers the enacted laws, and the Open Law Book overlaps eval's
     reserved Reshumot material.
   - **Namespace 106 (396M characters).** This is contributors' own modern writing under CC BY-SA, not transcriptions
     of public-domain works. Its licence would fit `htext-by-sa`, but it breaks the "underlying work is public domain"
     rule in `sources_plan.md`. Taking it in is a separate decision.
   - Articles that carry the OCR-conversion or auto-conversion templates.
   - Roots not on the works list.
3. **Quality.** There are no ProofreadPage levels in the main namespace, so the lines are `text_quality:
   transcription`, flagged on the card as "unproofread transcription". An eye check of 100 lines against the source
   editions named on each root's page goes on the card. A root whose sample fails is dropped.
4. **Reservations and overlap, unchanged.**
   - The v7 units already map to works and their scans, and those works stay out whole.
   - The `--eval-overlap-drop` list must be present, and eval's official check must find 0 before release.
   - P-hist is the eval domain at risk here (old rabbinic print), so the check matters more than usual.
5. **Attribution, unchanged.** Per article revision: the oldid URL, the history URL, and "Hebrew Wikisource
   contributors", plus the NOTICE.
6. **Sefaria overlap.** The Bavli and Mishneh Torah roots (11M characters) overlap the planned `sefaria-by-sa`. Exact
   lines are deduplicated within the `htext-by-sa` release, whichever corpus is built second.

Expected size: on the order of 200–300M characters of lines after filters. That is several times
`pby-v3`'s plain file, and almost all of it is old rabbinic Hebrew. It feeds P-hist (old print), which is HeOCR's next
training round. These are rough estimates; a measuring build would replace them.

## Decisions needed

1. Whether to build (B) on a reviewed works list, with age as the basis for pre-modern classics (the proposal above).
2. Whether namespace 106 (contributor commentary under CC BY-SA) can ever enter `htext-by-sa`. The proposal leaves it
   out of v1.
3. Who reviews the works list. The proposal: htext drafts it, and heocr-lead reviews it, as for PBY's manual death years.

# htext sources plan

This plan takes htext from one corpus, Project Ben-Yehuda (PBY), to every openly licensed Hebrew text we can
find. It lists the candidate sources, the rights basis of each, an estimated size, and the order to build them in.
It is a plan only: it adds no builder and no data.

- **Status:** accepted by heocr-lead, 2026-11-18 (#6); decisions on the open questions below.
- **Written by:** `htext[claude/claude-code#shay-macbook-m4]@heocr/opensource`.
- **Builds on:**
  - [ADR 0007](https://github.com/HeOCR/hocrsyngen/blob/main/docs/decisions/0007-third-party-public-domain-training-text.md):
    outside public-domain text may be used, Israeli public-domain status is enough, US status is recorded, and
    translations need both the author and the translator in the public domain;
  - heocr-engine decision 0022 (2026-11-18): htext ships as three releases split by licence (below);
  - the hocrgen decisions on Knesset protocols (2026-11-11), plenary private names (2026-11-13), and Sefaria and
    Project Gutenberg texts (2026-11-11).

Sizes are estimates unless marked *measured*. Each builder PR measures its own size and reports it on its card.

## Three releases

Decision 0022: htext ships one release per licence. Every entry records its source licence (the exact label the
source gives) and its credit line, so each release can be rebuilt and filtered.

| Release | Takes | Release licence | Use |
| --- | --- | --- | --- |
| `htext-cc0` | public-domain text, CC0 text, and §6 material (laws, regulations, Knesset records) | CC0-1.0 | the default for training and benchmarks |
| `htext-by` | text under CC BY or equivalent attribution-only terms | each source's attribution terms, with a credit field per entry and one consolidated `NOTICE` | training with credit |
| `htext-by-sa` | CC BY-SA text | CC BY-SA 4.0 for the whole release, with credit per entry | training with credit and share-alike for the text |

Rules for all three:

- **NC and ND are out of every release.** So is any text whose licence is unknown, and any label that no decision
  names. The licence gate matches label strings exactly and fails closed.
- **No line crosses releases.** A `htext-cc0` build never contains a CC BY or CC BY-SA line, and a `htext-by` build
  never contains a CC BY-SA line. Deduplication runs within a release, never across, so a line that exists in both
  a PD source and a BY-SA source stays in each.
- **HeOCR's own processing and metadata stay CC0**, as far as they can be separated from the text: rights and line
  indexes, exclusion lists, cards and checksums. The BY and BY-SA terms bind the source text.
- **Models** trained on `htext-by` or `htext-by-sa` stay Apache-2.0, with the credits in their `NOTICE`
  (decision 0016's reasoning).
- **Leakage checks and eval reservations apply to all three releases** (see "Leakage and eval reservations").

## Shared machinery (first PR after this plan)

Before the second source lands, htext gets a small common layer, so every builder writes the same records:

1. **`htext.rights`:** one entry record for every source, generalising PBY's rights index:
   - `entry_id`, `source`, `source_version` (commit, dump date or API snapshot sha256);
   - `pd_israel` and `pd_us`, each with `basis` and `as_of`. §6 material uses the basis `s6_official_text`;
   - `source_licence` (the exact label), `htext_release` (`cc0`, `by`, `by-sa`) and `credit` (`text`, `url`).
2. **`htext.release`:** a fixed map from licence label to release, plus a guard that every corpus writer calls. The
   guard refuses an entry whose `htext_release` is not the build's release.
   - **Test (decision 0022):** a CC0 build that is fed one CC BY and one CC BY-SA entry must fail.
   - **Test:** a check over every committed card asserts that each card's release matches the licences of its entries.
3. **Layout:** cards stay at `data/<corpus>/<version>/` and gain `htext_release`. Corpus files remain assets of a
   `<corpus>-<version>` GitHub release. A release bundle, for example `htext-cc0-2026.12`, is a manifest of corpus
   files and their sha256s, with no new text.
4. **Leakage:** the hash fixtures gain the eval reservations below, and the check runs on every corpus.
5. **The PBY card** is re-emitted with `htext_release: cc0` and a source licence of `Public Domain`. The published
   `pby-v1` files do not change.

The site page (HeOCR/heocr.github.io, `htext/corpora.json`) is updated whenever a corpus is published.

## `htext-cc0`: sources, in build order

| # | Corpus | Source and route | Rights basis | Size (est.) | Clarity |
| ---: | --- | --- | --- | --- | --- |
| 1 | `pby` v2 | PBY `public_domain_dump`, pinned | creators died ≤ `as_of`−71 (Wikidata); PBY dump licence "Public domain" | 2.03M lines *measured* (v1) → about 9.8M | clear |
| 2 | `knesset-laws` | Knesset OData `KNS_Bill` → laws as enacted (`*_lsr_*.PDF`) on `fs.knesset.gov.il`, K1–8 | §6: laws and regulations | thousands of laws; about 2,146 K1–8 bills carry a publication series; words unmeasured | clear |
| 3 | `knesset-plenary` | Knesset OData `KNS_PlenumSession` → `KNS_DocumentPlenumSession` (`*_ptm_*.pdf`), sittings before 1976-01-01; K13–25 born-digital protocols (decision 1 below) | §6: Knesset protocols; publishable for the period up to 1975 (2026-11-11 decision) | about 3,300 sittings (K1–8); order of tens of millions of words | clear |
| 4 | `tanakh` | Westminster Leningrad Codex (WLC 4.20), `openscriptures/morphhb` `wlc/`, pinned by commit (changed from UXLC, 2026-11-18) | the codex is ancient; the WLC text is in the public domain (OSHB README and file headers) | 23,213 verses; about 58k lines per form *measured* | clear |
| 5 | `sefaria-pd` | Sefaria-Export (public bucket), version JSON, cross-checked with `/api/texts/versions/<title>` | version licence exactly `Public Domain` or `CC0`, **and** `versionSource` names a printing, **and** every named author and editor died ≤ `as_of`−71 | tens of millions of words before filtering; unmeasured after | probable |
| 6 | `gutenberg-he` | Project Gutenberg, via a mirror (not gutenberg.org directly) | PD in the US per PG's record; Israeli status per author | 7 books, one out (living author) | clear but tiny |

### 1. PBY v2: more of PBY

The v1 card already shows where the extra text is (*measured*):

- **The per-work cap.** At 200 lines per work, the cap dropped 7,726,087 segments. A higher cap, or none, takes
  the corpus from 2.03M lines to about 9.8M. A per-work cap stays available as a mix-time option in `hocrsyngen`
  rather than a build-time cut.
- **Death years.** 2,781 works lack a usable death year, mostly medieval and early-modern poets with no Wikidata
  item. The `manual` creators list gets rows, each with a citable source. The 164 anonymous works stay out.
- **Genres.** The build skipped 1,361 works by genre. Drama and reference genres are reviewed for line quality.
- **US status.** Sourcing first-publication years widens the `il_us` variant (668 works today).

The rights rule does not change.

### 2–3. Knesset laws and plenary records

- **Text.** The PDFs carry an OCR text layer: good for the plenary records, with some typos in the laws. It is OCR,
  not a transcription. So these builders add a **line-quality filter**: a word must be found in a lexicon built from
  `htext-cc0`'s clean corpora, or the line is dropped. The card reports the drop rate, and a sample is checked by eye
  before publishing. Soft hyphens and bidi controls are removed. pdftotext gives logical order.
- **Plenary privacy.** Every plenary line passes hocrgen's `plenary_private_names_v1` gate and carries its stamp.
  A line that names a private person, or whose names could not be judged, is dropped (2026-11-13 decision).
- **What is excluded:**
  - committee protocols, of any period, because htext is a published dataset;
  - bills (`_ls1_`), because explanatory notes are written by ministry staff and are not clearly §6;
  - Yalkut HaPirsumim notices: they mix tenders and private names, and there is no bulk route;
  - court rulings, which are out by project policy;
  - Nevo and every other commercial database.
- **Access.** The OData API needs no key. `fs.knesset.gov.il` has no robots file, and `main.knesset.gov.il/robots.txt`
  blocks named SEO bots only. No Knesset terms of use could be found, so the rights rest on §6 and the absence of any
  licence. The fetcher:
  - runs once per pin, outside the build, as `fetch_pby_creators.py` does;
  - sends one request at a time, at most one per second;
  - uses a generic client name;
  - stores the downloads outside git.

### 4. Tanakh

- **Source.** The WLC from OSHB's `morphhb`, pinned by commit (heocr-lead, 2026-11-18). UXLC from tanach.us was the
  first choice, but tanach.us's robots file disallows automated fetching, so htext does not fetch it. The WLC text is
  in the public domain; OSHB's lemma and morphology layers are CC BY 4.0 and are not used, and its `/` morpheme
  dividers are removed.
- **Two forms.** A pointed form without cantillation: U+0591–U+05AF removed, maqaf kept, meteg decided against the
  S10b mark set, and the {פ}/{ס} section markers removed. A plain form with all points removed.
- **Naming.** The card names the edition WLC 4.x, not UXLC, and credits OSHB.
- **Line length.** Each verse is packed to the S10b length profile, as PBY prose is, and no line crosses a verse.
  Balanced verse halves, as PBY poetry is cut, left the median line at 38 characters, outside the S10b targets.

### 5. Sefaria public-domain versions

The gate is the one in the hocrgen decision of 2026-11-11, reused rather than reinvented:

- **Licence.** The `license` field must be exactly `Public Domain` or `CC0`. The variant `PD` maps to
  `Public Domain` only after a check of each version.
- **Printing.** `versionSource` must be the catalogue record of a printing, such as an NLI record, an Internet
  Archive item or a Project Gutenberg ebook. Versions labelled PD that name no printing are out: Torat Emet, On
  Your Way, Daat, Mechon Mamre. So are modern editions labelled PD, such as Miqra Mevoar (2020) and modern critical
  editions of manuscripts.
- **People.** Every author, editor, translator and annotator has a Wikidata death year at or before `as_of`−71.
  Ancient compilations may use `anonymous_work`, with the edition published more than 70 years before `as_of`.
- **Reserved.** *Leket Yosher*, ed. Freimann (`sefaria_leket_yosher`), is held out whole, along with any other
  edition hocrgen or eval reserves.
- **What is not there.** Sefaria has no clean Vilna Bavli: the William Davidson text is CC BY-NC (out), and the
  Wikisource Bavli is CC BY-SA (`htext-by-sa`).

### 6. Project Gutenberg Hebrew

Seven books, one out. The PG header, footer and trademark are stripped, as PG's licence asks when the text is
redistributed. This builder is low priority, and it may be folded into a later "small sources" corpus.

### Considered, not planned for `htext-cc0`

| Source | Why not now |
| --- | --- |
| Open Siddur (CC0 items) | Licences are per post, there is no bulk export, and the site returned 403 to automated fetches. Revisit if a dump appears. |
| Internet Archive OCR (`_djvu.txt`) | raw OCR with no transcription; better used as a scan source by hocrgen |
| Historical Jewish Press (JPress) | no stated licence for the OCR text; noisy |
| Wikimedia Commons | scans, almost no text files |
| hebrewbooks.org | terms unreachable; scans |
| Dicta datasets, HeDC4 | NC or unknown licences; HeDC4 is web crawl with unclear rights |
| Knesset Corpus (Haifa), ParlaMint-IL | conflicting or BY-SA labels; 1992 on; mixes committee text |
| Knesset plenary K8 (from 1976) and K9–12 | no hocrgen publishability flag (decision 1 below) |

## `htext-by`: sources

| # | Corpus | Source | Rights basis | Size (est.) | Clarity |
| ---: | --- | --- | --- | --- | --- |
| 1 | `sefaria-by` | Sefaria versions labelled exactly `CC-BY` | the version licence; the credit names Sefaria and the version's source | unmeasured; mostly modern editions and translations, few Hebrew | probable |
| 2 | `opensiddur-by` | Open Siddur items under CC BY | per-item licence | small; no bulk route | unclear (deferred) |

`htext-by` starts with Sefaria. Each version still needs its underlying Hebrew text to be public domain, or to be
licensed CC BY itself, and its own record. The OSHB morphology layer (CC BY) is annotation, not text, and is not
used.

## `htext-by-sa`: sources

| # | Corpus | Source | Rights basis | Size (est.) | Clarity |
| ---: | --- | --- | --- | --- | --- |
| 1 | `wikisource` | Hebrew Wikisource `pages-articles` dump, pinned by date and SHA-256 | CC BY-SA 4.0 for quality 3 and 4 ProofreadPage transcriptions with explicit underlying-work rights markings | unmeasured | builder documented in [wikisource.md](wikisource.md); release pending |
| 2 | `sefaria-by-sa` | Sefaria versions labelled exactly `CC-BY-SA`, e.g. the Wikisource Bavli and Mishneh Torah | the version licence | large; overlaps `wikisource` (deduplicated within the release) | clear |
| 3 | `opensiddur-by-sa` | Open Siddur items under CC BY-SA | per-item licence | small | deferred |

- **Underlying work.** A proofread page needs an explicit public-domain or compatible free-licence marking
  for the underlying work. The rights index records the qualifying template or category.
- **Credit.** Credit is per page: the page title, its URL and "Hebrew Wikisource contributors". The release NOTICE
  points to the history of each page.
- **Eval reservations.** HeOCR's evaluation holds Hebrew Wikisource Indexes out whole: the audit2 and release-test
  Indexes in hocrgen's `docs/wikisource_lines.md`, and the pages behind the public Wikisource benchmark. No line from
  those Indexes or pages, or from their works, may enter `htext-by-sa`. The builder maps Indexes to Page
  titles and article transclusions. Other editions are outside the v1 mapping and rely on the mandatory
  official eval overlap check, which must find zero before release.

## Leakage and eval reservations (all releases)

- **Today.** The current check covers line hashes and word 3-grams, in pointed and stripped forms, against
  `hocrsyngen`'s packaged eval text and `hocrgen`'s bidi corpus.
- **Added before any new corpus is published:**
  - **heocr-eval's reserved texts.** I have asked eval for them, in particular the modern-legislation and PBY prose
    in its print-and-scan pack. Reserved works and documents are excluded whole, not only line by line.
  - **The mid-century review batch** (`newprinted_midcentury_v0`). Its K1–12 plenary and law pages are eval
    references, so their sittings and laws are excluded whole from `knesset-plenary` and `knesset-laws`.
  - **hocrgen reserved editions and Indexes:** *Leket Yosher*, the Wikisource audit2 and release-test Indexes, and
    any `--reserve` list that follows.
  - **Eval-reserved Knesset units** listed by hocrgen's `knesset_lines` planner.
- **Form.** All of this enters as hash-only fixtures, so tests stay offline, together with whole-unit deny lists of
  IDs. Each card lists every fixture it was checked against.
- **Standing rule (proposed).** Before a corpus from a source that eval also draws on is published, eval confirms
  that its reservations are in the fixtures.

### Reservations received

- **Source of truth.** Eval's `reservations/eval_reservations_v1.json` in heocr-restricted-eval (#31), schema
  `heocr_eval_reservations.v1`. It holds identifiers only, never reference text. htext reads it as it is
  (`htext.reservations`), and every builder passes it with `--reserved`. A unit it lists is excluded whole, in every
  release. The loader fails closed on any field it does not recognise.
- **Pins** (repository commit plus file sha256; cards record the file sha256):

  | File in heocr-restricted-eval | Commit | sha256 |
  | --- | --- | --- |
  | `reservations/eval_reservations_v1.json` | `7190455e7492ee2674768e09af74b87dd7e38b6d` | `6952c8d5e93b3c2118dbc1031db844d142b83a795252c9eba00659c165a1b4a5` |
  | `reservations/dbench_text_pool.hashes.json` | `7190455e7492ee2674768e09af74b87dd7e38b6d` | `6b5a0b8188d8ed44c01d13c0ed00998c8c67911f86e53d95dc5cd25e6556e9b7` |
  | `preregistration/print_scan_PS-v1_2026-11-18/htext_leakage_ps_v1.hashes.json` | `876f3dc284531ac339fc5ec6de3dc0f0d1520d9a` | `adc0559fcce29c53eff43f6f323cfd68c6ceccc06d49d79d05f046ccbc8aa10f` |
  | `reservations/eval_reservations_v2.json` | `8ca52a4bd3edf098266a9eb6dec6df0fb844d9be` | `2abce5ea8083ae7527461776bbeb70c5e4eecf3e52910e7b607bd94a68ed2a1e` |

  `eval_reservations_v2.json` (heocr-restricted-eval#34) supersedes v1. `pby` v2 is built against it, with the
  PS-v1 and D-bench fixtures above; its card lists each set with counts only.
- **What it reserves** (v1, 2026-11-18, as htext reads it):

  | Unit kind | Units | Sets |
  | --- | ---: | --- |
  | PBY works | 4 | PS-v1 print-and-scan |
  | Reshumot booklets, scanned or born-digital | 226 | PS-v1, mid-century, P-mod, D-bench text pool |
  | Knesset plenary sittings (K1–25) | 138 | mid-century, P-mod |
  | Knesset committee protocols | 7 | P-mod (committees are out of htext anyway) |
  | Hebrew Wikisource Indexes | 28 | P-hist audit2, line_verify |
  | NLI records aligned to PBY books | 2 | line_verify |

  Pages and lines are cut to their unit, so a reserved Wikisource page reserves its whole Index, and a reserved
  aligned line reserves its whole NLI record. Scanned and born-digital Reshumot are the same booklets.
- **Fixtures.** The PS-v1 fixture covers the twelve printed pages. The D-bench fixture covers the 83 born-digital
  booklets' text pool (17,779 lines). Both are in htext's leakage format and are passed with `--leakage`.
  PBY corpora apply fixtures by line and by word 3-gram. Legal corpora apply them by line and exclude reserved
  booklets and sittings whole, because a word 3-gram match on legal formulas would drop far too much. Each legal
  builder PR records which mode it used.
- **Standing rule** (eval and htext, 2026-11-18). A source that eval might use gets its reservation from eval before
  htext publishes any corpus built from it. New eval sets arrive as a new version of eval's file.
- **Ids stay private.** Cards record each set's name, the file's sha256 and counts, never the reserved ids.
- **v2 additions.**
  - line_verify's two NLI records now name their PBY works, which gives 10 more PBY works, held out whole. The reader
    takes `pby_work_ids` from any set.
  - A handwriting set adds 34 HASH units (`hash_source_ids`). htext builds no HASH text, but the reader keeps them,
    so the reservation is complete.
  - With v2, htext reads 14 PBY works.
- **Exposure through other routes.** `pby_excluded_works` lists only the works with lines in htext. PBY works also
  reach training through other lists, for example lines aligned to NLI scans of the same books. A set meant to be
  safe for evaluation is checked against those lists too.

## Order of work

One builder per PR, each branched from `main`, with tests that need no network and green CI:

1. this plan;
2. shared machinery: the rights record, the release guard and its tests, and the PBY card re-emitted;
3. `pby` v2;
4. `knesset-laws`, then `knesset-plenary` (eval's reservations: received 2026-11-18);
5. `tanakh`;
6. `sefaria-pd`, then `sefaria-by` and `sefaria-by-sa` from the same fetcher;
7. `wikisource` (`htext-by-sa`);
8. small sources: Gutenberg, and Open Siddur if a bulk route appears.

## Decisions on the open questions (heocr-lead, 2026-11-18)

1. **Plenary records from 1976 on.** htext follows hocrgen's existing publishability flags exactly, per Knesset,
   with no judgment of its own, and every line passes `plenary_private_names_v1`. Today that means:
   - **K1–8 sittings up to 1975-12-31:** period 1 of the 2026-11-11 decision; scans with an OCR text layer.
   - **K13–25:** hocrgen's `knesset_lines` plenary series (`knessetplenarylines_v1`) marks every unit `publishable`.
     The source is born-digital DOC/DOCX protocols, so `text_quality: transcription`.
   - **Out:** K8 sittings from 1976-01-01, and K9–12, which no hocrgen flag marks. They come in only if hocrgen
     marks them.

   Committee protocols stay out of every period, including the pre-1976 committee scans.
2. **Bills** stay out of v1. Enacted laws already carry the enacted text. Revisit only with a reason.
3. **OCR text layers** may be published in `htext-cc0`, on three conditions:
   - the lexicon line filter;
   - a sampled check by eye, whose **measured error rate goes on the card**;
   - `text_quality: ocr_layer` on every entry, so users and `hocrsyngen` can include or exclude it.

   Lines from OCR layers never build word lists, lexicons or dawgs (`htext.release.lexicon_eligible`). The lexicon
   that filters OCR lines is built from `transcription` entries only.

— htext[claude/claude-code#shay-macbook-m4]@heocr/opensource

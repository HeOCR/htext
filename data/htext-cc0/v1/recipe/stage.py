"""Stage a unified tier package: data shards (hard links), README (HF config, components with HF commit + DOI,
per-source counts, CLEAN references, tag note), NOTICE (per-source credit; Sefaria per-edition credits), manifest,
recipe, SHA256SUMS, and the Zenodo ZIP. Usage: stage.py TIER OUT_DIR(build) STAGE_DIR REGISTRY_JSON CLEAN_REFS_JSON"""
import gzip, hashlib, json, os, shutil, sys, zipfile
TIER, BUILD, STAGE, REG, REFS = sys.argv[1:6]
m = json.load(open(f"{BUILD}/build_manifest.json")); reg = {f'{x["corpus"]}-{x["version"]}': x for x in json.load(open(REG))["corpora"]}
refs = json.load(open(REFS)); SRC = os.path.join(os.path.dirname(BUILD), "src")
LIC = {"cc0": ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/", "cc0-1.0"),
       "by": ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/", "cc-by-4.0"),
       "by-sa": ("CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/", "cc-by-sa-4.0")}[TIER]
d = os.path.join(STAGE, f"htext-{TIER}"); os.makedirs(f"{d}/data", exist_ok=True); os.makedirs(f"{d}/recipe", exist_ok=True)
for name in m["files"]:
    t = os.path.join(d, name)
    if not os.path.exists(t): os.link(os.path.join(BUILD, name), t)
shutil.copy(f"{BUILD}/build_manifest.json", f"{d}/build_manifest.json")
here = os.path.dirname(os.path.abspath(__file__))
for f in ("fetch.py", "build.py", "stage.py"): shutil.copy(os.path.join(here, f), f"{d}/recipe/{f}")
st = m["stats"]; comp = m["components"]
rows = []
for n in m["order"]:
    r = reg[n]; z = (r.get("zenodo") or {}).get("doi")
    hf = f'[{comp[n]["repo"]}@{comp[n]["commit"][:8]}](https://huggingface.co/datasets/{comp[n]["repo"]}/tree/{comp[n]["commit"]})'
    rows.append(f'| `{n}` | {hf} | {z or "—"} | {st["by_source"].get(n, 0):,} | {refs.get(n, "")} |')
var = ", ".join(f"{k} {v:,}" for k, v in sorted(st["by_variant"].items()))
readme = f"""---
language:
- he
license: {LIC[2]}
tags:
- ocr
- hebrew
- htext
configs:
- config_name: default
  data_files:
  - split: train
    path: data/*.parquet
---

# htext-{TIER}: all {LIC[0]} htext text releases in one dataset

{st["rows_out"]:,} Hebrew (and some Aramaic) text lines for OCR training: every published htext release under
{LIC[0]}, merged and de-duplicated. The per-source repositories stay as they are; this dataset is a convenience union.

## Columns

| Column | Meaning |
| --- | --- |
| `text` | the line |
| `variant` | `plain` or `niqqud` (pointed); for the Knesset plenary, `ocr` (the scans' text layer) or `transcription` |
| `lang` | `he`, or `arc` for Aramaic-heavy works (Talmud tractates, Targum, Zohar) |
| `source`, `source_release` | the component release the row was taken from |
| `sources` | every component release that has this exact line |
| `licence` | the source's own licence or rights basis for the line |
| `work_id`, `edition` | the work (and edition, where known) in the source's own ids |

Variants: {var}.

## Build

- Exact de-duplication on (`variant`, `text`) within this dataset. {st["rows_in"]:,} input rows; {st["rows_out"]:,} kept.
  The first row in the component order below is kept; the others are listed in `sources`. The Knesset plenary OCR and
  transcription lanes are separate variants, so a line in both is kept in both.
- Every component file was fetched from its pinned Hugging Face commit and checked against the SHA-256 on its htext
  card. Recipe: `recipe/` (fetch, build, stage); `build_manifest.json` lists every input file and hash.

## Components

| Release | Hugging Face | DOI | Rows kept here | CLEAN record (HeOCR, private) |
| --- | --- | --- | ---: | --- |
{chr(10).join(rows)}

## Evaluation hygiene

No new CLEAN check was needed: every component is an already published release that passed HeOCR's independent
CLEAN check (records above), and this dataset as a whole passed a work-level screen against HeOCR's current
evaluation reservations (v14; record #1893). Lines that share text with material HeOCR uses for evaluation are tagged in private
sidecars of those checks, not dropped (contamination policy v2, amendment 1), and HeOCR evaluations report results
both with and without them. Works that an evaluation set holds out whole are not in any component.

## Rights and credit

Released under [{LIC[0]}]({LIC[1]}). See NOTICE.md for the credit of every source.

Built by HeOCR (https://github.com/HeOCR) with htext (https://github.com/HeOCR/htext).
"""
open(f"{d}/README.md", "w", encoding="utf-8").write(readme)
N = [f"# Attribution\n\nhtext-{TIER} merges these htext releases; credit each source as below.\n"]
for n in m["order"]:
    c = reg[n]["credit"]; N.append(f"- **{n}**: {c['text']} ({c.get('url', '')})")
seen = set(); ed = []
for n in m["order"]:
    if not n.startswith("sefaria-v3"): continue
    for l in gzip.open(os.path.join(SRC, n, "sefaria_rights_index.v3.jsonl.gz"), "rt", encoding="utf-8"):
        r = json.loads(l); k = (r.get("title"), (r.get("credit") or {}).get("text"))
        if k not in seen: seen.add(k); ed.append(f"- {k[0]}: {k[1]} ({r.get('source_licence')})")
if ed: N += ["", "## Sefaria editions (from the rights indexes)", ""] + ed
if TIER == "by-sa": N += ["", "Wikisource text: Hebrew Wikisource contributors, CC BY-SA 4.0. The per-page revision and contributor history is in each Wikisource component's rights index (linked above)."]
open(f"{d}/NOTICE.md", "w", encoding="utf-8").write("\n".join(N) + "\n")
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()
allf = sorted(os.path.relpath(os.path.join(r, f), d) for r, _, fs in os.walk(d) for f in fs if f != "SHA256SUMS")
open(f"{d}/SHA256SUMS", "w").write("".join(f"{sha(os.path.join(d, f))}  {f}\n" for f in allf))
z = os.path.join(STAGE, f"htext-{TIER}.zip")
with zipfile.ZipFile(z, "w", zipfile.ZIP_STORED) as zf:  # parquet is already zstd-compressed
    for f in sorted(allf + ["SHA256SUMS"]):
        zi = zipfile.ZipInfo(f"htext-{TIER}/{f}", date_time=(2026, 11, 27, 0, 0, 0)); zi.external_attr = 0o644 << 16
        with open(os.path.join(d, f), "rb") as fi, zf.open(zi, "w", force_zip64=True) as fo:
            for b in iter(lambda: fi.read(1 << 20), b""): fo.write(b)
print(TIER, len(allf) + 1, "files;", os.path.getsize(z), "zip bytes")

"""Stage htext Sefaria v3 (cc0 / by / by-sa) and Gutenberg v1 packages for HF and Zenodo.
Each package: the release files as built, README.md, NOTICE.md (per-edition credit from the rights index),
SHA256SUMS over every file, and a deterministic ZIP. Usage: stage.py V3_DIR OUT_DIR"""
import gzip, hashlib, json, os, sys, zipfile
from pathlib import Path
V3, OUT = Path(sys.argv[1]), Path(sys.argv[2])
LIC = {"cc0": ("CC0 1.0 / public domain", "https://creativecommons.org/publicdomain/zero/1.0/", "cc0-1.0"),
       "by": ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/", "cc-by-4.0"),
       "by-sa": ("CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/", "cc-by-sa-4.0")}
TAGS = ("HeOCR's independent CLEAN check (2026-11-27) kept every line. 19,073 lines of the Sefaria v3 and Gutenberg "
        "tranche share text with material HeOCR uses for evaluation; they are tagged in a private sidecar, not dropped "
        "(contamination policy v2, amendment 1), and HeOCR evaluations report results both with and without them. "
        "Works that an evaluation set holds out whole are not in this release.")
def sha(p): h = hashlib.sha256(); h.update(p.read_bytes()); return h.hexdigest()
def package(name, src, lane, title, desc, rights_file, credit_line, extra=""):
    d = OUT / name; d.mkdir(parents=True, exist_ok=True)
    for f in sorted(src.iterdir()):
        if f.name != "SHA256SUMS":
            t = d / f.name
            if not t.exists(): os.link(f, t)
    lic, url, hf = LIC[lane]
    card = json.loads((src / "corpus_card.json").read_text(encoding="utf-8"))
    files = {k: v for k, v in card["files"].items()}
    rows = "\n".join(f"| `{k}` | {v['lines']:,} |" for k, v in files.items())
    (d / "README.md").write_text(f"""---
language:
- he
license: {hf}
tags:
- ocr
- hebrew
- htext
---

# {title}

{desc}

## Files

| Text file | Lines |
| --- | ---: |
{rows}

`*_arc` files hold Aramaic-heavy works (Talmud tractates, Targum, Zohar); leave them out for a Hebrew-only fit.
The line index binds every line to its work, edition and segment; the rights index gives each edition's licence,
credit and source URL. SHA256SUMS covers the package files. CORPUS_CARD.md and corpus_card.json describe the build.

## Evaluation hygiene

{TAGS}{extra}

## Rights and credit

Released under [{lic}]({url}). {credit_line.replace('listed below', 'listed in NOTICE.md')}

Built by HeOCR (https://github.com/HeOCR) with htext (https://github.com/HeOCR/htext).
""", encoding="utf-8")
    notice = [f"# Attribution\n\n{credit_line}\n\nEdition credits (from `{rights_file}`):\n"]
    seen = set()
    for l in gzip.open(src / rights_file, "rt", encoding="utf-8"):
        r = json.loads(l); c = (r.get("credit") or {}).get("text") or r.get("title")
        key = (r.get("title"), c)
        if key in seen: continue
        seen.add(key); notice.append(f"- {r.get('title')}: {c} ({r.get('source_licence')})")
    (d / "NOTICE.md").write_text("\n".join(notice) + "\n", encoding="utf-8")
    names = sorted(p.name for p in d.iterdir() if p.name != "SHA256SUMS")
    (d / "SHA256SUMS").write_text("".join(f"{sha(d / n)}  {n}\n" for n in names), encoding="utf-8")
    z = OUT / f"htext-{name}.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in sorted(p.name for p in d.iterdir()):
            zi = zipfile.ZipInfo(f"htext-{name}/{n}", date_time=(2026, 11, 27, 0, 0, 0)); zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            with open(d / n, "rb") as fi, zf.open(zi, "w") as fo:
                for b in iter(lambda: fi.read(1 << 20), b""): fo.write(b)
    print(name, len(names) + 1, "files;", z.stat().st_size, "zip bytes", flush=True)
S = "Text from Sefaria (https://www.sefaria.org) and the editions it credits."
package("sefaria-v3-cc0", V3 / "release-cc0", "cc0", "htext Sefaria v3 (cc0): public-domain and CC0 Hebrew training lines",
        "Hebrew and Aramaic text lines for OCR training from 4,697 public-domain and CC0 editions in Sefaria (29.1 million lines), cut to printed-line lengths. HeOCR normalized, segmented, filtered and de-duplicated the text, and removed lines already in other htext releases.",
        "sefaria_rights_index.v3.jsonl.gz", S,
        extra=" Three works held out whole by an evaluation set were removed after CLEAN (79,735 lines); five short pointed lines that then reappeared in `sefaria_cc0_lines_niqqud_arc_v3.txt` are texts already in the CLEAN-checked tranche.")
package("sefaria-v3-by", V3 / "release-by", "by", "htext Sefaria v3 (by): CC BY Hebrew training lines",
        "Hebrew and Aramaic text lines for OCR training from 268 CC BY editions in Sefaria (1.38 million lines), cut to printed-line lengths and de-duplicated against other htext releases. Each edition keeps its own credit.",
        "sefaria_rights_index.v3.jsonl.gz", S + " Each edition is CC BY; credit it as listed below.")
package("sefaria-v3-by-sa", V3 / "release-by-sa", "by-sa", "htext Sefaria v3 (by-sa): CC BY-SA Hebrew training lines",
        "Hebrew and Aramaic text lines for OCR training from 84 CC BY-SA editions in Sefaria (591,087 lines), cut to printed-line lengths and de-duplicated against other htext releases. Each edition keeps its own credit; share-alike applies.",
        "sefaria_rights_index.v3.jsonl.gz", S + " Each edition is CC BY-SA; credit it as listed below and share alike.")
package("gutenberg-v1", V3 / "release-gutenberg", "cc0", "htext Gutenberg v1: public-domain Hebrew training lines",
        "Hebrew text lines for OCR training from two public-domain Project Gutenberg ebooks (PG 43740, Bet Nekhot ha-Halakhot, responsa of the Geonim; PG 45252, Isaac Erter's Ha-Tsofeh le-Veit Yisrael), 5,316 lines. Only the text between Project Gutenberg's start and end markers is used, and the producers' electronic-edition notes are left out.",
        "gutenberg_rights_index.v1.jsonl.gz", "Transcriptions by Project Gutenberg volunteers (https://www.gutenberg.org); the works are in the public domain.")

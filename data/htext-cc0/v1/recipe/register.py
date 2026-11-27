"""Registry rows + cards: htext-{cc0,by,by-sa} v1 (unified), sefaria v3.1-cc0, and v3-cc0 withdrawn.
Usage: register.py REPO_ROOT UNIFIED_STAGE_DIR SEFARIA_PUBLISH_DIR"""
import json, os, re, sys
from pathlib import Path
ROOT, STAGE, SP = map(Path, sys.argv[1:4])
tiers = json.loads((Path.home() / ".config/heocr/unified-tiers-state.json").read_text())
hfs = json.loads((Path.home() / ".config/heocr/hf-sefaria-v3-state.json").read_text())["sefaria-v3.1-cc0"]
z31 = json.loads((Path.home() / ".config/heocr/zenodo-production-sefaria-v31-state.json").read_text())["sefaria-v3.1-cc0"]
CONCEPT = {}
reg_p = ROOT / "data/releases.json"; s = reg_p.read_text(encoding="utf-8"); reg = json.loads(s)
rows_new = []
# sefaria v3.1-cc0
d = ROOT / "data/sefaria/v3.1-cc0"; d.mkdir(parents=True, exist_ok=True)
for f in ("corpus_card.json", "CORPUS_CARD.md", "README.md", "SHA256SUMS"):
    (d / f).write_bytes((SP / "sefaria-v3.1-cc0" / f).read_bytes())
card = json.loads((d / "corpus_card.json").read_text(encoding="utf-8"))
rows_new.append({"corpus": "sefaria", "version": "v3.1-cc0", "card": "data/sefaria/v3.1-cc0/corpus_card.json", "release_tag": "sefaria-v3.1-cc0",
                 "supersedes": "sefaria-v3-cc0", "htext_release": "cc0", "source_licence": "Public Domain", "text_quality": card["text_quality"],
                 "credit": card["credit"], "huggingface": "HeOCR/htext-sefaria", "huggingface_revision": hfs["commit"],
                 "huggingface_path": "releases/sefaria-v3.1-cc0", "zenodo": {"doi": z31["doi"], "concept_doi": "10.5281/zenodo.24521422"}})
# unified tiers
for t in ("cc0", "by", "by-sa"):
    st = tiers.get(t, {})
    if not st.get("zpublished"): print("skip unpublished tier", t); continue
    man = json.load(open(STAGE / f"htext-{t}" / "build_manifest.json"))
    credit = {"text": "the htext component releases listed in NOTICE.md (Sefaria and its editions, Project Ben-Yehuda, Hebrew Wikisource contributors, the Knesset, Project Gutenberg, OSHB/WLC)" if t == "cc0" else
              ("Sefaria and the CC BY editions it credits (see NOTICE.md)" if t == "by" else "Hebrew Wikisource contributors and the CC BY-SA Sefaria editions (see NOTICE.md)"),
              "url": f"https://huggingface.co/datasets/HeOCR/htext-{t}/blob/{st['commit']}/NOTICE.md"}
    lic = {"cc0": ["Israel Copyright Act 2007 s.6 (not protected)", "Public Domain"], "by": ["CC-BY"], "by-sa": ["CC-BY-SA"]}[t]
    q = {f"variant:{v}": ("ocr_layer" if v == "ocr" else "transcription") for v in sorted(man["stats"]["by_variant"])}
    cardu = {"schema": "htext_unified_card.v1", "name": f"htext-{t}", "corpus_version": "v1", "htext_release": t, "credit": credit,
             "source_licences": lic, "sources": [{"source_licence": x} for x in lic], "text_quality": q,
             "files": {f"variant:{v}": {"rows": n, "text_quality": q[f"variant:{v}"]} for v, n in sorted(man["stats"]["by_variant"].items())},
             "shards": man["files"], "rows_in": man["stats"]["rows_in"], "rows_out": man["stats"]["rows_out"], "by_source": man["stats"]["by_source"],
             "components": {n: {"repo": c["repo"], "commit": c["commit"]} for n, c in man["components"].items()},
             "dedupe": man["dedupe"], "clean": "no new CLEAN: every component passed CLEAN (records in README); work-level screen vs reservations v14: restricted-eval #1893",
             "huggingface": f"HeOCR/htext-{t}", "huggingface_revision": st["commit"], "zenodo": {"doi": st["doi"]}}
    dd = ROOT / f"data/htext-{t}/v1"; dd.mkdir(parents=True, exist_ok=True)
    (dd / "corpus_card.json").write_text(json.dumps(cardu, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (dd / "README.md").write_bytes((STAGE / f"htext-{t}" / "README.md").read_bytes())
    rows_new.append({"corpus": f"htext-{t}", "version": "v1", "card": f"data/htext-{t}/v1/corpus_card.json", "release_tag": f"htext-{t}-v1",
                     "htext_release": t, "source_licences": lic, "source_licence": lic[0], "text_quality": q, "credit": credit,
                     "huggingface": f"HeOCR/htext-{t}", "huggingface_revision": st["commit"], "zenodo": {"doi": st["doi"]}})
# withdraw v3-cc0 (text edit keeps the file's formatting)
old = '"release_tag": "sefaria-v3-cc0",'
assert s.count(old) == 1
s = s.replace(old, old + '\n      "withdrawn": {"date": "2026-11-27", "reason": "reserved eval work removed (Arukh HaShulchan, Choshen Mishpat, a P-hist hold-out book, and footnotes on another; restricted-eval #1893)", "superseded_by": "sefaria-v3.1-cc0", "assets": "removed from HF main (commit ' + hfs["v3_removed_commit"][:8] + '; history keeps them); the Zenodo version stays as an older version"},')
tail = "    }\n  ]\n}\n"; assert s.endswith(tail); s = s[:-len(tail)]
for r in rows_new:
    s += "    },\n    {\n" + ",\n".join(f"      {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in r.items()) + "\n"
s += tail; reg_p.write_text(s, encoding="utf-8"); json.loads(s); print("rows added:", [r["corpus"] + "-" + r["version"] for r in rows_new])

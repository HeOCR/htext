"""Zenodo for htext Sefaria v3 (cc0, by: new versions of 24521423 / 24521430; by-sa, Gutenberg v1: new records), one
ZIP each mirroring the HF package (revisions from ~/.config/heocr/hf-sefaria-v3-state.json). md5 read back.
State: ~/.config/heocr/zenodo-production-sefaria-v31-state.json. Steps: draft | publish."""
import copy, hashlib, json, os, sys
from pathlib import Path
src = open(Path(__file__).parent / "zenodo_linepairs.py").read().replace("\nmain()\n", "\n")
z1 = {}; exec(compile(src, "zenodo_linepairs.py", "exec"), z1); call = z1["call"]
PUB = Path.home() / "temp/heocr/downloads/htext-sefaria/v3/publish"
HFST = json.loads((Path.home() / ".config/heocr/hf-sefaria-v3-state.json").read_text())
STATE = Path.home() / ".config/heocr/zenodo-production-sefaria-v31-state.json"
state = json.loads(STATE.read_text()) if STATE.exists() else {}
save = lambda: STATE.write_text(json.dumps(state, indent=2) + "\n")
token = os.environ["ZENODO_TOKEN"]
def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return "md5:" + h.hexdigest()
JOBS = [("sefaria-v3.1-cc0", "24581317", "24581317", "HeOCR/htext-sefaria", "releases/sefaria-v3.1-cc0", "cc0-1.0",
         "htext Sefaria v3.1: public-domain and CC0 Hebrew training lines (HeOCR)", 28994342)]
step = sys.argv[1]
for name, prev, tmpl, repo, path, lic, title, lines in JOBS:
    st = state.setdefault(name, {})
    if step == "draft":
        if st.get("drafted"): print("drafted", name, st["doi"]); continue
        rev = HFST[name]["commit"]; assert HFST[name].get("verified"), name
        hf = f"https://huggingface.co/datasets/{repo}/tree/{rev}" + (f"/{path}" if path else "")
        base = call("GET", f"/records/{tmpl}", token)
        if not st.get("id"):
            st["id"] = (call("POST", f"/records/{prev}/versions", token) if prev else call("POST", "/records", token, {"metadata": {}, "files": {"enabled": True}}))["id"]; save()
        rid = st["id"]; z = PUB / f"htext-{name}.zip"; key = z.name
        have = {e["key"]: e for e in call("GET", f"/records/{rid}/draft/files", token).get("entries", [])}
        for k in list(have):
            if k != key or have[k].get("checksum") != md5(z): call("DELETE", f"/records/{rid}/draft/files/{k}", token); have.pop(k)
        if key not in have:
            call("POST", f"/records/{rid}/draft/files", token, [{"key": key}])
            with open(z, "rb") as f: call("PUT", f"/records/{rid}/draft/files/{key}/content", token, data=f.read(), ctype="application/octet-stream")
            call("POST", f"/records/{rid}/draft/files/{key}/commit", token); print("uploaded", key, flush=True)
        have = {e["key"]: e["checksum"] for e in call("GET", f"/records/{rid}/draft/files", token)["entries"]}
        assert have == {key: md5(z)}, (name, have)
        m = copy.deepcopy(base["metadata"])
        m["title"] = title; m["version"] = name; m["publication_date"] = "2026-11-27"
        m["rights"] = [{"id": lic}]
        m["description"] = (f"<p>{lines:,} Hebrew OCR training lines in {name}. This version supersedes sefaria-v3-cc0: a work held out for HeOCR evaluation (Arukh HaShulchan, Choshen Mishpat, Vilna 1923-29) and footnotes printed with another held-out work were found in v3 and are removed here (144,843 lines); v3.1 is otherwise a subset of v3. The attached ZIP holds the line files, per-line and "
            "rights indexes (each edition's licence, credit and source), NOTICE, README, corpus card and SHA256SUMS. HeOCR's CLEAN "
            "check kept every line; lines sharing text with HeOCR evaluation material are tagged in a private sidecar and results "
            f'are reported with and without them.</p><p><a href="{hf}">Hugging Face, identical package files</a></p>')
        m["related_identifiers"] = [{"identifier": hf, "scheme": "url", "relation_type": {"id": "isidenticalto"}, "resource_type": {"id": "dataset"}},
            {"identifier": "https://www.sefaria.org" if "sefaria" in name else "https://www.gutenberg.org", "scheme": "url",
             "relation_type": {"id": "isderivedfrom"}, "resource_type": {"id": "dataset"}}]
        dr = call("GET", f"/records/{rid}/draft", token)
        if not dr.get("pids", {}).get("doi"): call("POST", f"/records/{rid}/draft/pids/doi", token); dr = call("GET", f"/records/{rid}/draft", token)
        call("PUT", f"/records/{rid}/draft", token, {"metadata": m, "pids": dr["pids"], "files": {"enabled": True}, "access": {"record": "public", "files": "public"}})
        st.update(drafted=True, doi=dr["pids"]["doi"]["identifier"], hf=hf); save(); print("drafted", name, st["doi"], flush=True)
    elif step == "publish":
        if not st.get("published"): call("POST", f"/records/{st['id']}/draft/actions/publish", token); st["published"] = True; save()
        print("published", name, st["doi"])

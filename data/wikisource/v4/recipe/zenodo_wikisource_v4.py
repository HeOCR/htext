"""Zenodo wikisource-v4 as a new version of record 24521419 (concept 24521418): one ZIP mirroring HF
HeOCR/htext-wikisource releases/wikisource-v4 @a5ee2ac1. State in ~/.config/heocr/zenodo-production-wikisource-v4-state.json."""
import copy, hashlib, json, os, sys, urllib.request
from pathlib import Path
src = open(Path(__file__).parent / "zenodo_linepairs.py").read().replace("\nmain()\n", "\n")
z1 = {}; exec(compile(src, "zenodo_linepairs.py", "exec"), z1); call = z1["call"]
PREV, REV = "24521419", "a5ee2ac15051447d571e027c87c9512317cce919"
HFURL = f"https://huggingface.co/datasets/HeOCR/htext-wikisource/tree/{REV}/releases/wikisource-v4"
ZIP = Path("/private/tmp/claude-501/-Users-shaypalachy-agents-environments-opensource-projects-heocr/637d117b-830a-4c5a-b823-a43dddffc52a/scratchpad/wsv4/htext-wikisource-v4.zip")
STATE = Path.home() / ".config/heocr/zenodo-production-wikisource-v4-state.json"
md5 = lambda p: "md5:" + hashlib.md5(p.read_bytes()).hexdigest()
token = os.environ["ZENODO_TOKEN"]; state = json.loads(STATE.read_text()) if STATE.exists() else {}
save = lambda: STATE.write_text(json.dumps(state, indent=2) + "\n"); step = sys.argv[1]
if step == "draft":
    prev = call("GET", f"/records/{PREV}", token)
    if not state.get("id"): state["id"] = call("POST", f"/records/{PREV}/versions", token)["id"]; save()
    rid = state["id"]; key = ZIP.name
    have = {e["key"]: e for e in call("GET", f"/records/{rid}/draft/files", token).get("entries", [])}
    for k in list(have):
        if k != key or have[k].get("checksum") != md5(ZIP): call("DELETE", f"/records/{rid}/draft/files/{k}", token); have.pop(k)
    if key not in have:
        call("POST", f"/records/{rid}/draft/files", token, [{"key": key}])
        call("PUT", f"/records/{rid}/draft/files/{key}/content", token, data=ZIP.read_bytes(), ctype="application/octet-stream")
        call("POST", f"/records/{rid}/draft/files/{key}/commit", token)
    have = {e["key"]: e["checksum"] for e in call("GET", f"/records/{rid}/draft/files", token)["entries"]}
    assert have == {key: md5(ZIP)}, have
    meta = copy.deepcopy(prev["metadata"])
    meta["title"] = "htext Wikisource B v4: Hebrew Wikisource main-namespace training lines (HeOCR)"
    meta["version"] = "wikisource-v4"; meta["publication_date"] = "2026-11-27"
    meta["description"] = ("<p>4,088 Hebrew OCR training lines in wikisource-v4, from five works on Hebrew Wikisource (מאמר הדור, "
        "דברי אגרת, קורא הדורות, אל הציפור, מעשה שמשון). The attached ZIP contains source attribution (NOTICE, rights index "
        "with revision links), per-line indexes, the corpus card and SHA256SUMS. Text: Hebrew Wikisource contributors, "
        f'CC BY-SA 4.0.</p><p><a href="{HFURL}">Hugging Face, identical package files</a></p>')
    for r in meta.get("related_identifiers", []):
        if "huggingface.co" in r["identifier"]: r["identifier"] = HFURL
    dr = call("GET", f"/records/{rid}/draft", token)
    if not dr.get("pids", {}).get("doi"): call("POST", f"/records/{rid}/draft/pids/doi", token); dr = call("GET", f"/records/{rid}/draft", token)
    call("PUT", f"/records/{rid}/draft", token, {"metadata": meta, "pids": dr["pids"], "files": {"enabled": True}, "access": {"record": "public", "files": "public"}})
    state.update(drafted=True, doi=dr["pids"]["doi"]["identifier"]); save(); print(json.dumps({"draft": rid, "doi": state["doi"]}))
elif step == "publish":
    rid = state["id"]
    if not state.get("published"): call("POST", f"/records/{rid}/draft/actions/publish", token); state["published"] = True; save()
    print(json.dumps({"record": rid, "doi": state["doi"]}))

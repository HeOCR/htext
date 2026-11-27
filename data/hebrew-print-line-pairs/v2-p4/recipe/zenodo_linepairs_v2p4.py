"""Zenodo v2-p3 as a new version of record 24575597 (concept 24571579): previous files imported, README replaced by the
HF tag v2-p3 README (commit 481edf6e), v2-p3 shard + manifest added, md5 read back. State in
~/.config/heocr/zenodo-production-linepairs-v2p4-state.json. Steps: draft | publish."""
import hashlib, json, os, sys, copy
from pathlib import Path
src = open(Path(__file__).parent / "zenodo_linepairs.py").read().replace("\nmain()\n", "\n")
z1 = {}; exec(compile(src, "zenodo_linepairs.py", "exec"), z1)
call = z1["call"]; HF = z1["HF"]
PREV, REV = "24580468", "be8f68ef74e0f79e4896e5887ee1d2455528811e"
STATE = Path.home() / ".config/heocr/zenodo-production-linepairs-v2p4-state.json"
SCR = Path("/private/tmp/claude-501/-Users-shaypalachy-agents-environments-opensource-projects-heocr/637d117b-830a-4c5a-b823-a43dddffc52a/scratchpad/v2p4pub")
PART = Path.home() / "temp/heocr/downloads/v2/parts/p4-ia-pby"
new = {"README.md": SCR / "README_p4.md", "v2-p4_manifest.json": SCR / "manifest_p4.json",
       **{f"v2-p4_train-0000{i}.parquet": PART / f"public/train-0000{i}.parquet" for i in range(4)}}
md5 = lambda p: "md5:" + hashlib.md5(p.read_bytes()).hexdigest()
token = os.environ["ZENODO_TOKEN"]
state = json.loads(STATE.read_text()) if STATE.exists() else {}
save = lambda: STATE.write_text(json.dumps(state, indent=2) + "\n")
step = sys.argv[1]
if step == "draft":
    prev = call("GET", f"/records/{PREV}", token)
    import urllib.request
    with urllib.request.urlopen(f"https://zenodo.org/api/records/{PREV}/files", timeout=120) as r_:
        prev_files = {e["key"]: e["checksum"] for e in json.loads(r_.read())["entries"]}
    if not state.get("id"):
        state["id"] = call("POST", f"/records/{PREV}/versions", token)["id"]; save()
    rid = state["id"]
    have = {e["key"]: e for e in call("GET", f"/records/{rid}/draft/files", token).get("entries", [])}
    if not have:
        call("POST", f"/records/{rid}/draft/actions/files-import", token); print("imported previous files", flush=True)
        have = {e["key"]: e for e in call("GET", f"/records/{rid}/draft/files", token)["entries"]}
    for key, p in new.items():
        if key in have and have[key].get("checksum") != md5(p):
            call("DELETE", f"/records/{rid}/draft/files/{key}", token); have.pop(key)
        if key not in have:
            call("POST", f"/records/{rid}/draft/files", token, [{"key": key}])
            call("PUT", f"/records/{rid}/draft/files/{key}/content", token, data=p.read_bytes(), ctype="application/octet-stream")
            call("POST", f"/records/{rid}/draft/files/{key}/commit", token); print("uploaded", key, flush=True)
    have = {e["key"]: e["checksum"] for e in call("GET", f"/records/{rid}/draft/files", token)["entries"]}
    want = {**{k: v for k, v in prev_files.items() if k not in new}, **{k: md5(p) for k, p in new.items()}}
    if have != want: raise SystemExit(f"draft differs: {set(have.items()) ^ set(want.items())}")
    meta = copy.deepcopy(prev["metadata"])
    meta["title"] = "Hebrew print line pairs v2-p4: OCR training lines from Hebrew Wikisource pages, whole-book edition pairs, Vilna Talmud regions, historical press and Ben-Yehuda works in their 1880-1930 printings (HeOCR)"
    meta["version"] = "v2-p4"; meta["publication_date"] = "2026-11-27"
    old = prev["metadata"]["related_identifiers"][0]["identifier"]
    d = meta["description"].replace(old, f"{HF}/tree/{REV}").replace("tag v2-p3<", "tag v2-p4<")
    meta["description"] = d + ("<p>v2 part 4 (files v2-p4_*): 64,235 lines from 79 Project Ben-Yehuda works on 30 Internet Archive "
        "books printed 1880–1930, each paired with its Ben-Yehuda transcription (public domain); images are faithful facsimiles of the "
        "original printings. Credit also Project Ben-Yehuda and its volunteers and the holding libraries.</p>")
    for r in meta["related_identifiers"]:
        if r["identifier"] == old: r["identifier"] = f"{HF}/tree/{REV}"
    dr = call("GET", f"/records/{rid}/draft", token)
    if not dr.get("pids", {}).get("doi"):
        call("POST", f"/records/{rid}/draft/pids/doi", token); dr = call("GET", f"/records/{rid}/draft", token)
    call("PUT", f"/records/{rid}/draft", token, {"metadata": meta, "pids": dr["pids"], "files": {"enabled": True}, "access": {"record": "public", "files": "public"}})
    state.update(drafted=True, doi=dr["pids"]["doi"]["identifier"]); save(); print(json.dumps({"draft": rid, "doi": state["doi"], "files": len(have)}))
elif step == "publish":
    rid = state["id"]
    if not state.get("published"):
        call("POST", f"/records/{rid}/draft/actions/publish", token); state["published"] = True; save()
    print(json.dumps({"record": rid, "doi": state["doi"]}))

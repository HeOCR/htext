"""Zenodo v2-p3 as a new version of record 24575597 (concept 24571579): previous files imported, README replaced by the
HF tag v2-p3 README (commit 481edf6e), v2-p3 shard + manifest added, md5 read back. State in
~/.config/heocr/zenodo-production-linepairs-v2p6-state.json. Steps: draft | publish."""
import hashlib, json, os, sys, copy
from pathlib import Path
src = open(Path(__file__).parent / "zenodo_linepairs.py").read().replace("\nmain()\n", "\n")
z1 = {}; exec(compile(src, "zenodo_linepairs.py", "exec"), z1)
call = z1["call"]; HF = z1["HF"]
PREV = "24600092"
REV = json.loads(Path("/Users/shaypalachy/temp/heocr/downloads/v2p6pub/hf_state.json").read_text())["commit_p4b"]
STATE = Path.home() / ".config/heocr/zenodo-production-linepairs-v2p6-state.json"
SCR = Path("/Users/shaypalachy/temp/heocr/downloads/v2p6pub")
PART = Path.home() / "temp/heocr/downloads/v2/parts/p6-vilna-volumes"
new = {"README.md": SCR / "README_v2p6b.md", "v2-p4b_manifest.json": SCR / "manifest_p4b.json",
       "v2-p4b_train-00000.parquet": Path.home() / "temp/heocr/downloads/v2/parts/p4b-ia-pby-pointed/public/train-00000.parquet", "v2-p6_manifest.json": SCR / "manifest_p6.json",
       **{f"v2-p6_train-0000{i}.parquet": PART / f"public/train-0000{i}.parquet" for i in range(6)},
       "v1.1_data_train-00001.parquet": SCR / "new/data/train-00001.parquet", "v1.1_data_train-00002.parquet": SCR / "new/data/train-00002.parquet",
       "v1.1_manifest.json": SCR / "new/manifest.json",
       "v2-p3_train-00000.parquet": SCR / "new/v2/p3-ops711-714/public/train-00000.parquet", "v2-p3_manifest.json": SCR / "new/v2/p3-ops711-714/manifest.json"}
md5 = lambda p: "md5:" + hashlib.md5(p.read_bytes()).hexdigest()
from htext.public_guard import assert_public_safe  # fail closed on custody material (htext#81)
assert_public_safe(new.values(), targets=new.keys())
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
    meta["title"] = "Hebrew print line pairs v2-p6: OCR training lines from Hebrew Wikisource pages, whole-book edition pairs, Vilna Talmud regions (15 tractates), historical press and Ben-Yehuda works in their 1880-1930 printings (HeOCR)"
    meta["version"] = "v2-p6"; meta["publication_date"] = "2026-11-27"
    old = prev["metadata"]["related_identifiers"][0]["identifier"]
    d = meta["description"].replace(old, f"{HF}/tree/{REV}").replace("tag v2-p4<", "tag v2-p4b<")
    meta["description"] = d.replace("47,997", "47,979").replace("9,492 lines", "8,960 lines") + ("<p>v2 part 6 (files v2-p6_*): 119,939 lines from 3,008 leaves "
        "of the Vilna Romm Talmud in 15 tractates, cut by region (Rashi 46,118, Tosafot 53,316, Gemara 20,505). Scans: public domain in Israel, "
        "digitized by Duke University Libraries, served by the Internet Archive. Rashi, Rashbam and Tosafot labels: the public-domain Vilna Edition "
        "in Sefaria. <b>Gemara labels: the Hebrew Wikisource Talmud Bavli via Sefaria, CC BY-SA 4.0. Attribute Hebrew Wikisource contributors "
        "(https://he.wikisource.org) and Sefaria; share alike.</b></p><p>Changes in this version: 550 rows removed for overlap with reserved "
        "evaluation material (532 in part 3, 18 in v1.1).</p><p>v2 part 4b (files v2-p4b_*): 12,001 lines of pointed (niqqud) print from 28 Project Ben-Yehuda works on 16 Internet Archive books printed 1880–1930; labels keep the niqqud; images public domain in Israel, text public domain.</p>")
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

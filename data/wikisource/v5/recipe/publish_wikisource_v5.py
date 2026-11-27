"""wikisource-v5: HF releases/wikisource-v5 in HeOCR/htext-wikisource (tag, anonymous sha256 readback), then a new Zenodo
version after record 24580528 (v4) with the ZIP (md5 read back). State ~/.config/heocr/wikisource-v5-state.json.
Usage: publish_wikisource_v5.py PKG_DIR"""
import copy, hashlib, json, os, sys
from pathlib import Path
P = Path(sys.argv[1]); d = P / "wikisource-v5"; z = P / "htext-wikisource-v5.zip"; repo = "HeOCR/htext-wikisource"
STATE = Path.home() / ".config/heocr/wikisource-v5-state.json"; st = json.loads(STATE.read_text()) if STATE.exists() else {}
save = lambda: STATE.write_text(json.dumps(st, indent=1))
def h(p, a="sha256"):
    x = hashlib.new(a)
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): x.update(b)
    return x.hexdigest()
from huggingface_hub import HfApi, CommitOperationAdd, hf_hub_download
api = HfApi(token=os.environ["HF_TOKEN"])
if not st.get("commit"):
    c = api.create_commit(repo, [CommitOperationAdd(f"releases/wikisource-v5/{f.name}", str(f)) for f in sorted(d.iterdir())], repo_type="dataset",
                          parent_commit=api.dataset_info(repo).sha, commit_message="wikisource-v5: 3,703,412 lines from 130 rights-proven works (CLEAN #1896)")
    api.create_tag(repo, tag="wikisource-v5", revision=c.oid, repo_type="dataset"); st["commit"] = c.oid; save()
for f in sorted(d.iterdir()):
    g = hf_hub_download(repo, f"releases/wikisource-v5/{f.name}", repo_type="dataset", revision=st["commit"], token=False, local_dir=str(P / ".rb"))
    assert h(g) == h(f), f.name; os.remove(g)
print("hf verified", st["commit"])
src = open(Path(__file__).parent / "zenodo_linepairs.py").read().replace("\nmain()\n", "\n"); z1 = {}; exec(compile(src, "z", "exec"), z1); call = z1["call"]
token = os.environ["ZENODO_TOKEN"]
if not st.get("zid"): st["zid"] = call("POST", "/records/24580528/versions", token)["id"]; save()
rid = st["zid"]; key = z.name
have = {e["key"]: e for e in call("GET", f"/records/{rid}/draft/files", token).get("entries", [])}
for k in list(have):
    if k != key or have[k].get("checksum") != "md5:" + h(z, "md5"): call("DELETE", f"/records/{rid}/draft/files/{k}", token); have.pop(k)
if key not in have:
    call("POST", f"/records/{rid}/draft/files", token, [{"key": key}])
    with open(z, "rb") as f: call("PUT", f"/records/{rid}/draft/files/{key}/content", token, data=f.read(), ctype="application/octet-stream")
    call("POST", f"/records/{rid}/draft/files/{key}/commit", token)
assert {e["key"]: e["checksum"] for e in call("GET", f"/records/{rid}/draft/files", token)["entries"]} == {key: "md5:" + h(z, "md5")}
m = copy.deepcopy(call("GET", "/records/24580528", token)["metadata"]); hf = f"https://huggingface.co/datasets/{repo}/tree/{st['commit']}/releases/wikisource-v5"
m.update(title="htext Wikisource B v5: Hebrew Wikisource main-namespace training lines, 130 public-domain works (HeOCR)", version="wikisource-v5",
         publication_date="2026-11-27",
         description=("<p>3,703,412 Hebrew OCR training lines (plain 3,292,731; pointed 410,681) from 130 public-domain works on Hebrew Wikisource "
                      "(all authors died by 1955). Lines already in other htext releases and in-corpus duplicates are removed; about 39% of the "
                      "content also appears in Sefaria with different line breaks or wording and is kept on purpose. HeOCR's CLEAN check kept every "
                      "line; lines sharing text with evaluation material are tagged privately and results are reported with and without them. "
                      "The attached ZIP contains the line files, line and rights indexes (revision-level attribution), NOTICE, corpus card, works "
                      f'list and SHA256SUMS. Text: Hebrew Wikisource contributors, CC BY-SA 4.0.</p><p><a href="{hf}">Hugging Face, identical package files</a></p>'))
for r in m.get("related_identifiers", []):
    if "huggingface.co" in r["identifier"]: r["identifier"] = hf
dr = call("GET", f"/records/{rid}/draft", token)
if not dr.get("pids", {}).get("doi"): call("POST", f"/records/{rid}/draft/pids/doi", token); dr = call("GET", f"/records/{rid}/draft", token)
call("PUT", f"/records/{rid}/draft", token, {"metadata": m, "pids": dr["pids"], "files": {"enabled": True}, "access": {"record": "public", "files": "public"}})
st["doi"] = dr["pids"]["doi"]["identifier"]; save()
if not st.get("published"): call("POST", f"/records/{rid}/draft/actions/publish", token); st["published"] = True; save()
print("zenodo published", st["doi"])

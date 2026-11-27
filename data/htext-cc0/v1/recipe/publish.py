"""Publish a staged unified tier: new public HF repo HeOCR/htext-<tier> (one commit, tag v1, anonymous sha256 readback
of every file), then a new Zenodo record with the ZIP (md5 read back). State: ~/.config/heocr/unified-tiers-state.json.
Usage: publish.py STAGE_DIR TIER hf|zenodo-draft|zenodo-publish"""
import copy, hashlib, json, os, sys
from pathlib import Path
STAGE, TIER, STEP = sys.argv[1:4]
STATE = Path.home() / ".config/heocr/unified-tiers-state.json"
state = json.loads(STATE.read_text()) if STATE.exists() else {}; st = state.setdefault(TIER, {})
save = lambda: STATE.write_text(json.dumps(state, indent=2) + "\n")
d = Path(STAGE) / f"htext-{TIER}"; repo = f"HeOCR/htext-{TIER}"
files = sorted(str(p.relative_to(d)) for p in d.rglob("*") if p.is_file())
def sha(p, algo="sha256"):
    h = hashlib.new(algo)
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()
if STEP == "hf":
    from huggingface_hub import HfApi, CommitOperationAdd, hf_hub_download
    api = HfApi(token=os.environ["HF_TOKEN"])
    if not st.get("commit"):
        api.create_repo(repo, repo_type="dataset", private=False, exist_ok=True)
        parent = api.dataset_info(repo).sha
        c = api.create_commit(repo, [CommitOperationAdd(f, str(d / f)) for f in files], repo_type="dataset", parent_commit=parent,
                              commit_message=f"htext-{TIER} v1: unified htext {TIER} text releases (see README)")
        api.create_tag(repo, tag="v1", revision=c.oid, repo_type="dataset"); st.update(commit=c.oid); save()
    bad = []
    for f in files:
        got = hf_hub_download(repo, f, repo_type="dataset", revision=st["commit"], token=False, local_dir=str(Path(STAGE) / ".readback" / TIER))
        if sha(got) != sha(d / f): bad.append(f)
        os.remove(got)
    if bad: raise SystemExit(f"readback mismatch {bad}")
    st["hf_verified"] = True; save(); print("hf verified", repo, st["commit"])
else:
    src = open(Path.home() / "agents/environments/opensource/projects/heocr/tasks/heocr-data/zenodo/zenodo_linepairs.py").read().replace("\nmain()\n", "\n")
    z1 = {}; exec(compile(src, "zenodo_linepairs.py", "exec"), z1); call = z1["call"]; token = os.environ["ZENODO_TOKEN"]
    z = Path(STAGE) / f"htext-{TIER}.zip"; key = z.name
    if STEP == "zenodo-draft":
        assert st.get("hf_verified")
        if not st.get("zid"): st["zid"] = call("POST", "/records", token, {"metadata": {}, "files": {"enabled": True}})["id"]; save()
        rid = st["zid"]
        have = {e["key"]: e for e in call("GET", f"/records/{rid}/draft/files", token).get("entries", [])}
        if key not in have or have[key].get("checksum") != "md5:" + sha(z, "md5"):
            if key in have: call("DELETE", f"/records/{rid}/draft/files/{key}", token)
            call("POST", f"/records/{rid}/draft/files", token, [{"key": key}])
            with open(z, "rb") as f: call("PUT", f"/records/{rid}/draft/files/{key}/content", token, data=f.read(), ctype="application/octet-stream")
            call("POST", f"/records/{rid}/draft/files/{key}/commit", token)
        have = {e["key"]: e["checksum"] for e in call("GET", f"/records/{rid}/draft/files", token)["entries"]}
        assert have == {key: "md5:" + sha(z, "md5")}, have
        base = call("GET", "/records/24581317", token)["metadata"]  # an htext record: creators, publisher, resource type
        man = json.load(open(d / "build_manifest.json")); hf = f"https://huggingface.co/datasets/{repo}/tree/{st['commit']}"
        lic = {"cc0": "cc0-1.0", "by": "cc-by-4.0", "by-sa": "cc-by-sa-4.0"}[TIER]
        m = copy.deepcopy(base); m.update(title=f"htext-{TIER}: all {TIER.upper()} htext Hebrew OCR text releases, merged (HeOCR)", version="v1",
            publication_date="2026-11-27", rights=[{"id": lic}],
            description=(f"<p>{man['stats']['rows_out']:,} Hebrew OCR training lines: every published htext release under this licence "
                         f"({', '.join(man['order'])}), merged and exact-deduplicated, as zstd parquet. The attached ZIP holds the parquet "
                         "shards, README (columns, components pinned by Hugging Face commit and DOI, per-source counts), NOTICE, the build "
                         "manifest, recipe and SHA256SUMS. No new CLEAN was needed: every component passed HeOCR's CLEAN check, and the "
                         "union passed a work-level screen against the current evaluation reservations. Lines sharing text with HeOCR "
                         f'evaluation material are tagged in private sidecars and results are reported with and without them.</p><p><a href="{hf}">'
                         "Hugging Face, identical files</a></p>"),
            related_identifiers=[{"identifier": hf, "scheme": "url", "relation_type": {"id": "isidenticalto"}, "resource_type": {"id": "dataset"}}])
        dr = call("GET", f"/records/{rid}/draft", token)
        if not dr.get("pids", {}).get("doi"): call("POST", f"/records/{rid}/draft/pids/doi", token); dr = call("GET", f"/records/{rid}/draft", token)
        call("PUT", f"/records/{rid}/draft", token, {"metadata": m, "pids": dr["pids"], "files": {"enabled": True}, "access": {"record": "public", "files": "public"}})
        st.update(doi=dr["pids"]["doi"]["identifier"]); save(); print("drafted", TIER, st["doi"])
    elif STEP == "zenodo-publish":
        if not st.get("zpublished"): call("POST", f"/records/{st['zid']}/draft/actions/publish", token); st["zpublished"] = True; save()
        print("published", TIER, st["doi"])

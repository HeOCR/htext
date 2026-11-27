"""Publish the staged Sefaria v3 / Gutenberg v1 packages to HF, tag, and read every file back anonymously (sha256).
State: ~/.config/heocr/hf-sefaria-v3-state.json. Usage: hf_publish.py PUBLISH_DIR"""
import hashlib, json, os, sys
from pathlib import Path
from huggingface_hub import HfApi, CommitOperationAdd, hf_hub_download
P = Path(sys.argv[1]); api = HfApi(token=os.environ["HF_TOKEN"])
STATE = Path.home() / ".config/heocr/hf-sefaria-v3-state.json"
state = json.loads(STATE.read_text()) if STATE.exists() else {}
JOBS = [("sefaria-v3-cc0", "HeOCR/htext-sefaria", "releases/sefaria-v3-cc0", False),
        ("sefaria-v3-by", "HeOCR/htext-sefaria-by", "releases/sefaria-v3-by", False),
        ("sefaria-v3-by-sa", "HeOCR/htext-sefaria-by-sa", "", True),
        ("gutenberg-v1", "HeOCR/htext-gutenberg", "", True)]
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()
for name, repo, prefix, new in JOBS:
    if state.get(name, {}).get("verified"): print("done", name, state[name]["commit"]); continue
    d = P / name
    if new and not state.get(name, {}).get("created"):
        api.create_repo(repo, repo_type="dataset", private=False, exist_ok=True)
        state[name] = {"created": True}; STATE.write_text(json.dumps(state, indent=2))
    if not state.get(name, {}).get("commit"):
        parent = api.dataset_info(repo).sha
        ops = [CommitOperationAdd(f"{prefix}/{f.name}" if prefix else f.name, str(f)) for f in sorted(d.iterdir())]
        c = api.create_commit(repo, ops, repo_type="dataset", parent_commit=parent,
                              commit_message=f"{name}: htext release (CLEAN-checked; see README)")
        api.create_tag(repo, tag=name, revision=c.oid, repo_type="dataset")
        state.setdefault(name, {}).update(commit=c.oid, parent=parent); STATE.write_text(json.dumps(state, indent=2))
    rev = state[name]["commit"]; bad = []
    for f in sorted(d.iterdir()):
        path = f"{prefix}/{f.name}" if prefix else f.name
        got = hf_hub_download(repo, path, repo_type="dataset", revision=rev, token=False, local_dir=str(P / ".readback" / name))
        if sha(got) != sha(f): bad.append(f.name)
        os.remove(got)
    if bad: raise SystemExit(f"{name}: readback mismatch {bad}")
    state[name]["verified"] = True; STATE.write_text(json.dumps(state, indent=2)); print("verified", name, repo, rev, flush=True)

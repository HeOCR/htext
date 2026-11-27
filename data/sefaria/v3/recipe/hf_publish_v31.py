"""sefaria-v3.1-cc0 on HF: add releases/sefaria-v3.1-cc0 (tag sefaria-v3.1-cc0, anonymous readback), then a separate commit
removing releases/sefaria-v3-cc0/ from main (history keeps it). State in ~/.config/heocr/hf-sefaria-v3-state.json."""
import hashlib, json, os, sys
from pathlib import Path
from huggingface_hub import HfApi, CommitOperationAdd, CommitOperationDelete, hf_hub_download
P = Path(sys.argv[1]) / "sefaria-v3.1-cc0"; api = HfApi(token=os.environ["HF_TOKEN"]); repo = "HeOCR/htext-sefaria"
STATE = Path.home() / ".config/heocr/hf-sefaria-v3-state.json"; state = json.loads(STATE.read_text()); st = state.setdefault("sefaria-v3.1-cc0", {})
save = lambda: STATE.write_text(json.dumps(state, indent=1))
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()
if not st.get("commit"):
    parent = api.dataset_info(repo).sha
    c = api.create_commit(repo, [CommitOperationAdd(f"releases/sefaria-v3.1-cc0/{f.name}", str(f)) for f in sorted(P.iterdir())], repo_type="dataset",
                          parent_commit=parent, commit_message="sefaria-v3.1-cc0: supersedes sefaria-v3-cc0 (reserved eval work removed)")
    api.create_tag(repo, tag="sefaria-v3.1-cc0", revision=c.oid, repo_type="dataset"); st.update(commit=c.oid, parent=parent); save()
for f in sorted(P.iterdir()):
    got = hf_hub_download(repo, f"releases/sefaria-v3.1-cc0/{f.name}", repo_type="dataset", revision=st["commit"], token=False, local_dir=str(P.parent / ".readback"))
    assert sha(got) == sha(f), f.name; os.remove(got)
st["verified"] = True; save(); print("verified", st["commit"])
if not st.get("v3_removed_commit"):
    c = api.create_commit(repo, [CommitOperationDelete("releases/sefaria-v3-cc0/")], repo_type="dataset", parent_commit=st["commit"],
                          commit_message="withdraw sefaria-v3-cc0 from main: superseded by sefaria-v3.1-cc0 (reserved eval work removed); history and tag sefaria-v3-cc0 keep it")
    st["v3_removed_commit"] = c.oid; save()
left = [f.path for f in api.list_repo_tree(repo, repo_type="dataset", recursive=True) if f.path.startswith("releases/sefaria-v3-cc0")]
print("v3 removed from main:", st["v3_removed_commit"], "remaining:", left)

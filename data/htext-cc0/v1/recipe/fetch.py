"""Fetch every component release of the unified htext tiers at its pinned HF revision (anonymous), recording sha256.
Usage: fetch.py OUT_DIR"""
import hashlib, json, os, sys
from huggingface_hub import HfApi, hf_hub_download
OUT = sys.argv[1]; api = HfApi()
C = [  # name, tier, repo, revision, path prefix
 ("pby-v1.1", "cc0", "HeOCR/htext-pby", "pby-v1.1", "data/"), ("pby-v2.1", "cc0", "HeOCR/htext-pby", "pby-v2.1", "data/"),
 ("pby-v3.1", "cc0", "HeOCR/htext-pby", "pby-v3.1", "data/"), ("tanakh-v1.1", "cc0", "HeOCR/htext-tanakh", "tanakh-v1.1", "data/"),
 ("knesset-laws-v2", "cc0", "HeOCR/htext-knesset-laws", "knesset-laws-v2", "data/"),
 ("knesset-plenary-v1", "cc0", "HeOCR/htext-knesset-plenary", "knesset-plenary-v1", "data/"),
 ("sefaria-v1", "cc0", "HeOCR/htext-sefaria", "2572e399c910cbfe6410830cc93360b192c14728", ""),
 ("sefaria-v2-cc0", "cc0", "HeOCR/htext-sefaria", "a92766c9fb4955b1f9fcb3766430cd5522af7614", "releases/sefaria-v2-cc0/"),
 ("sefaria-v3-cc0", "cc0", "HeOCR/htext-sefaria", "8da7fb539e9ac8fc40c4f6e4f7073cb9a575bb38", "releases/sefaria-v3-cc0/"),
 ("tsel-haolam-v1", "cc0", "HeOCR/htext-tsel-haolam", "c95c9a349a1f9a9d1972489c1b1d25b23fc24dbb", ""),
 ("gutenberg-v1", "cc0", "HeOCR/htext-gutenberg", "1f7432ee0240c0a23b44347cb1612c454fe78eed", ""),
 ("sefaria-v2-by", "by", "HeOCR/htext-sefaria-by", "e28fae17d635f72ad6c9a628734252c1ea219e24", ""),
 ("sefaria-v3-by", "by", "HeOCR/htext-sefaria-by", "c55b5dcbc79b360b87031a1fa7aca029b62d25f0", "releases/sefaria-v3-by/"),
 ("wikisource-v1", "by-sa", "HeOCR/htext-wikisource", "wikisource-v1", "data/"),
 ("wikisource-v2", "by-sa", "HeOCR/htext-wikisource", "efcf3e55bedd7a17e6eef7db02afd4c5f6447144", "releases/wikisource-v2/"),
 ("wikisource-v3", "by-sa", "HeOCR/htext-wikisource", "b7766502d9d297176925da620b01e357ad0f4ec6", "releases/wikisource-v3/"),
 ("wikisource-v4", "by-sa", "HeOCR/htext-wikisource", "a5ee2ac15051447d571e027c87c9512317cce919", "releases/wikisource-v4/"),
 ("sefaria-v3-by-sa", "by-sa", "HeOCR/htext-sefaria-by-sa", "1d24204f8bd53d3abc214619a2b73cd731552b5e", "")]
man = {}
for name, tier, repo, rev, pref in C:
    commit = api.dataset_info(repo, revision=rev).sha
    files = [f.path for f in api.list_repo_tree(repo, repo_type="dataset", revision=commit, recursive=True)
             if hasattr(f, "size") and f.path.startswith(pref) and ("/" not in f.path[len(pref):]) and
             f.path.endswith((".txt", ".jsonl", ".jsonl.gz", ".tsv.gz")) and "eye_check" not in f.path]
    d = os.path.join(OUT, name); os.makedirs(d, exist_ok=True); rec = {}
    for p in files:
        dst = os.path.join(d, os.path.basename(p))
        if not os.path.exists(dst):
            got = hf_hub_download(repo, p, repo_type="dataset", revision=commit, token=False, local_dir=os.path.join(OUT, ".dl"))
            os.replace(got, dst)
        h = hashlib.sha256()
        with open(dst, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
        rec[os.path.basename(p)] = {"path": p, "sha256": h.hexdigest(), "bytes": os.path.getsize(dst)}
    man[name] = {"tier": tier, "repo": repo, "revision": rev, "commit": commit, "files": rec}
    print(name, commit[:10], len(rec), "files", flush=True)
    json.dump(man, open(os.path.join(OUT, "components.json"), "w"), indent=1)
print("done")

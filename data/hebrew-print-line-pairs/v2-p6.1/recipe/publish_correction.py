"""Publish the corrected v2 parts 1, 3 and 4 as v2-p6.1 (lead GO 2026-11-28). Text changes only; images unchanged.
Steps: stage | hf | zenodo-draft | zenodo-publish. Tokens HF_TOKEN / ZENODO_TOKEN from the environment, never printed.
State: ~/.config/heocr/linepairs-v2p61-state.json."""
import hashlib, json, os, sys, urllib.error, urllib.request
from pathlib import Path
from htext.public_guard import assert_public_safe, private_tokens  # fail closed on custody material (htext#81)

PARTS = {"p1-ops707": "v2-p1", "p3-ops711-714": "v2-p3", "p4-ia-pby": "v2-p4"}
ROOT = Path.home() / "temp/heocr/downloads/v2/parts-corrected"
STAGE = ROOT / "stage"
STATE = Path.home() / ".config/heocr/linepairs-v2p61-state.json"
REPO, TAG, PREV = "HeOCR/hebrew-print-line-pairs", "v2-p6.1", "24615586"
BASE_REV = "d3cbbd551763f1ce86f22b1e37ee80efa73a8b47"  # main: v2-p4b data plus the niqqud caveat
OLD_LINK_REV = "dca089016e6cc389997b533cbf5cee4fcc3df2a3"
CLEAN_NOTE = ("No new CLEAN check was needed: only label text was removed, and no image or text was added, "
              "so the earlier CLEAN check of this part still holds.")
CHANGE = ("v2-p6.1 corrects the labels of v2 parts 1, 3 and 4. Niqqud and cantillation marks were stripped from 1,963 "
          "rows that were mostly unpointed in print (marks on under 30% of letters in parts 1 and 4, under 10% in "
          "part 3). 516 more heavily marked rows (5 in part 1, 511 in part 3) are omitted pending a check against the "
          "scans. Images and all other columns are unchanged. No new CLEAN check was needed: only label text was "
          "removed from rows that had already passed it. New training uses should take these parts from v2-p6.1 or later.")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
state = json.loads(STATE.read_text()) if STATE.exists() else {}
save = lambda: STATE.write_text(json.dumps(state, indent=2) + "\n")


def once(s, old, new):
    assert s.count(old) == 1, (old, s.count(old))
    return s.replace(old, new)


def hf_files():
    """{path in the HF repo: local file}"""
    out = {"README.md": STAGE / "README.md"}
    for part in PARTS:
        d = ROOT / part
        for f in [d / "manifest.json", d / "CHANGELOG.md", *sorted(d.glob("public/*.parquet"))]:
            out[f"v2/{part}/{f.relative_to(d)}"] = f
    return out


def guard(files, targets):
    """The guard, file by file. The only identifiers allowed are those already public in the same file at BASE_REV
    (a part's own source scans, its CLEAN record reference, digits inside a published hash). A new one still fails."""
    toks = private_tokens()
    assert toks, "HTEXT_PRIVATE_EXCLUSIONS must name the private exclusion file"
    for path, target in zip(files, targets):
        hf_path = next(k for k, v in hf_files().items() if v == path)
        allow = set()
        if path.suffix in (".json", ".md") and path.name != "CHANGELOG.md":
            url = f"https://huggingface.co/datasets/{REPO}/raw/{BASE_REV}/{hf_path}"
            old = urllib.request.urlopen(url, timeout=120).read().decode()
            allow = {t for t in toks if t in old}
        assert_public_safe([path], targets=[target], tokens=toks, allow_tokens=allow)


def zen_key(path):
    if path == "README.md":
        return path
    part, rest = path[3:].split("/", 1)
    return f"{PARTS[part]}_{rest.split('/')[-1]}"


def stage():
    STAGE.mkdir(exist_ok=True)
    for part in PARTS:
        d = ROOT / part
        m = json.load(open(d / "manifest.json"))
        for name, s in m["shards"].items():
            assert sha(d / name) == s["sha256"]
        log = (d / "CHANGELOG.md").read_text()
        if CLEAN_NOTE not in log:
            log = log.replace("These rows had marks", "These rows were mostly unpointed in print: they had marks")
            (d / "CHANGELOG.md").write_text(log + f"- {CLEAN_NOTE}\n")
    url = f"https://huggingface.co/datasets/{REPO}/raw/{BASE_REV}/README.md"
    card = urllib.request.urlopen(url, timeout=120).read().decode()
    card = once(card, "**What:** 15,248 lines", "**What:** 15,243 lines")
    card = once(card, "**What:** 8,960 lines", "**What:** 8,449 lines")
    card = once(card, "315 lines (Ben-Yehuda work 1282", "In the original build, 315 lines (Ben-Yehuda work 1282")
    card = once(card, "## Changes in this version\n", f"## Changes in this version\n{CHANGE}\n\n## Changes in v2-p6\n")
    (STAGE / "README.md").write_text(card)
    files = hf_files()
    targets = [*files, *map(zen_key, files)]
    guard([*files.values()] * 2, targets)
    assert not any("held_ids" in str(p) for p in files.values())
    print("staged and passed the public guard:", len(files), "files")


def hf():
    from huggingface_hub import HfApi, CommitOperationAdd
    files = hf_files()
    guard(list(files.values()), list(files))
    api = HfApi(token=os.environ["HF_TOKEN"])
    if not state.get("hf_commit"):
        c = api.create_commit(REPO, [CommitOperationAdd(k, str(v)) for k, v in files.items()], repo_type="dataset",
                              parent_commit=BASE_REV,
                              commit_message="v2-p6.1: niqqud correction of v2 parts 1, 3 and 4 (label text only)")
        state["hf_commit"] = c.oid; save()
        api.create_tag(REPO, tag=TAG, revision=c.oid, repo_type="dataset")
    anon = HfApi(token=False)
    info = anon.dataset_info(REPO, revision=TAG, files_metadata=True)
    assert info.sha == state["hf_commit"]
    have = {s.rfilename: s for s in info.siblings}
    for k, v in files.items():
        s = have[k]
        if s.lfs:
            assert s.lfs.sha256 == sha(v), k
        else:
            raw = v.read_bytes()
            assert s.blob_id == hashlib.sha1(b"blob %d\0" % len(raw) + raw).hexdigest(), k
    print("HF", TAG, state["hf_commit"], "- anonymous readback matched", len(files), "files")


BASE, RDM = "https://zenodo.org/api", "application/vnd.inveniordm.v1+json"


def call(method, path, body=None, data=None, ctype="application/json"):
    if body is not None:
        data = json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={
        "Authorization": "Bearer " + os.environ["ZENODO_TOKEN"], "Accept": RDM,
        **({} if data is None else {"Content-Type": ctype})})
    try:
        with urllib.request.urlopen(req, timeout=3600) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path}: HTTP {e.code}: {e.read(1500).decode('utf-8', 'replace')}") from None
    return json.loads(raw) if raw.strip() else {}


def md5(p):
    return "md5:" + hashlib.md5(Path(p).read_bytes()).hexdigest()


def public_files(rec):
    d = json.load(urllib.request.urlopen(f"{BASE}/records/{rec}/files", timeout=120))
    return {e["key"]: e["checksum"] for e in d["entries"]}


def wanted():
    new = {zen_key(k): v for k, v in hf_files().items()}
    return new, {**public_files(PREV), **{k: md5(v) for k, v in new.items()}}


def zenodo_draft():
    rev = state["hf_commit"]
    new, want = wanted()
    guard(list(new.values()), list(new))
    if not state.get("record"):
        state["record"] = call("POST", f"/records/{PREV}/versions")["id"]; save()
    rid = state["record"]
    have = {e["key"]: e for e in call("GET", f"/records/{rid}/draft/files").get("entries", [])}
    if not have:
        call("POST", f"/records/{rid}/draft/actions/files-import")
        have = {e["key"]: e for e in call("GET", f"/records/{rid}/draft/files")["entries"]}
    for key, p in new.items():
        if key in have and have[key].get("checksum") != md5(p):
            call("DELETE", f"/records/{rid}/draft/files/{key}"); have.pop(key)
        if key not in have:
            call("POST", f"/records/{rid}/draft/files", [{"key": key}])
            call("PUT", f"/records/{rid}/draft/files/{key}/content", data=p.read_bytes(), ctype="application/octet-stream")
            call("POST", f"/records/{rid}/draft/files/{key}/commit"); print("uploaded", key, flush=True)
    got = {e["key"]: e["checksum"] for e in call("GET", f"/records/{rid}/draft/files")["entries"]}
    if got != want:
        raise SystemExit(f"draft differs in {sorted(k for k, _ in set(got.items()) ^ set(want.items()))}")
    prev = call("GET", f"/records/{PREV}")
    meta = prev["metadata"]
    meta["title"] = once(meta["title"], "line pairs v2-p6:", "line pairs v2-p6.1:")
    meta["version"] = TAG
    meta["publication_date"] = "2026-11-28"
    d = meta["description"]
    d = once(d, f'{OLD_LINK_REV}">HeOCR/hebrew-print-line-pairs, tag v2-p4b<', f'{rev}">HeOCR/hebrew-print-line-pairs, tag {TAG}<')
    d = once(d, "15,248 lines from 21", "15,243 lines from 21")
    d = once(d, "8,960 lines from 352", "8,449 lines from 352")
    meta["description"] = d + f"<p>{CHANGE}</p>"
    for r in meta["related_identifiers"]:
        r["identifier"] = r["identifier"].replace(OLD_LINK_REV, rev)
    dr = call("GET", f"/records/{rid}/draft")
    if not dr.get("pids", {}).get("doi"):
        call("POST", f"/records/{rid}/draft/pids/doi"); dr = call("GET", f"/records/{rid}/draft")
    call("PUT", f"/records/{rid}/draft", {"metadata": meta, "pids": dr["pids"], "files": {"enabled": True},
                                          "access": {"record": "public", "files": "public"}})
    state["doi"] = dr["pids"]["doi"]["identifier"]; state["files"] = want; save()
    print(json.dumps({"draft": rid, "doi": state["doi"], "files": len(got)}))


def zenodo_publish():
    rid = state["record"]
    if not state.get("published"):
        call("POST", f"/records/{rid}/draft/actions/publish"); state["published"] = True; save()
    assert public_files(rid) == state["files"]
    rec = json.load(urllib.request.urlopen(f"{BASE}/records/{rid}", timeout=120))
    assert rec["metadata"]["version"] == TAG and CHANGE in rec["metadata"]["description"]
    print("Zenodo", rid, state["doi"], "- anonymous readback matched", len(state["files"]), "files")


{"stage": stage, "hf": hf, "zenodo-draft": zenodo_draft, "zenodo-publish": zenodo_publish}[sys.argv[1]]()

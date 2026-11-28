"""Add the niqqud caveat (lead 2026-11-28) to the published cards of the line-pair releases with marked Ben-Yehuda
labels (v2 parts 1, 3, 4, 4b) and of the pointed model trained on part 4b. Text only: no data file changes.
Idempotent. Tokens HF_TOKEN and ZENODO_TOKEN from the environment, never printed.

Usage: apply_caveat.py [--apply]   (without --apply it only reports what would change)"""
import json, sys, os, urllib.error, urllib.request
from huggingface_hub import CommitOperationAdd, HfApi, hf_hub_download

SENTENCE = ("Niqqud in these labels follows the Project Ben-Yehuda text; it has not been verified mark by mark "
            "against the printed scan.")
APPLY = "--apply" in sys.argv
HF_CARDS = [  # (repo type, repo, heading)
    ("dataset", "HeOCR/hebrew-print-line-pairs", "Niqqud in Ben-Yehuda labels (v2 parts 1, 3, 4 and 4b)"),
    ("model", "HeOCR/heocr-pointed-measured", "Training-data note"),
]
# every published Zenodo version that carries one of those parts, plus the pointed model
ZENODO = {"24574729": "(v2 part 1)", "24575597": "(v2 part 1)", "24580468": "(v2 parts 1 and 3)",
          "24600092": "(v2 parts 1, 3 and 4)", "24615586": "(v2 parts 1, 3, 4 and 4b)", "24620184": "(training data)"}
BASE, RDM = "https://zenodo.org/api", "application/vnd.inveniordm.v1+json"


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(), method=method,
                                 headers={"Authorization": "Bearer " + os.environ["ZENODO_TOKEN"], "Accept": RDM,
                                          **({} if body is None else {"Content-Type": "application/json"})})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path}: HTTP {e.code}: {e.read(1000).decode('utf-8', 'replace')}") from None
    return json.loads(raw) if raw.strip() else {}


def hf():
    api = HfApi(token=os.environ.get("HF_TOKEN") if APPLY else False)
    for kind, repo, heading in HF_CARDS:
        head = api.repo_info(repo, repo_type=kind).sha
        path = hf_hub_download(repo, "README.md", repo_type=kind, revision=head, token=False)
        card = open(path, encoding="utf-8").read()
        if SENTENCE in card:
            print(repo, "already has the caveat"); continue
        block = f"## {heading}\n\n{SENTENCE}\n\n"
        # before the first level-2 section, so it is read with the introduction
        at = card.find("\n## ")
        new = card + "\n" + block if at < 0 else card[:at + 1] + block + card[at + 1:]
        if not APPLY:
            print(repo, "would add the caveat at offset", at); continue
        c = api.create_commit(repo, [CommitOperationAdd("README.md", new.encode())], repo_type=kind, parent_commit=head,
                              commit_message="docs: niqqud caveat for Ben-Yehuda labels")
        back = hf_hub_download(repo, "README.md", repo_type=kind, revision=c.oid, token=False)
        assert open(back, encoding="utf-8").read() == new
        print(repo, "updated", c.oid)


def zenodo():
    for rec, scope in ZENODO.items():
        public = json.load(urllib.request.urlopen(f"{BASE}/records/{rec}", timeout=120))
        if SENTENCE in public["metadata"]["description"]:
            print(rec, "already has the caveat"); continue
        if not APPLY:
            print(rec, "would add the caveat", scope); continue
        before = {f["key"]: f["checksum"] for f in public["files"]}
        draft = call("POST", f"/records/{rec}/draft")  # metadata edit of a published version
        meta = draft["metadata"]
        meta["description"] += f"<p>{SENTENCE} {scope}</p>"
        call("PUT", f"/records/{rec}/draft", {"metadata": meta, "pids": draft["pids"], "files": {"enabled": True},
                                              "access": draft["access"]})
        call("POST", f"/records/{rec}/draft/actions/publish")
        after = json.load(urllib.request.urlopen(f"{BASE}/records/{rec}", timeout=120))
        assert SENTENCE in after["metadata"]["description"]
        assert {f["key"]: f["checksum"] for f in after["files"]} == before
        print(rec, "updated; files unchanged")


hf()
zenodo()

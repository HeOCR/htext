"""Fold opensrc's Wikisource B candidates v4 + v5 (CLEAN heocr-restricted-eval#1714, all 16 pages TRAIN CLEAN) into
htext wikisource-v4: verify pinned inputs, drop in-corpus duplicates (first wins: v4, then v5, in file order) and lines
already in any live htext release or the pending Sefaria v3 / Gutenberg tranche (mark-stripped exact match), rewrite
line index + rights index line ranges, write card + NOTICE + SHA256SUMS.
Usage: fold.py CAND_ROOT DEDUP_DIR [--dedup-extra FILE ...] OUT
"""
import argparse, collections, gzip, hashlib, json, sys
from pathlib import Path
from htext.hebrew import strip_marks

ap = argparse.ArgumentParser(); ap.add_argument("cand_root", type=Path); ap.add_argument("dedup_dir", type=Path)
ap.add_argument("--dedup-extra", type=Path, action="append", default=[]); ap.add_argument("--exclude-pages", type=Path, default=None); ap.add_argument("out", type=Path)
a = ap.parse_args()
PINS = {"v4": "94cbc049929ced304fafe3fa32a857f655fb4c7716850044570c45c609e3dc15",
        "v5": "f806e8f3303ee315c9e9bf45cf373f234d1a0df589a43233847a074bc0ed6110"}
sha = lambda b: hashlib.sha256(b).hexdigest()
cands = []
for v, pin in PINS.items():
    d = a.cand_root / f"wiki-b-{v}"; h = (d / "candidate-handoff.json").read_bytes(); assert sha(h) == pin, v
    hj = json.loads(h)
    for name, p in hj["candidate_pins"].items():
        assert sha((d / "candidate" / name).read_bytes()) == p["sha256"], (v, name)
    lines = (d / "candidate" / f"wikisource_plain_{v}.txt").read_text(encoding="utf-8").splitlines()
    assert (d / "candidate" / f"wikisource_niqqud_{v}.txt").read_bytes() == b""
    idx = [json.loads(x) for x in gzip.decompress((d / "candidate" / "wikisource_line_index.v1.jsonl.gz").read_bytes()).splitlines()]
    rights = [json.loads(x) for x in gzip.decompress((d / "candidate" / "wikisource_rights_index.v1.jsonl.gz").read_bytes()).splitlines()]
    assert len(idx) == len(lines) and all(sha(l.encode()) == r["sha256"] for l, r in zip(lines, idx)), v
    card = json.loads((d / "candidate" / "corpus_card.json").read_text(encoding="utf-8"))
    cands.append((v, pin, lines, idx, rights, card))
EXCL = json.loads(a.exclude_pages.read_text(encoding="utf-8")) if a.exclude_pages else {}
key = lambda s: strip_marks(s.strip())
want = {key(l) for c in cands for l in c[2]}
hits = collections.defaultdict(set); dedup_inputs = []
for f in sorted(a.dedup_dir.glob("*.txt")) + a.dedup_extra:
    hsh = hashlib.sha256(); n = 0
    with open(f, "rb") as fh:
        for raw in fh:
            hsh.update(raw); n += 1
            s = raw.decode("utf-8").rstrip("\n")
            if s and key(s) in want: hits[key(s)].add(f.name)
    dedup_inputs.append({"file": f.name, "lines": n, "sha256": hsh.hexdigest()}); print("scanned", f.name, n, flush=True)
seen, out_lines, out_idx, stats = set(), [], [], collections.Counter()
page_new = collections.defaultdict(list)
for v, pin, lines, idx, rights, card in cands:
    for l, r in zip(lines, idx):
        if r["unit_id"].removeprefix("ws_page_") in EXCL: stats["dropped:page_excluded_corpus_quality"] += 1; continue
        k = key(l)
        if k in hits: stats["dropped:prior_release_duplicate"] += 1; continue
        if k in seen: stats["dropped:in_corpus_duplicate"] += 1; continue
        seen.add(k); out_lines.append(l); out_idx.append({**r, "file": "wikisource_plain_v4.txt", "candidate": v})
        page_new[r["unit_id"]].append(len(out_lines))
stats["lines_out"] = len(out_lines); stats["lines_in"] = sum(len(c[2]) for c in cands)
out_rights, works = [], set()
for v, pin, lines, idx, rights, card in cands:
    for r in rights:
        uid = f"ws_page_{r['page_id']}"; ln = page_new.get(uid, [])
        if not ln:
            stats["pages_excluded" if str(r["page_id"]) in EXCL else "pages_emptied"] += 1; continue
        assert ln == list(range(ln[0], ln[0] + len(ln))), uid
        out_rights.append({**r, "line_ranges": {"plain": {"first_line": ln[0], "lines": len(ln)}}, "candidate": v})
a.out.mkdir(parents=True, exist_ok=True)
def w(name, b): (a.out / name).write_bytes(b); return sha(b)
files = {"wikisource_plain_v4.txt": w("wikisource_plain_v4.txt", "".join(x + "\n" for x in out_lines).encode()),
         "wikisource_niqqud_v4.txt": w("wikisource_niqqud_v4.txt", b"")}
gz = lambda rows: gzip.compress("".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in rows).encode(), mtime=0)
files["wikisource_line_index.v1.jsonl.gz"] = w("wikisource_line_index.v1.jsonl.gz", gz(out_idx))
files["wikisource_rights_index.v1.jsonl.gz"] = w("wikisource_rights_index.v1.jsonl.gz", gz(out_rights))
base = cands[1][5]
card = {**{k: v for k, v in base.items() if k not in ("corpus_version", "release", "eval_overlap_drop")},
        "corpus_version": "v4", "name": "htext Wikisource B v4: Hebrew Wikisource main-namespace training lines",
        "release": {**base["release"], "entries_admitted": len(out_rights)},
        "folded_candidates": [{"candidate": v, "handoff_sha256": pin, "builder_git": None, "lines": len(l), "pages": len(r)} for v, pin, l, i, r, c in cands],
        "train_clean": {"record": "HeOCR/heocr-restricted-eval#1714", "merge_commit": "f4070238", "train_clean_code": "a8e14c7e",
                        "policy": "contamination v2 amendment 1 (text matches are tags, kept in a private sidecar)",
                        "pages": {"v4": "2/2 kept", "v5": "14/14 kept"}},
        "pages_excluded_corpus_quality": EXCL,
        "dedup": {"key": "htext.hebrew.strip_marks, exact", "against": dedup_inputs, "stats": dict(stats)},
        "totals": {"plain": len(out_lines), "niqqud": 0, "lines": len(out_lines), "pages": len(out_rights)},
        "files": {k: {"sha256": v} for k, v in files.items()},
        "known_limitations": ["No paired scans are included.", "Unproofread against print. Preserve revision-level attribution and NOTICE."]}
for i, (v, pin, l, ix, r, c) in enumerate(cands):
    card["folded_candidates"][i]["builder_git"] = json.loads((a.cand_root / f"wiki-b-{v}" / "candidate-handoff.json").read_text()).get("builder_git")
files["corpus_card.json"] = w("corpus_card.json", (json.dumps(card, ensure_ascii=False, indent=1) + "\n").encode())
files["NOTICE.md"] = w("NOTICE.md", (a.cand_root / "wiki-b-v5" / "candidate" / "NOTICE.md").read_bytes())
w("SHA256SUMS", "".join(f"{v}  {k}\n" for k, v in sorted(files.items())).encode())
print(json.dumps({"stats": stats, "pages": len(out_rights)}, ensure_ascii=False))

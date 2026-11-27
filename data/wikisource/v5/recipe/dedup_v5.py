"""wikisource-v5: drop lines already in any published htext release (the unified htext-cc0/by/by-sa v1 parquet) and
in-corpus duplicates; mark-stripped exact match. Rewrites line index and rights-index line ranges.
Usage: dedup_v5.py BUILD_DIR UNIFIED_STAGE_DIR OUT_DIR"""
import collections, glob, gzip, hashlib, json, os, sys
import pyarrow.parquet as pq
from htext.hebrew import strip_marks
B, U, O = sys.argv[1:4]; os.makedirs(O, exist_ok=True)
key = lambda s: hashlib.blake2b(strip_marks(s.strip()).encode(), digest_size=8).digest()
files = ["wikisource_plain_v5.txt", "wikisource_niqqud_v5.txt"]
lines = {f: open(os.path.join(B, f), encoding="utf-8").read().splitlines() for f in files}
idx = [json.loads(l) for l in gzip.open(os.path.join(B, "wikisource_line_index.v1.jsonl.gz"), "rt", encoding="utf-8")]
by_file = collections.defaultdict(list)
for r in idx: by_file[r["file"]].append(r)
for f in files: assert len(by_file[f]) == len(lines[f]), f
want = {key(l) for f in files for l in lines[f]}
hit = set(); scanned = 0
for p in sorted(glob.glob(os.path.join(U, "htext-*/data/*.parquet"))):
    for batch in pq.ParquetFile(p).iter_batches(columns=["text"], batch_size=500_000):
        for t in batch.column(0).to_pylist():
            k = key(t)
            if k in want: hit.add(k)
        scanned += batch.num_rows
    print("scanned", os.path.basename(os.path.dirname(os.path.dirname(p))), os.path.basename(p), scanned, len(hit), flush=True)
seen, stats, out_idx, out_lines = set(), collections.Counter(), [], {f: [] for f in files}
pos = {f: collections.defaultdict(list) for f in files}
for f in files:
    for l, r in zip(lines[f], by_file[f]):
        k = key(l)
        if k in hit: stats["dropped:prior_release_duplicate"] += 1; continue
        if k in seen: stats["dropped:in_corpus_duplicate"] += 1; continue
        seen.add(k); out_lines[f].append(l); out_idx.append(r); pos[f][r["unit_id"]].append(len(out_lines[f]))
stats["lines_in"] = sum(len(v) for v in lines.values()); stats["lines_out"] = sum(len(v) for v in out_lines.values())
rights = []
for l in gzip.open(os.path.join(B, "wikisource_rights_index.v1.jsonl.gz"), "rt", encoding="utf-8"):
    r = json.loads(l); uid = f"ws_page_{r['page_id']}"; lr = {}
    for f, sub in (("wikisource_plain_v5.txt", "plain"), ("wikisource_niqqud_v5.txt", "niqqud")):
        ln = pos[f].get(uid)
        if ln:
            if ln != list(range(ln[0], ln[0] + len(ln))): raise SystemExit(f"{uid}: non-contiguous lines in {f}")
            lr[sub] = {"first_line": ln[0], "lines": len(ln)}
    if lr: rights.append({**r, "line_ranges": lr})
    else: stats["pages_emptied"] += 1
def w(name, data): open(os.path.join(O, name), "wb").write(data); return hashlib.sha256(data).hexdigest()
sums = {f: w(f, "".join(x + "\n" for x in out_lines[f]).encode()) for f in files}
gz = lambda rows: gzip.compress("".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in rows).encode(), mtime=0)
sums["wikisource_line_index.v1.jsonl.gz"] = w("wikisource_line_index.v1.jsonl.gz", gz(out_idx))
sums["wikisource_rights_index.v1.jsonl.gz"] = w("wikisource_rights_index.v1.jsonl.gz", gz(rights))
json.dump({"stats": stats, "files": sums, "dedup_against": "htext-cc0/by/by-sa v1 parquet (every published htext line)"},
          open(os.path.join(O, "dedup_report.json"), "w"), indent=1)
print(json.dumps(stats))

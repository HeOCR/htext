"""Unified htext tiers (cc0 / by / by-sa): stream every component release (pinned, verified in components.json), exact
dedupe on (variant, text) within the tier keeping the first row in priority order with a `sources` list, write zstd
parquet shards. Two streaming passes; only 64-bit hashes, lengths and source ids are held in memory.
Usage: build.py SRC_DIR TIER OUT_DIR"""
import array, csv, gzip, hashlib, io, json, os, sys, time
import numpy as np, pyarrow as pa, pyarrow.parquet as pq
SRC, TIER, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
COMP = json.load(open(os.path.join(SRC, "components.json")))
ORDER = {"cc0": ["tanakh-v1.1", "sefaria-v3.1-cc0", "sefaria-v2-cc0", "sefaria-v1", "pby-v3.1", "pby-v2.1", "pby-v1.1",
                 "tsel-haolam-v1", "gutenberg-v1", "knesset-laws-v2", "knesset-plenary-v1"],
         "by": ["sefaria-v3-by", "sefaria-v2-by"],
         "by-sa": ["wikisource-v4", "wikisource-v3", "wikisource-v2", "wikisource-v1", "sefaria-v3-by-sa"]}[TIER]
TIER_LIC = {"cc0": "CC0-1.0", "by": "CC-BY-4.0", "by-sa": "CC-BY-SA-4.0"}[TIER]
DEFAULT_LIC = {"pby": "Public Domain", "tanakh": "Public Domain", "knesset-laws": "Israel Copyright Act 2007 s.6 (not protected)",
               "knesset-plenary": "Israel Copyright Act 2007 s.6 (not protected)", "tsel-haolam": "Public Domain", "gutenberg": "Public Domain",
               "wikisource": "CC BY-SA 4.0"}
SOURCE = lambda name: name.rsplit("-v", 1)[0]
def rows_jsonl(path, keep=lambda r: True):
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", encoding="utf-8") as f:
        for l in f:
            r = json.loads(l)
            if keep(r): yield r
def files_of(name):
    d = os.path.join(SRC, name); fs = sorted(f for f in COMP[name]["files"] if f.endswith(".txt")); out = []
    for f in fs:
        p = os.path.join(d, f)
        if os.path.getsize(p) == 0: continue
        if name.startswith("sefaria-v3"):
            parts = f.split("_lines_")[1].split("_"); subset, lang = parts[0], parts[1]
            def it(subset=subset, lang=lang, d=d):
                with gzip.open(os.path.join(d, "sefaria_line_index.v3.tsv.gz"), "rt", encoding="utf-8") as fh:
                    rd = csv.reader(fh, delimiter="\t", quoting=csv.QUOTE_NONE); next(rd)
                    for r in rd:
                        if r[0] == subset and r[1] == lang: yield {"work": r[2], "version": r[3]}
            out.append((p, subset, lang, it, False))
        elif name.startswith("knesset-plenary") or name.startswith("wikisource"):
            idx = [x for x in COMP[name]["files"] if "line_index" in x][0]
            variant = ("ocr" if "_ocr_" in f else "transcription") if "plenary" in name else ("niqqud" if "niqqud" in f else "plain")
            out.append((p, variant, "he", (lambda f=f, idx=idx, d=d: rows_jsonl(os.path.join(d, idx), lambda r: r.get("file") == f)), True))
        elif name.startswith("knesset-laws"):
            out.append((p, "plain", "he", (lambda d=d: rows_jsonl(os.path.join(d, "knesset_laws_line_index.v1.jsonl.gz"))), True))
        elif name.startswith("gutenberg"):
            sub = "niqqud" if "niqqud" in f else "plain"
            out.append((p, sub, "he", (lambda sub=sub, d=d: rows_jsonl(os.path.join(d, "gutenberg_line_index.v1.jsonl.gz"), lambda r: r.get("subset") == sub)), True))
        else:  # pby, tanakh: name.index.jsonl.gz; sefaria v1/v2, tsel: plain.index.jsonl
            cand = [f.replace(".txt", ".index.jsonl.gz"), f.replace(".txt", ".index.jsonl")]
            idx = [c for c in cand if c in COMP[name]["files"]][0]
            out.append((p, "niqqud" if "niqqud" in f else "plain", "he", (lambda idx=idx, d=d: rows_jsonl(os.path.join(d, idx))), True))
    return out
def meta(name, r):
    s = SOURCE(name)
    if s == "pby": return f"pby:{r['pby_work_id']}", None
    if s == "tanakh": return f"tanakh:{r['ref']}", "Westminster Leningrad Codex (OSHB)"
    if s == "knesset-laws": return f"law:{r['bill_id']}", r.get("booklet")
    if s == "knesset-plenary": return f"plenary:{r['unit_id']}", None
    if s == "gutenberg": return f"pg:{r['pg']}", None
    if s == "tsel-haolam": return "pg:61024", None
    if s == "wikisource": return f"wikisource:{r['unit_id']}", None
    if s == "sefaria": return f"sefaria:{r.get('work')}", r.get("version") or r.get("version_title")
    raise ValueError(name)
def stream():
    for si, name in enumerate(ORDER):
        for p, variant, lang, idx_it, has_sha in files_of(name):
            n = 0
            with open(p, encoding="utf-8") as fh:
                it = idx_it()
                for line in fh:
                    text = line.rstrip("\n"); r = next(it)
                    if has_sha and n % 997 == 0 and r.get("sha256") and hashlib.sha256(text.encode()).hexdigest() != r["sha256"]:
                        raise SystemExit(f"{p}:{n + 1}: index misaligned")
                    n += 1
                    yield si, name, variant, lang, text, r
                if next(it, None) is not None: raise SystemExit(f"{p}: index has more rows than lines")
            print(f"  {name} {os.path.basename(p)} {n:,}", flush=True)
key = lambda v, t: int.from_bytes(hashlib.blake2b((v + "\x1f" + t).encode(), digest_size=8).digest(), "little", signed=True)
os.makedirs(OUT, exist_ok=True); t0 = time.time()
H, L, S = array.array("q"), array.array("i"), array.array("b")
print("pass 1", TIER, flush=True)
for si, name, variant, lang, text, r in stream():
    H.append(key(variant, text)); L.append(len(text)); S.append(si)
H = np.frombuffer(H, dtype=np.int64); L = np.frombuffer(L, dtype=np.int32); S = np.frombuffer(S, dtype=np.int8); N = len(H)
o = np.lexsort((np.arange(N), L, H)); hs, ls = H[o], L[o]
start = np.ones(N, dtype=bool); start[1:] = (hs[1:] != hs[:-1]) | (ls[1:] != ls[:-1])
gid = np.cumsum(start) - 1; first = o[start]
mask = np.zeros(int(gid[-1]) + 1, dtype=np.int32); np.bitwise_or.at(mask, gid, (1 << S[o].astype(np.int32)))
keep = np.zeros(N, dtype=bool); keep[first] = True; rowmask = np.zeros(N, dtype=np.int32); rowmask[first] = mask
del H, L, hs, ls, o, start, gid
print(f"pass 1 done: {N:,} rows, {int(keep.sum()):,} kept, {time.time() - t0:.0f}s", flush=True)
schema = pa.schema([("text", pa.string()), ("variant", pa.string()), ("lang", pa.string()), ("source", pa.string()),
                    ("source_release", pa.string()), ("sources", pa.list_(pa.string())), ("licence", pa.string()),
                    ("work_id", pa.string()), ("edition", pa.string())])
SHARD = 2_000_000; buf = {k: [] for k in schema.names}; shard = 0; files = {}; stats = {"rows_in": int(N), "rows_out": 0, "by_source": {}, "by_variant": {}}
def flush():
    global shard, buf
    if not buf["text"]: return
    name = f"data/train-{shard:05d}.parquet"; path = os.path.join(OUT, name); os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"; pq.write_table(pa.table(buf, schema=schema), tmp, compression="zstd", row_group_size=200_000); os.replace(tmp, path)
    h = hashlib.sha256(open(path, "rb").read()).hexdigest(); files[name] = {"rows": len(buf["text"]), "sha256": h, "bytes": os.path.getsize(path)}
    print(f"  wrote {name} {len(buf['text']):,}", flush=True); shard += 1; buf = {k: [] for k in schema.names}
print("pass 2", flush=True)
for i, (si, name, variant, lang, text, r) in enumerate(stream()):
    if not keep[i]: continue
    wid, ed = meta(name, r); m = int(rowmask[i])
    lic = r.get("source_licence") or DEFAULT_LIC.get(SOURCE(name)) or ""
    if name.startswith("sefaria-v3"): lic = lic or {"cc0": "Public Domain or CC0", "by": "CC-BY", "by-sa": "CC-BY-SA"}[TIER]
    for k, v in (("text", text), ("variant", variant), ("lang", lang), ("source", SOURCE(name)), ("source_release", name),
                 ("sources", [ORDER[j] for j in range(len(ORDER)) if m >> j & 1]), ("licence", lic), ("work_id", wid), ("edition", ed)):
        buf[k].append(v)
    stats["by_source"][name] = stats["by_source"].get(name, 0) + 1; stats["by_variant"][variant] = stats["by_variant"].get(variant, 0) + 1
    stats["rows_out"] += 1
    if len(buf["text"]) >= SHARD: flush()
flush()
json.dump({"tier": TIER, "licence": TIER_LIC, "order": ORDER, "components": {n: COMP[n] for n in ORDER}, "stats": stats, "files": files,
           "dedupe": "exact (variant, text); blake2b-64 + length; first row in component order kept, others listed in `sources`"},
          open(os.path.join(OUT, "build_manifest.json"), "w"), ensure_ascii=False, indent=1)
print(json.dumps(stats), f"{time.time() - t0:.0f}s", flush=True)

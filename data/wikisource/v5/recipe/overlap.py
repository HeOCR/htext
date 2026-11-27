"""Share of each work's sampled 4-word phrases (within 25-char-ish lines) already present in htext line files.
Usage: overlap.py DIR LINEFILE..."""
import gzip, json, random, re, sys, hashlib, collections
D, files = sys.argv[1], sys.argv[2:]
W = [w for w in json.load(open(f"{D}/works_joined.json")) if w["he"] >= 100_000]
want = {w["root"] for w in W}
MARKS = re.compile(r"[֑-ׇ]"); WORD = re.compile(r"[א-ת]+")
toks = lambda s: WORD.findall(MARKS.sub("", s))
texts = collections.defaultdict(list)
for l in gzip.open(f"{D}/pages.jsonl.gz", "rt", encoding="utf-8"):
    r = json.loads(l)
    if r["ns"] == 0 and not r["redirect"]:
        root = r["title"].split("/")[0].strip()
        if root in want: texts[root].append(r["text"])
rng = random.Random(1127); samp = {}; owner = collections.defaultdict(set)
for root, ts in texts.items():
    t = toks(" ".join(ts)); n = len(t)
    if n < 10: continue
    picks = set()
    for _ in range(300):
        i = rng.randrange(0, n - 4); picks.add(" ".join(t[i:i + 4]))
    samp[root] = picks
    for p in picks: owner[p].add(root)
hit = set()
for f in files:
    with open(f, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            t = toks(line)
            for i in range(len(t) - 3):
                p = " ".join(t[i:i + 4])
                if p in owner: hit.add(p)
    print("scanned", f, len(hit), flush=True)
out = {root: round(sum(p in hit for p in ps) / len(ps), 3) for root, ps in samp.items()}
json.dump(out, open(f"{D}/overlap.json", "w"), ensure_ascii=False, indent=0); print("works", len(out))

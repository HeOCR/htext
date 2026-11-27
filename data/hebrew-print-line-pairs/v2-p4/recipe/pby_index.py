"""PBY 4-word phrase index: blake2b-8 hashes of Hebrew-letter 4-grams (marks removed) with PBY work ids; phrases in
more than 3 works dropped. Writes index.npz (sorted hashes, work ids). Usage: pby_index.py TXT_STRIPPED_DIR OUT"""
import hashlib, os, re, sys
import numpy as np
root, out = sys.argv[1], sys.argv[2]
TOK = re.compile(r"[א-ת]+"); MARK = re.compile(r"[֑-ׇ]")
def grams(text):
    t = TOK.findall(MARK.sub("", text))
    return {int.from_bytes(hashlib.blake2b(" ".join(t[i:i + 4]).encode(), digest_size=8).digest(), "little") >> 1 for i in range(len(t) - 3)}
H, W = [], []
n = 0
for dp, _, fs in os.walk(root):
    for f in fs:
        m = re.search(r"m(\d+)\.txt$", f)
        if not m: continue
        g = grams(open(os.path.join(dp, f), encoding="utf-8", errors="replace").read())
        H.append(np.fromiter(g, dtype=np.int64, count=len(g))); W.append(np.full(len(g), int(m.group(1)), dtype=np.int32))
        n += 1
        if n % 2000 == 0: print(n, flush=True)
h = np.concatenate(H); w = np.concatenate(W); o = np.argsort(h, kind="stable"); h, w = h[o], w[o]
u, idx, cnt = np.unique(h, return_index=True, return_counts=True)
keep = np.repeat(cnt <= 3, cnt)
np.savez(out, h=h[keep], w=w[keep]); print("works", n, "grams", len(h), "kept", int(keep.sum()))

"""Screen pre-1931 Hebrew IA text items against PBY by content: IA's own OCR (_djvu.txt, robots-permitted, 1 req/s,
cached gz) -> Hebrew 4-gram hashes -> hits in the PBY index -> per-work hit counts. Excludes already-used and
reserved IA ids. Usage: ia_pby_screen.py SCRAPE_DIR INDEX.npz USED_IDS RESERVATIONS OUT_DIR"""
import glob, gzip, hashlib, json, os, re, sys, time, urllib.request, collections
import numpy as np
scrape, idx, used_f, res_f, out = sys.argv[1:6]; os.makedirs(f"{out}/djvu", exist_ok=True)
UA = "htext-fetch/0.1 (https://github.com/HeOCR/htext)"
TOK = re.compile(r"[א-ת]+"); MARK = re.compile(r"[֑-ׇ]")
z = np.load(idx); H, Wk = z["h"], z["w"]
used = set(open(used_f).read().split())
reserved = set()
for s in json.load(open(res_f))["reservations"]:
    if s.get("status"): continue
    for k in ("ia_identifiers", "books", "reserves"): reserved.update(str(x) for x in (s.get(k) or []))
    for v in (s.get("strata") or {}).values(): reserved.update(v)
    reserved.update(s.get("conditional") or {})
items = [it for f in sorted(glob.glob(f"{scrape}/page_*.json")) for it in json.load(open(f))["items"]]
def year(it):
    for k in ("year", "date"):
        m = re.match(r"(\d{4})", str(it.get(k) or ""))
        if m: return int(m.group(1))
cand = [it for it in items if (year(it) or 9999) <= 1930 and int(it.get("imagecount") or 0) >= 20
        and it["identifier"] not in used and it["identifier"] not in reserved]
print("candidates", len(cand), "of", len(items), "; excluded used", sum(it["identifier"] in used for it in items), "reserved", sum(it["identifier"] in reserved for it in items), flush=True)
res_path = f"{out}/screen.jsonl"; done = set()
if os.path.exists(res_path): done = {json.loads(l)["id"] for l in open(res_path)}
fo = open(res_path, "a")
for k, it in enumerate(cand):
    i = it["identifier"]
    if i in done: continue
    p = f"{out}/djvu/{i}.txt.gz"; status = "ok"
    if not os.path.exists(p):
        url = f"https://archive.org/download/{i}/{i}_djvu.txt"; raw = None
        for a in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120) as r: raw = r.read(); break
            except urllib.error.HTTPError as e:
                if e.code in (403, 404): status = f"http_{e.code}"; break
                time.sleep(20 * (a + 1))
            except Exception: time.sleep(20 * (a + 1))
        time.sleep(1)
        if raw is None:
            fo.write(json.dumps({"id": i, "status": status or "fetch_failed"}) + "\n"); fo.flush(); continue
        open(p, "wb").write(gzip.compress(raw))
    text = gzip.decompress(open(p, "rb").read()).decode("utf-8", "replace")
    t = TOK.findall(MARK.sub("", text))
    g = np.fromiter((int.from_bytes(hashlib.blake2b(" ".join(t[j:j + 4]).encode(), digest_size=8).digest(), "little") >> 1 for j in range(len(t) - 3)), dtype=np.int64)
    if len(g) == 0:
        fo.write(json.dumps({"id": i, "status": "no_hebrew_text"}) + "\n"); fo.flush(); continue
    pos = np.searchsorted(H, g); pos[pos >= len(H)] = len(H) - 1; hit = H[pos] == g
    works = collections.Counter(Wk[pos[hit]].tolist())
    fo.write(json.dumps({"id": i, "status": status, "year": year(it), "title": it.get("title"), "imagecount": it.get("imagecount"),
                         "grams": int(len(g)), "hit_grams": int(hit.sum()), "top": works.most_common(8)}, ensure_ascii=False) + "\n"); fo.flush()
    if k % 100 == 0: print(k, i, flush=True)
print("done")

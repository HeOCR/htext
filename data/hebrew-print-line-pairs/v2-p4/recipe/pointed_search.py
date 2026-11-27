"""Targeted IA search for 1880-1930 volumes by authors of pointed PBY works (Wikidata labels/aliases -> IA creator
queries, robots-permitted advancedsearch, 1 req/s, cached). Katzenelson excluded. Usage: pointed_search.py DIR"""
import json, os, re, sys, time, urllib.parse, urllib.request
D = sys.argv[1]; UA = "htext-fetch/0.1 (https://github.com/HeOCR/htext)"; os.makedirs(f"{D}/wd", exist_ok=True); os.makedirs(f"{D}/ia_q", exist_ok=True)
def get(url, p):
    if not os.path.exists(p):
        for a in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=90) as r: open(p, "wb").write(r.read()); break
            except Exception: time.sleep(15 * (a + 1))
        time.sleep(1)
    return json.load(open(p))
top = json.load(open(f"{D}/pointed_authors.json"))[:45]
used = set(open(f"{D}/used_ia_ids.txt").read().split())
res = json.load(open(os.path.expanduser("~/temp/heocr/downloads/real-line-modern-20261127/gates/eval_reservations_v14.json")))
reserved = set()
for s in res["reservations"]:
    if s.get("status"): continue
    for k in ("ia_identifiers", "books", "reserves"): reserved.update(str(x) for x in (s.get(k) or []))
    for v in (s.get("strata") or {}).values(): reserved.update(v)
    reserved.update(s.get("conditional") or {})
screened = {json.loads(l)["id"] for l in open(f"{D}/screen/screen.jsonl")}
cands = {}
for name, n, letters, uri in top:
    q = (uri or "").rsplit("/", 1)[-1]
    if not q.startswith("Q"): continue
    e = get(f"https://www.wikidata.org/wiki/Special:EntityData/{q}.json", f"{D}/wd/{q}.json")["entities"].popitem()[1]
    labels = {e.get("labels", {}).get(l, {}).get("value") for l in ("en", "de", "he")} | {a["value"] for l in ("en",) for a in e.get("aliases", {}).get(l, [])}
    labels = {x for x in labels if x and len(x) > 3}
    surn = {x.split()[-1] for x in labels if re.match(r"^[A-Za-z]", x)}
    for lab in sorted(labels)[:6]:
        qq = f'creator:("{lab}") AND mediatype:texts AND date:[1880-01-01 TO 1930-12-31]'
        url = "https://archive.org/advancedsearch.php?" + urllib.parse.urlencode([("q", qq), ("rows", "200"), ("output", "json")] + [("fl[]", f) for f in ("identifier", "title", "date", "year", "imagecount", "creator", "language")])
        docs = get(url, f"{D}/ia_q/{re.sub(r'[^A-Za-z0-9]+', '_', lab)[:60]}_{q}.json").get("response", {}).get("docs", [])
        for d in docs:
            i = d["identifier"]
            if i in used or i in reserved: continue
            cands.setdefault(i, {**d, "authors": set()})["authors"].add(name)
out = [{**{k: v for k, v in d.items() if k != "authors"}, "authors": sorted(d["authors"]), "already_screened": d["identifier"] in screened} for d in cands.values()]
json.dump(out, open(f"{D}/pointed_candidates.json", "w"), ensure_ascii=False, indent=0)
print(len(out), "candidates;", sum(not x["already_screened"] for x in out), "not yet screened")

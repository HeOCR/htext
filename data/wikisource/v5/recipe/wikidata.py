"""Wikidata rights facts for works' QIDs: P50 author(s) -> P570 death year; P577 publication; P31. Cached EntityData
JSON (robots-permitted /wiki/Special:EntityData), 1 request/s. Usage: wikidata.py DIR"""
import json, sys, time, urllib.request, os
D = sys.argv[1]; cache = f"{D}/wd_cache"; os.makedirs(cache, exist_ok=True)
UA = "htext-fetch/0.1 (https://github.com/HeOCR/htext)"
def ent(q):
    p = f"{cache}/{q}.json"
    if not os.path.exists(p):
        for a in range(4):
            try:
                req = urllib.request.Request(f"https://www.wikidata.org/wiki/Special:EntityData/{q}.json", headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=60) as r: open(p, "wb").write(r.read()); break
            except Exception as e:
                time.sleep(10 * (a + 1))
        time.sleep(1)
    try: return json.load(open(p))["entities"].popitem()[1]
    except Exception: return {}
def year(e, prop):
    out = []
    for c in e.get("claims", {}).get(prop, []):
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        if isinstance(v, dict) and v.get("time"): out.append(int(v["time"][1:5]) * (-1 if v["time"][0] == "-" else 1))
    return out
def ids(e, prop): return [c["mainsnak"]["datavalue"]["value"]["id"] for c in e.get("claims", {}).get(prop, []) if c.get("mainsnak", {}).get("datavalue")]
W = [w for w in json.load(open(f"{D}/works_joined.json")) if w["he"] >= 100_000 and w.get("qid")]
out = {}
for w in W:
    e = ent(w["qid"]); auth = ids(e, "P50") or ids(e, "P170")
    # edition items point at their work (P629): read authors there too
    if not auth:
        for wq in ids(e, "P629")[:1]: auth = ids(ent(wq), "P50")
    deaths = {a: year(ent(a), "P570") for a in auth[:4]}
    out[w["root"]] = {"qid": w["qid"], "label_he": e.get("labels", {}).get("he", {}).get("value"), "authors": auth, "deaths": deaths,
                      "pub": year(e, "P577"), "inception": year(e, "P571"), "instance": ids(e, "P31")[:3]}
json.dump(out, open(f"{D}/wikidata.json", "w"), ensure_ascii=False, indent=0); print("done", len(out))

"""Match Wikisource works (>=20k Hebrew letters) to IA Hebrew text items by normalised Hebrew title.
Excludes IA identifiers reserved in eval reservations (v14). Usage: ia_match.py DIR RESERVATIONS"""
import glob, json, re, sys, collections
D, RES = sys.argv[1], sys.argv[2]
HEW = re.compile(r"[א-ת]+")
def norm(s): return " ".join(HEW.findall(re.sub(r"[֑-ׇ]", "", s or "")))
STOP = {"ספר", "על", "עם", "או", "חלק", "של", "שו", "ת", "מאת", "הוא", "והוא"}
def core(t):
    t = re.sub(r"\(.*?\)", " ", t); w = [x for x in norm(t).split() if x not in STOP]
    return " ".join(w)
items = [it for f in sorted(glob.glob(f"{D}/ia_scrape/page_*.json")) for it in json.load(open(f))["items"]]
reserved = set()
for s in json.load(open(RES))["reservations"]:
    if s.get("status"): continue
    for k in ("ia_identifiers", "books", "reserves"): reserved.update(str(x) for x in (s.get(k) or []))
    for v in (s.get("strata") or {}).values(): reserved.update(v)
    reserved.update(s.get("conditional") or {})
for it in items:
    t = it.get("title"); t = " ".join(t) if isinstance(t, list) else (t or "")
    it["_he"] = " " + norm(t) + " "
W = [w for w in json.load(open(f"{D}/works_joined.json"))]
out = {}
for w in W:
    c = core(w["root"])
    if len(c.replace(" ", "")) < 5 and len(c.split()) < 2: continue
    hits = [it for it in items if f" {c} " in it["_he"]]
    if not hits: continue
    out[w["root"]] = [{"id": it["identifier"], "title": it.get("title"), "date": it.get("date") or it.get("year"),
                       "imagecount": it.get("imagecount"), "rights": it.get("possible-copyright-status"),
                       "reserved": it["identifier"] in reserved} for it in hits[:30]]
json.dump(out, open(f"{D}/ia_match.json", "w"), ensure_ascii=False, indent=0)
print(len(items), "IA items;", len(out), "works with >=1 IA title match;", sum(len(v) for v in out.values()), "pairs;",
      sum(1 for v in out.values() for h in v if h["reserved"]), "reserved hits")

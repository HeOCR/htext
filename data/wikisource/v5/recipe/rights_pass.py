"""Rights pass for Wikisource ns0 works. Candidate authors from the root page ({{ספר|מחבר}}, {{מח|..}}, 'מאת [[..]]',
[[מחבר:..]] links = attributed; categories = fallback), resolved via the page and page_props dumps to Wikidata humans
(P31=Q5); P570/P569 from EntityData (robots-permitted, 1 req/s, cached). PD only if every resolved author died <= 1955.
Translations need a proven translator. Usage: rights_pass.py DIR"""
import gzip, json, os, re, sys, time, urllib.request
D = sys.argv[1]; cache = f"{D}/wd_cache"; os.makedirs(cache, exist_ok=True)
UA = "htext-fetch/0.1 (https://github.com/HeOCR/htext)"
pid = {}
for line in gzip.open(f"{D}/page.sql.gz", "rt", encoding="utf-8", errors="replace"):
    for i, ns, t in re.findall(r"\((\d+),(14|108|0),'((?:[^'\\]|\\.)*)'", line):
        pid[(int(ns), t.replace("\\'", "'").replace('\\"', '"').replace("_", " "))] = int(i)
qid = {}
for line in gzip.open(f"{D}/page_props.sql.gz", "rt", encoding="utf-8", errors="replace"):
    for p, q in re.findall(r"\((\d+),'wikibase_item','(Q\d+)'", line): qid[int(p)] = q
def ent(q):
    p = f"{cache}/{q}.json"
    if not os.path.exists(p):
        for a in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(f"https://www.wikidata.org/wiki/Special:EntityData/{q}.json", headers={"User-Agent": UA}), timeout=60) as r:
                    open(p, "wb").write(r.read()); break
            except Exception: time.sleep(10 * (a + 1))
        time.sleep(1)
    try: return json.load(open(p))["entities"].popitem()[1]
    except Exception: return {}
def years(e, prop):
    out = []
    for c in e.get("claims", {}).get(prop, []):
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        if isinstance(v, dict) and v.get("time"): out.append(int(v["time"][1:5]) * (-1 if v["time"][0] == "-" else 1))
    return out
def human(name):
    name = name.strip().replace("_", " ")
    for key in ((108, name), (14, name), (14, "כתבי " + name)):
        q = qid.get(pid.get(key))
        if q:
            e = ent(q); p31 = [c["mainsnak"].get("datavalue", {}).get("value", {}).get("id") for c in e.get("claims", {}).get("P31", [])]
            if "Q5" in p31: return {"name": name, "qid": q, "death": years(e, "P570"), "birth": years(e, "P569"), "via": key[0]}
            return None
    return None
roots = {}
for l in gzip.open(f"{D}/pages.jsonl.gz", "rt", encoding="utf-8"):
    r = json.loads(l)
    if r["ns"] == 0 and not r["redirect"] and "/" not in r["title"]: roots[r["title"]] = r["text"]
rows = json.load(open(f"{D}/ranked_raw.json"))
LINK = re.compile(r"\[\[(?:מחבר:)?([^\]|#]+)(?:\|[^\]]*)?\]\]")
for row in rows:
    if row["kind"] != "work": continue
    t = roots.get(row["root"], "")
    attr = set()
    m = re.search(r"\|\s*מחבר\s*=\s*([^|\n}]*)", t)
    if m: attr.update(x for x in LINK.findall(m.group(1))); attr.update(re.findall(r"\{\{\s*מח\s*\|\s*([^|}]+)", m.group(1)))
    attr.update(re.findall(r"\{\{\s*מח\s*\|\s*([^|}]+)", t[:4000]))
    attr.update(re.findall(r"\[\[מחבר:([^\]|#]+)", t))
    for mm in re.finditer(r"מאת\s+(?:ה?רב\s+|רבי\s+|ר'\s+)?\[\[([^\]|#]+)", t[:3000]): attr.add(mm.group(1))
    cats = set(c.strip() for c in re.findall(r"\[\[\s*קטגוריה\s*:\s*([^|\]]+)", t))
    translation = bool(re.search(r"תרגום|מתורגם|translated", " ".join(cats) + " " + row["root"] + " " + t[:2000]))
    hum_attr = [h for h in (human(a) for a in attr) if h]
    hum_cat = [h for h in (human(c) for c in cats) if h]
    auth, basis = (hum_attr, "attributed") if hum_attr else (hum_cat, "category")
    row["rights_pass"] = {"attributed": sorted(attr), "categories_human": [h["name"] for h in hum_cat], "authors": auth, "basis": basis, "translation": translation}
    if not auth: verdict = "out: no author resolved"
    elif any(not h["death"] and (not h["birth"] or max(h["birth"]) >= 1900) for h in auth): verdict = "out: possibly living / no death date"
    elif any(not h["death"] for h in auth): verdict = "out: no death date"
    elif max(max(h["death"]) for h in auth) > 1955: verdict = "out: author died after 1955 (d. %d)" % max(max(h["death"]) for h in auth)
    elif translation: verdict = "out: translation, translator unproven"
    else: verdict = "PD-IL (d. %d, %s)" % (max(max(h["death"]) for h in auth), basis)
    if row["rights"].startswith("unverified"): row["rights"] = verdict
    elif row["rights"].startswith("PD") and translation: row["rights"] = "out: translation, translator unproven (was " + row["rights"] + ")"
json.dump(rows, open(f"{D}/ranked_rights.json", "w"), ensure_ascii=False, indent=0)
import collections
W = [r for r in rows if r["kind"] == "work"]
print(collections.Counter(r["rights"].split(" (")[0].split(":")[0] for r in W))
print(collections.Counter(r["rights"].split(" (")[0] for r in W if r["rights"].startswith("out")))
print("PD new lines:", sum(r["new"] for r in W if r["rights"].startswith("PD")))

"""Join works.json with page_props wikibase_item, Sefaria Hebrew titles and the reserved P-hist Index titles."""
import gzip, json, re, sys
D = sys.argv[1]
qid = {}
for line in gzip.open(f"{D}/page_props.sql.gz", "rt", encoding="utf-8", errors="replace"):
    for pid, val in re.findall(r"\((\d+),'wikibase_item','(Q\d+)'", line):
        qid[int(pid)] = val
he_sef = set()
import glob
for f in glob.glob("/Users/shaypalachy/temp/heocr/downloads/htext-sefaria/v3/export/schemas/*.json"):
    t = json.load(open(f, encoding="utf-8")).get("heTitle") or ""
    if t: he_sef.add(re.sub(r"\s+", " ", t).strip())
res = json.load(open("/Users/shaypalachy/temp/heocr/downloads/htext-gutenberg/eval_reservations_v13.json"))
idx_ids = set()
for s in res["reservations"]:
    for k in ("wikisource_indexes", "item_ids"):
        for x in s.get(k, []) or []:
            m = re.search(r"ws_index_(\d+)", str(x)); m and idx_ids.add(int(m.group(1)))
idx_titles = {}
for l in gzip.open(f"{D}/pages.jsonl.gz", "rt", encoding="utf-8"):
    r = json.loads(l)
    if r["ns"] == 112 and r["id"] in idx_ids: idx_titles[r["id"]] = r["title"].split(":", 1)[-1]
W = json.load(open(f"{D}/works.json"))
norm = lambda s: re.sub(r"[\"'״׳()\s]+", " ", s).strip()
sef_n = {norm(t) for t in he_sef}
res_n = [norm(re.sub(r"\.(pdf|djvu)$", "", t, flags=re.I)) for t in idx_titles.values()]
for w in W:
    w["qid"] = qid.get(w["root_id"]); w["est_lines"] = w["he"] // 21
    w["sefaria_title_match"] = norm(w["root"]) in sef_n or norm(re.sub(r"\s*\(.*?\)", "", w["root"])) in sef_n
    w["reserved_index_title_hit"] = [t for t in res_n if norm(w["root"]) and (norm(w["root"]) in t or t in norm(w["root"]))][:3]
json.dump(W, open(f"{D}/works_joined.json", "w"), ensure_ascii=False, indent=0)
json.dump(idx_titles, open(f"{D}/reserved_index_titles.json", "w"), ensure_ascii=False, indent=1)
print(len(qid), "qids;", len(he_sef), "sefaria he titles;", len(idx_titles), "reserved index titles")
for th in (100_000, 150_000, 300_000):
    sel = [w for w in W if w["he"] >= th]
    print(th, len(sel), "works; with qid", sum(1 for w in sel if w["qid"]), "; sefaria title match", sum(w["sefaria_title_match"] for w in sel), "; reserved hits", sum(bool(w["reserved_index_title_hit"]) for w in sel))

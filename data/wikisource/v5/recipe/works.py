"""Aggregate ns0 pages into works by root title (before the first '/'): Hebrew letters, pages, {{ספר}} fields, title
page, categories, scan links (archive.org, Commons File:, hebrewbooks, NLI), Index (מפתח) links. Usage: works.py DIR"""
import gzip, json, re, sys, collections
D = sys.argv[1]
HE = re.compile(r"[א-ת]")
TPL_BOOK = re.compile(r"\{\{\s*ספר\s*\n?\|(.*?)\}\}", re.S)
IA = re.compile(r"archive\.org/(?:details|download|stream)/([A-Za-z0-9._-]+)")
FILE = re.compile(r"\[\[\s*(?:קובץ|File|Image|תמונה)\s*:\s*([^|\]]+\.(?:pdf|djvu))", re.I)
HB = re.compile(r"hebrewbooks\.org/(?:pdfpager\.aspx\?req=|)(\d{2,6})|\|\s*היברו\s*=\s*(\d+)")
NLI = re.compile(r"\|\s*לאומית\s*=\s*(\d+)")
IDX = re.compile(r"\[\[\s*(?:מפתח|Index)\s*:\s*([^|\]]+)")
CAT = re.compile(r"\[\[\s*קטגוריה\s*:\s*([^|\]]+)")
W = collections.defaultdict(lambda: {"pages": 0, "he": 0, "ia": set(), "files": set(), "hb": set(), "nli": set(), "index": set(), "cats": set(), "book": None, "root_id": None, "title_page": None})
authors = {}
for l in gzip.open(f"{D}/pages.jsonl.gz", "rt", encoding="utf-8"):
    r = json.loads(l)
    if r["redirect"]: continue
    t = r["text"]
    if r["ns"] == 108:
        authors[r["title"].split(":", 1)[-1]] = t[:3000]; continue
    if r["ns"] != 0: continue
    root = r["title"].split("/")[0].strip(); w = W[root]
    w["pages"] += 1; w["he"] += len(HE.findall(t))
    w["ia"].update(IA.findall(t)); w["files"].update(f.strip() for f in FILE.findall(t))
    for a, b in HB.findall(t): w["hb"].add(a or b)
    w["nli"].update(NLI.findall(t)); w["index"].update(i.strip() for i in IDX.findall(t))
    if r["title"] == root:
        w["root_id"] = r["id"]; w["cats"].update(c.strip() for c in CAT.findall(t))
        m = TPL_BOOK.search(t)
        if m: w["book"] = {k.strip(): v.strip() for k, v in (p.split("=", 1) for p in m.group(1).split("|") if "=" in p)}
        m = re.search(r"\{\{\s*דף שער(.*?)\}\}\s*\n", t, re.S)
        if m: w["title_page"] = re.sub(r"\s+", " ", m.group(1))[:400]
out = []
for root, w in W.items():
    if w["he"] < 20000: continue
    out.append({"root": root, **{k: (sorted(v) if isinstance(v, set) else v) for k, v in w.items()}})
out.sort(key=lambda x: -x["he"])
json.dump(out, open(f"{D}/works.json", "w"), ensure_ascii=False, indent=0)
json.dump(authors, open(f"{D}/authors.json", "w"), ensure_ascii=False)
print(len(W), "roots;", len(out), ">=20k letters;", len(authors), "author pages")

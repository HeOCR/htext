"""v2-p4 editions batch manifest from screened IA x PBY pairs. Per pair: the item's original PDF (sha1 pinned), the
page span holding the PBY work (IA's own per-page OCR from _djvu.xml vs the work's 4-grams), and the PBY dump text
(txt_stripped = plain lane; pinned rev). Usage: make_manifest.py DIR PAIRS_JSON DROP_IA_IDS OUT_JSON"""
import csv, gzip, hashlib, json, os, re, sys, time, urllib.request, collections
D, PAIRS, DROP, OUT = sys.argv[1:5]; UA = "htext-fetch/0.1 (https://github.com/HeOCR/htext)"; REV = "5e4277fead7b565f32cc4b352abd3565023a77d8"
os.makedirs(f"{D}/meta", exist_ok=True); os.makedirs(f"{D}/djvuxml", exist_ok=True)
def get(url, p, binary=False):
    if not os.path.exists(p):
        for a in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=300) as r: raw = r.read(); break
            except Exception: time.sleep(20 * (a + 1))
        open(p, "wb").write(gzip.compress(raw) if p.endswith(".gz") else raw); time.sleep(1)
    raw = open(p, "rb").read(); return gzip.decompress(raw) if p.endswith(".gz") else raw
TOK = re.compile(r"[א-ת]+"); MARK = re.compile(r"[֑-ׇ]")
g4 = lambda t: (lambda w: {" ".join(w[i:i + 4]) for i in range(len(w) - 3)})(TOK.findall(MARK.sub("", t)))
cat = {int(r["ID"]): r for r in csv.DictReader(open(f"{D}/pseudocatalogue.csv", encoding="utf-8"))}
drop = set(open(DROP).read().split()); pairs = [p for p in json.load(open(PAIRS)) if p["ia"] not in drop]
out, report = [], {}
for p in pairs:
    ia, wid = p["ia"], p["pby"]
    m = json.loads(get(f"https://archive.org/metadata/{ia}", f"{D}/meta/{ia}.json"))
    pdfs = [f for f in m["files"] if f["name"].endswith(".pdf") and f.get("source") == "original"] or [f for f in m["files"] if f["name"] == f"{ia}.pdf"]
    if not pdfs: report[f"{ia}:{wid}"] = "no original pdf"; continue
    pdf = pdfs[0]
    xmlf = [f["name"] for f in m["files"] if f["name"].endswith("_djvu.xml")]
    if not xmlf: report[f"{ia}:{wid}"] = "no djvu.xml"; continue
    x = get(f"https://archive.org/download/{ia}/{xmlf[0]}", f"{D}/djvuxml/{ia}.xml.gz").decode("utf-8", "replace")
    pages = re.split(r"<OBJECT\b", x)[1:]
    ptxt = [" ".join(re.findall(r"<WORD[^>]*>([^<]*)</WORD>", pg)) for pg in pages]
    rel = cat[wid]["path"].lstrip("/"); tpath = f"{D}/pbydump/txt_stripped/{rel}.txt"
    W = g4(open(tpath, encoding="utf-8").read())
    hits = [len(g4(t) & W) for t in ptxt]
    good = [i for i, h in enumerate(hits) if h >= 8]
    if len(good) < 2: report[f"{ia}:{wid}"] = "too few pages"; continue
    lo, hi = good[0], good[-1]
    out.append({"id": f"{ia}:pby:{wid}", "scan": {"url": f"https://archive.org/download/{ia}/{pdf['name']}", "sha1": pdf["sha1"], "size": int(pdf["size"])},
                "scope": {"pdf_ordinals": list(range(lo + 1, hi + 2)), "djvu_pages": len(pages), "pages_with_hits": len(good)},
                "transcription": {"url": f"https://raw.githubusercontent.com/projectbenyehuda/public_domain_dump/{REV}/txt_stripped/{rel}.txt",
                                  "sha256": hashlib.sha256(open(tpath, "rb").read()).hexdigest(), "format": "text", "id": f"pby:{wid}",
                                  "licence": "Public Domain", "source": "Project Ben-Yehuda", "title": cat[wid]["title"], "authors": cat[wid]["authors"]},
                "local_text": tpath, "year": p["year"], "exact_test_pages_excluded": []})
    report[f"{ia}:{wid}"] = f"pages {lo + 1}-{hi + 1} of {len(pages)} ({len(good)} with hits)"
json.dump({"schema": "htext_editions_batch.v2p4", "pairs": out}, open(OUT, "w"), ensure_ascii=False, indent=1)
json.dump({p["id"]: {"text": p["local_text"]} for p in out}, open(OUT.replace(".json", ".local.json"), "w"), indent=1)
print(len(out), "pairs;", sum(len(p["scope"]["pdf_ordinals"]) for p in out), "pages;", sum(p["scan"]["size"] for p in {x["scan"]["url"]: x for x in out}.values()) // 2**20, "MB of PDFs")
print(collections.Counter(v.split(" ")[0] if not v.startswith("pages") else "ok" for v in report.values()))

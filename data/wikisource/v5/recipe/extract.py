"""Stream the pinned hewikisource pages-articles dump; write ns0 + author + index + page-namespace rows (title, id,
rev, ns, redirect, text) to gzipped JSONL, and the namespace table. Usage: extract.py DUMP OUTDIR"""
import bz2, gzip, json, sys, xml.etree.ElementTree as ET
dump, out = sys.argv[1], sys.argv[2]
ns_names = {}; keep = None
fo = gzip.open(f"{out}/pages.jsonl.gz", "wt", encoding="utf-8")
n = 0
for ev, el in ET.iterparse(bz2.open(dump), events=("end",)):
    tag = el.tag.rsplit("}", 1)[-1]
    if tag == "namespace":
        ns_names[int(el.get("key"))] = el.text or ""
    elif tag == "siteinfo":
        json.dump(ns_names, open(f"{out}/namespaces.json", "w"), ensure_ascii=False, indent=1)
        keep = {0} | {k for k, v in ns_names.items() if v in ("מחבר", "עמוד", "מפתח", "ביאור", "Author", "Page", "Index")}
        print("keep ns", {k: ns_names[k] for k in keep}, flush=True)
    elif tag == "page":
        g = lambda t: el.find(f"{{*}}{t}")
        ns = int(g("ns").text)
        if ns in keep:
            rev = g("revision"); txt = rev.find("{*}text").text or ""
            fo.write(json.dumps({"title": g("title").text, "id": int(g("id").text), "ns": ns, "rev": int(rev.find("{*}id").text),
                                 "redirect": g("redirect") is not None, "text": txt}, ensure_ascii=False) + "\n")
            n += 1
        el.clear()
fo.close(); print("rows", n)

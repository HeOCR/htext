"""List every Internet Archive text item in Hebrew (scrape API, robots-permitted), cursor-paged, cached per page.
Usage: ia_scrape.py DIR"""
import json, os, sys, time, urllib.parse, urllib.request
D = sys.argv[1]; os.makedirs(f"{D}/ia_scrape", exist_ok=True)
UA = "htext-fetch/0.1 (https://github.com/HeOCR/htext)"
q = "mediatype:texts AND (language:heb OR language:hebrew OR language:Hebrew OR language:he)"
fields = "identifier,title,date,year,publisher,imagecount,language,creator,collection,possible-copyright-status,licenseurl,rights"
cursor, page, n = None, 0, 0
while True:
    p = f"{D}/ia_scrape/page_{page:04d}.json"
    if not os.path.exists(p):
        qs = {"q": q, "fields": fields, "count": "10000"}
        if cursor: qs["cursor"] = cursor
        url = "https://archive.org/services/search/v1/scrape?" + urllib.parse.urlencode(qs)
        for a in range(5):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=300) as r: raw = r.read(); break
            except Exception as e:
                print("retry", a, e, flush=True); time.sleep(30 * (a + 1))
        open(p, "wb").write(raw); time.sleep(2)
    d = json.load(open(p)); n += len(d.get("items", [])); print("page", page, n, d.get("total"), flush=True)
    cursor = d.get("cursor"); page += 1
    if not cursor: break

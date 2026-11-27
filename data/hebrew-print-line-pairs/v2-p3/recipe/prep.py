"""Press pairs heocr-ops #711/#713/#714 -> one htext editions batch manifest (columns rtlN).

Downloads each scan PDF once (sha1 + sha256 checked), hard-links it to the editions driver's per-pair scan path, and
pre-renders source-level 180-degree pages (Ha-Melitz supplement) upright into the driver's page cache.
Usage: prep.py MANIFEST_DIR WORK_DIR
"""
import hashlib, json, os, subprocess, sys, time
from pathlib import Path
from htext.linepairs import editions as E, wikisource as W

mdir, work = Path(sys.argv[1]), Path(sys.argv[2])
SRC = [("real-line-print-types-press-20261126.json", "711"), ("real-line-press-scale-20261127.json", "713"),
       ("real-line-press-scale-extension-20261127.json", "714")]
scans, pairs = {}, []
for f, tag in SRC:
    d = json.loads((mdir / f).read_text(encoding="utf-8"))
    for s in d.get("scan_sources", []):
        scans[s["accession"]] = {"url": s["exact_pdf_url"], "sha1": s["pdf_sha1"], "sha256": s["pdf_sha256"],
                                 "rot": int(s.get("extra_rotation_degrees") or 0)}
    for p in d["pairs"]:
        if "scan" in p:
            s = p["scan"]
            rots = {x["upright_render"]["extra_rotation_degrees"] for x in p["exact_mapped_pages"]}
            assert len(rots) == 1, p["id"]
            scans.setdefault(s["accession"], {"url": s["exact_file_url"], "sha1": s["sha1"], "sha256": s["sha256"], "rot": rots.pop()})
            acc, ords = s["accession"], [x["pdf_ordinal_1_based"] for x in p["exact_mapped_pages"]]
        else:
            acc, ords = p["scan_accession"], [x["pdf_ordinal_1_based"] for x in p["exact_ranges"]]
        ords = list(dict.fromkeys(ords))
        t = p["transcription"]
        pairs.append({"id": f"{tag}:{p['id']}", "source_pr": f"heocr-ops#{tag}", "accession": acc,
                      "scan": {"url": scans[acc]["url"], "sha1": scans[acc]["sha1"]},
                      "scope": {"pdf_ordinals": ords},
                      "transcription": {"url": t["url"], "sha256": t["sha256"], "format": "text", "source": "Project Ben-Yehuda",
                                        "id": t["id"], "licence": t["licence"]},
                      "columns": "rtlN", "exact_test_pages_excluded": []})

def h(path, algo):
    x = hashlib.new(algo)
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""): x.update(b)
    return x.hexdigest()

pdf_dir = work / "pdf"; pdf_dir.mkdir(parents=True, exist_ok=True)
for acc, s in scans.items():
    dest = pdf_dir / f"{acc}.pdf"
    for attempt in range(5):
        if dest.exists() and h(dest, "sha1") == s["sha1"] and h(dest, "sha256") == s["sha256"]:
            break
        subprocess.run(["curl", "-sSfL", "-A", E.UA, "-o", str(dest), s["url"]], check=False)
        time.sleep(5 * attempt)
    else:
        raise SystemExit(f"{acc}: bytes do not match the pins")
    print("ok", acc, s["rot"], flush=True)

out = work / "pilot"
for p in pairs:
    sid = E.safe_id(p["id"]); acc = p["accession"]
    link = work / "scans" / f"{sid}.pdf"; link.parent.mkdir(parents=True, exist_ok=True)
    if not link.exists(): os.link(pdf_dir / f"{acc}.pdf", link)
    if scans[acc]["rot"]:
        from PIL import Image
        for n in p["scope"]["pdf_ordinals"]:
            png = out / "pages" / sid / f"p{n:04d}.png"
            if png.exists(): continue
            tmp = png.with_name(f".raw_{png.name}")
            W.page_image(pdf_dir / f"{acc}.pdf", n, tmp)
            Image.open(tmp).convert("L").rotate(scans[acc]["rot"], expand=True).save(png); tmp.unlink()
man = {"schema": "htext_editions_batch.press.v1", "sources": [f"heocr-ops#{t}" for _, t in SRC], "pairs": pairs}
(work / "batch.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(pairs), "pairs;", sum(len(p["scope"]["pdf_ordinals"]) for p in pairs), "page jobs")

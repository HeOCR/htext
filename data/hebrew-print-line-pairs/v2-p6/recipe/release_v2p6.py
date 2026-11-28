"""Combined line-pairs release, resumable: stage (fetch HF main files at the pinned parent, drop the #1927 550 rows from
v1.1 and p3, build p6 and p4b manifests and READMEs), HF commit v2-p6 (+ tag, readback), HF commit v2-p4b (+ tag,
readback). State: hf_state.json. Usage: release_v2p6.py STAGE_DIR"""
import collections, glob, hashlib, json, os, sys
import pyarrow as pa, pyarrow.compute as pc, pyarrow.parquet as pq
from huggingface_hub import HfApi, CommitOperationAdd, hf_hub_download
from htext.public_guard import assert_public_safe  # fail closed on custody material (htext#81)
S = sys.argv[1]; R = "HeOCR/hebrew-print-line-pairs"; PARENT = "be8f68ef74e0f79e4896e5887ee1d2455528811e"
P6 = os.path.expanduser("~/temp/heocr/downloads/v2/parts/p6-vilna-volumes"); P4B = os.path.expanduser("~/temp/heocr/downloads/v2/parts/p4b-ia-pby-pointed")
DROP = os.path.expanduser("~/temp/heocr/htext-v2-pull/release-drop-ids.jsonl")
api = HfApi(token=os.environ["HF_TOKEN"]); stf = f"{S}/hf_state.json"; st = json.load(open(stf)) if os.path.exists(stf) else {}
save = lambda: json.dump(st, open(stf, "w"), indent=1)
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
log = lambda *a: print(*a, flush=True)
assert sha(DROP) == "2b137283c18a062447aaa634e948048f79cd44c13b620f5a014a59abf6880b56"
if not st.get("staged"):
    files = ["README.md", "manifest.json", "data/train-00001.parquet", "data/train-00002.parquet",
             "v2/p3-ops711-714/public/train-00000.parquet", "v2/p3-ops711-714/manifest.json"]
    for f in files: hf_hub_download(R, f, repo_type="dataset", revision=PARENT, local_dir=f"{S}/cur")
    D = collections.defaultdict(set)
    for l in open(DROP): d = json.loads(l); D[d["part"]].add(d["id"])
    def rewrite(src, dst, ids):
        os.makedirs(os.path.dirname(dst), exist_ok=True); pf = pq.ParquetFile(src); t = pf.read()
        t2 = t.filter(pc.invert(pc.is_in(t["id"], value_set=pa.array(sorted(ids)))))
        pq.write_table(t2, dst, compression="zstd", row_group_size=pf.metadata.row_group(0).num_rows); return t.num_rows, t2
    m = json.load(open(f"{S}/cur/manifest.json")); removed = collections.Counter()
    for f in ("data/train-00001.parquet", "data/train-00002.parquet"):
        old = pq.read_table(f"{S}/cur/{f}", columns=["id", "image_licence_basis"]).to_pylist()
        for r in old:
            if r["id"] in D["v1.1"]: removed[r["image_licence_basis"]] += 1
        n0, t2 = rewrite(f"{S}/cur/{f}", f"{S}/new/{f}", D["v1.1"])
        m["shards"][f] = {**m["shards"][f], "rows": t2.num_rows, "sha256": sha(f"{S}/new/{f}")}; log(f, n0, "->", t2.num_rows)
    assert sum(removed.values()) == len(D["v1.1"]) == 18
    m["rows"] -= 18
    for k, v in removed.items(): m["by_licence_basis"][k] -= v
    m["release_row_drop"] = {"rows_removed": 18, "reason": "overlap with reserved evaluation material", "date": "2026-11-27"}
    os.makedirs(f"{S}/new", exist_ok=True); json.dump(m, open(f"{S}/new/manifest.json", "w"), ensure_ascii=False, indent=1)
    f3 = "v2/p3-ops711-714/public/train-00000.parquet"; n0, t2 = rewrite(f"{S}/cur/{f3}", f"{S}/new/{f3}", D["p3-ops711-714"]); assert n0 - t2.num_rows == 532
    m3 = json.load(open(f"{S}/cur/v2/p3-ops711-714/manifest.json")); n1 = t2.num_rows
    m3.update(rows={"public": n1, "internal": 0}, by_licence_basis={"public:pd_il": n1}, by_text_licence={"PD": n1})
    m3["shards"]["public/train-00000.parquet"] = {"rows": n1, "sha256": sha(f"{S}/new/{f3}")}
    m3["release_row_drop"] = {"rows_removed": 532, "reason": "overlap with reserved evaluation material", "date": "2026-11-27"}
    json.dump(m3, open(f"{S}/new/v2/p3-ops711-714/manifest.json", "w"), ensure_ascii=False, indent=1); log("p3", n0, "->", n1)
    r = open(f"{S}/cur/README.md", encoding="utf-8").read().replace("47,997", "47,979").replace("9,492 lines", "8,960 lines")
    r = r.replace("size_categories:\n- 10K<n<100K", "size_categories:\n- 100K<n<1M")
    cfg = lambda name, path: f"- config_name: {name}\n  data_files:\n  - split: train\n    path: {path}\n"
    anchor = cfg("book_level_v2_p4", "v2/p4-ia-pby/public/*.parquet"); assert anchor in r
    r6 = r.replace(anchor, anchor + cfg("book_level_v2_p6", "v2/p6-vilna-volumes/public/*.parquet"), 1)
    P6SEC = """
## v2, part 6: Vilna Talmud, 15 tractates by region (config `book_level_v2_p6`)
- **What:** 119,939 lines from 3,008 leaves of the Vilna Romm Talmud in 15 tractates: Rashi 46,118, Tosafot 53,316,
  Gemara 20,505. Most of it is Rashi script.
- **How:** the region route of part 2 at scale. Each leaf is read straight from the Internet Archive scan. The Gemara,
  Rashi and Tosafot regions are cut out and aligned separately to their own witnesses. A line is kept only when its
  printed surface, digits and CER checks pass.
- **Licences and attribution:**
  - The scans are in the public domain in Israel (`pd_il`), digitized by Duke University Libraries and served by the
    Internet Archive.
  - Rashi, Rashbam and Tosafot labels: the Vilna Edition witnesses in Sefaria, public domain (`text_licence = PD`).
  - **Gemara labels: the Hebrew Wikisource Talmud Bavli via Sefaria, CC BY-SA 4.0 (`text_licence = CC-BY-SA`).**
    Attribute "Hebrew Wikisource contributors" (https://he.wikisource.org/wiki/תלמוד_בבלי) and Sefaria, and share
    alike. The dataset as a whole is CC BY-SA 4.0.
- **Credit:** Rivok Labs (method), Sefaria, Hebrew Wikisource contributors, Duke University Libraries, the Internet
  Archive, and HeOCR's opensrc worker (the region runner).
- **Quality:** a manual check of 20 random lines found no defects.
- **Evaluation hygiene:** no evaluation set uses these volumes. The independent CLEAN check kept every line, and lines
  sharing text with evaluation material are tagged privately.
"""
    CHG = "\n## Changes in this version\n550 rows removed for overlap with reserved evaluation material: 532 in part 3 and 18 in v1.1.\n"
    open(f"{S}/README_v2p6.md", "w", encoding="utf-8").write(r6.rstrip("\n") + "\n" + P6SEC + CHG)
    P4BSEC = """
## v2, part 4b: pointed (niqqud) print, Ben-Yehuda works in their 1880–1930 printings (config `book_level_v2_p4b`)
- **What:** 12,001 lines of pointed (vocalized) Hebrew print, from 28 Project Ben-Yehuda works on 16 Internet Archive books
  printed 1880–1930. The labels keep the niqqud.
- **How:** as part 4, but only for books whose own pages print niqqud, checked by vowel-mark density over the work's
  pages. 96% of labels carry full niqqud.
- **Licences:** images `pd_il` (faithful facsimiles of the original printings). Text is public domain (Ben-Yehuda).
  These rows fall under the dataset's CC BY-SA 4.0.
- **Quality:** in a manual check of random lines, every sampled line matched its pointed print.
- **Evaluation hygiene:** HeOCR's pointed-print evaluation works, the DEV works and every other scan or printing of them
  were excluded before the build. The independent CLEAN check passed with every line kept.
"""
    r6b = r6.replace(anchor, anchor + cfg("book_level_v2_p4b", "v2/p4b-ia-pby-pointed/public/*.parquet"), 1)
    open(f"{S}/README_v2p6b.md", "w", encoding="utf-8").write(r6b.rstrip("\n") + "\n" + P4BSEC + P6SEC + CHG)
    m6 = json.load(open(f"{P6}/manifest.json"))
    m6.update(state="public", by_text_licence={"PD": 99434, "CC-BY-SA": 20505}, clean={"record": "HeOCR/heocr-restricted-eval#1931", "result": "119,939/119,939 keep, 0 exclusions; 84 text tags"},
              builder={"runner": "heocr-ops #729/#730/#732 (opensrc Vilna volume runner)", "packager": "htext pack_vilna_volumes.py"},
              attribution={"gemara_labels": "Hebrew Wikisource Talmud Bavli via Sefaria, CC BY-SA 4.0: Hebrew Wikisource contributors", "commentary_labels": "Vilna Edition via Sefaria, PD"})
    json.dump(m6, open(f"{S}/manifest_p6.json", "w"), ensure_ascii=False, indent=1)
    m4 = json.load(open(f"{P4B}/manifest.json"))
    m4.update(by_licence_basis={"public:pd_il": 12001}, by_text_licence={"PD": 12001}, clean={"record": "HeOCR/heocr-restricted-eval#1933", "result": "12,001/12,001 keep, 0 exclusions; 28 text tags"},
              builder={"htext_commit": "01528fb", "driver": "htext.linepairs.editions (page direction #79)", "labels": "PBY public_domain_dump @5e4277fe txt (pointed)"})
    json.dump(m4, open(f"{S}/manifest_p4b.json", "w"), ensure_ascii=False, indent=1)
    st["staged"] = True; save(); log("staged")
f6 = {f"v2/p6-vilna-volumes/public/{os.path.basename(f)}": f for f in sorted(glob.glob(P6 + "/public/*.parquet"))}
f6["v2/p6-vilna-volumes/manifest.json"] = f"{S}/manifest_p6.json"
for f in ("data/train-00001.parquet", "data/train-00002.parquet", "manifest.json", "v2/p3-ops711-714/public/train-00000.parquet", "v2/p3-ops711-714/manifest.json"):
    f6[f] = f"{S}/new/{f}"
f6["README.md"] = f"{S}/README_v2p6.md"
assert_public_safe(f6.values(), targets=f6.keys())
if not st.get("commit"):
    assert api.dataset_info(R).sha == PARENT, "HF main moved; re-stage on the new parent"
    c = api.create_commit(R, [CommitOperationAdd(k, v) for k, v in f6.items()], repo_type="dataset", parent_commit=PARENT,
        commit_message="v2-p6: Vilna Talmud 15 tractates by region (config book_level_v2_p6, 119,939 lines); 550 rows removed for overlap with reserved evaluation material")
    st["commit"] = c.oid; save(); log("commit p6", c.oid)
if not st.get("tag_p6"): api.create_tag(R, tag="v2-p6", revision=st["commit"], repo_type="dataset"); st["tag_p6"] = True; save()
if not st.get("verified_p6"):
    for k, v in f6.items():
        g = hf_hub_download(R, k, repo_type="dataset", revision=st["commit"], token=False, local_dir=f"{S}/rb"); assert sha(g) == sha(v), k; os.remove(g)
    st["verified_p6"] = True; save(); log("verified p6", len(f6))
f4 = {"v2/p4b-ia-pby-pointed/public/train-00000.parquet": f"{P4B}/public/train-00000.parquet", "v2/p4b-ia-pby-pointed/manifest.json": f"{S}/manifest_p4b.json", "README.md": f"{S}/README_v2p6b.md"}
assert_public_safe(f4.values(), targets=f4.keys())
if not st.get("commit_p4b"):
    c = api.create_commit(R, [CommitOperationAdd(k, v) for k, v in f4.items()], repo_type="dataset", parent_commit=st["commit"],
        commit_message="v2-p4b: pointed (niqqud) print, Ben-Yehuda works 1880-1930 (config book_level_v2_p4b, 12,001 lines)")
    st["commit_p4b"] = c.oid; save(); log("commit p4b", c.oid)
if not st.get("tag_p4b"): api.create_tag(R, tag="v2-p4b", revision=st["commit_p4b"], repo_type="dataset"); st["tag_p4b"] = True; save()
if not st.get("verified_p4b"):
    for k, v in f4.items():
        g = hf_hub_download(R, k, repo_type="dataset", revision=st["commit_p4b"], token=False, local_dir=f"{S}/rb"); assert sha(g) == sha(v), k; os.remove(g)
    st["verified_p4b"] = True; save(); log("verified p4b")
log("HF_DONE")

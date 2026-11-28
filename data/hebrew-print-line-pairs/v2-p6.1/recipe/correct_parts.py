"""Build corrected v2 parts 1, 3, 4 locally (lead 2026-11-28). Publishes nothing.
Marked rows below the part's strip threshold (marks per Hebrew letter: p1, p4 < 0.30; p3 < 0.10) lose ALL marks.
Marked rows at or above it are HELD: left out of the corrected files, so new TRAIN scopes cannot pick them up.
All other rows are byte-for-byte the same values."""
import hashlib, io, json, os, re, subprocess, sys
import pyarrow as pa, pyarrow.parquet as pq
from htext.linepairs.rivok_align import MARKS, cer
NIQ = re.compile("[ְ-ׇּׁׂ]")
REV = "dca089016e6cc389997b533cbf5cee4fcc3df2a3"
URL = f"https://huggingface.co/datasets/HeOCR/hebrew-print-line-pairs/resolve/{REV}"
OUT = os.path.expanduser("~/temp/heocr/downloads/v2/parts-corrected")
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
def fetch(path, dest):
    subprocess.run(["curl", "-sfL", "--retry", "5", "-A", "htext-fetch/0.1", "-o", dest, f"{URL}/{path}"], check=True)
for part, limit in [("p1-ops707", 0.30), ("p3-ops711-714", 0.10), ("p4-ia-pby", 0.30)]:
    d = f"{OUT}/{part}"; os.makedirs(f"{d}/public")
    fetch(f"v2/{part}/manifest.json", f"{d}/manifest_published.json")
    m = json.load(open(f"{d}/manifest_published.json"))
    c = dict(rows_published=0, stripped=0, marks_removed=0, held=0, unchanged=0); shards = {}; held_ids = []
    for name, info in m["shards"].items():
        src = f"{d}/src.parquet"; fetch(f"v2/{part}/{name}", src)
        assert sha(src) == info["sha256"], (part, name)
        t = pq.read_table(src); keep, texts = [], []
        for i, (rid, x) in enumerate(zip(t["id"].to_pylist(), t["text"].to_pylist())):
            c["rows_published"] += 1; n = len(NIQ.findall(x))
            if n:
                if n / max(1, sum("א" <= ch <= "ת" for ch in x)) >= limit:
                    c["held"] += 1; held_ids.append(rid); continue
                y = MARKS.sub("", x); assert y.strip() and not NIQ.search(y)
                c["stripped"] += 1; c["marks_removed"] += len(x) - len(y); x = y
            else:
                c["unchanged"] += 1
            keep.append(i); texts.append(x)
        new = t.take(pa.array(keep)); k = new.schema.get_field_index("text")
        new = new.set_column(k, new.schema.field(k), pa.array(texts, type=new.schema.field(k).type))
        assert new.schema.equals(t.schema, check_metadata=True)
        pq.write_table(new, f"{d}/{name}", compression="zstd"); os.remove(src)
        shards[name] = {"rows": new.num_rows, "sha256": sha(f"{d}/{name}")}
    c["rows_corrected"] = sum(s["rows"] for s in shards.values())
    assert c["rows_corrected"] == c["stripped"] + c["unchanged"]
    m["shards"] = shards; m["rows"] = {"public": c["rows_corrected"]}
    for key in ("by_licence_basis", "by_text_licence"):  # recompute only where one class covers every row
        if key in m:
            assert len(m[key]) == 1, (part, key, m[key]); m[key] = {list(m[key])[0]: c["rows_corrected"]}
    m["correction"] = {"of_revision": REV, "strip_below_marks_per_letter": limit, "counts": c,
                       "label_caveat": "Niqqud in these labels follows the Project Ben-Yehuda text; it has not been verified mark by mark against the printed scan."}
    json.dump(m, open(f"{d}/manifest.json", "w"), ensure_ascii=False, indent=1)
    json.dump(held_ids, open(f"{OUT}/{part}.held_ids.private.json", "w"))  # local only, never published
    open(f"{d}/CHANGELOG.md", "w").write(
        f"# v2 {part}: niqqud correction\n\n- {c['stripped']:,} rows: all niqqud and cantillation marks removed from the label ({c['marks_removed']:,} characters). "
        f"These rows had marks on under {int(limit*100)}% of their letters.\n- {c['held']:,} more heavily marked rows are left out until their marks are checked against the scans.\n"
        f"- {c['unchanged']:,} rows unchanged. Rows: {c['rows_published']:,} to {c['rows_corrected']:,}. Images and all other columns are unchanged.\n- {m['correction']['label_caveat']}\n")
    os.remove(f"{d}/manifest_published.json")
    print(part, json.dumps(c)); print(" manifest", sha(f"{d}/manifest.json"), "changelog", sha(f"{d}/CHANGELOG.md"))
    for n, s in shards.items(): print(" ", n, s["rows"], s["sha256"])

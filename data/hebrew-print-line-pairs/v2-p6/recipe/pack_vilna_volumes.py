"""Pack the 3,008-leaf Vilna Romm volume candidates (opensrc #729/#730/#732 runner) into the htext #64 part layout.
Rows: native crop bytes (sha256-checked against the receipt), the frozen witness label, region role, IA JP2 member URL +
sha256, leaf/folio, native box. Licences: images pd_il; Rashi/Rashbam/Tosafot labels PD (Vilna Edition via Sefaria),
Gemara labels CC-BY-SA (Wikisource Talmud Bavli via Sefaria). Usage: pack_vilna_volumes.py CANDIDATES OUT"""
import glob, gzip, hashlib, io, json, os, sys, collections
import pyarrow as pa, pyarrow.parquet as pq
C, OUT = sys.argv[1], sys.argv[2]; PART = "p6-vilna-volumes"
os.makedirs(f"{OUT}/public", exist_ok=True)
SCHEMA = pa.schema([("id", pa.string()), ("image", pa.struct([("bytes", pa.binary()), ("path", pa.string())])), ("text", pa.string()),
    ("ocr_text", pa.string()), ("cer_nomarks", pa.float64()), ("bbox", pa.list_(pa.int64())), ("source_id", pa.string()),
    ("scan_url", pa.string()), ("scan_digest", pa.string()), ("scan_page", pa.int64()), ("transcription_id", pa.string()),
    ("transcription_sha256", pa.string()), ("image_sha256", pa.string()), ("tags", pa.list_(pa.string())),
    ("image_licence_basis", pa.string()), ("text_licence", pa.string()), ("privacy_gate", pa.string())])
rows, stats, prov = [], collections.Counter(), []
for f in sorted(glob.glob(f"{C}/*/*/receipt.json")):
    d = json.load(open(f)); leaf = d["native"]
    if d["state"] != "pre_clean_candidate": stats[f"leaf:{d['state']}"] += 1; continue
    for role, reg in d["regions"].items():
        wid = d["witness_ids"].get("inner" if role == "rashi" else role) or d["witness_ids"].get(role)
        for c in reg.get("candidates", []) or []:
            p = os.path.join(os.path.dirname(f), role, c["path"]); b = open(p, "rb").read()
            h = hashlib.sha256(b).hexdigest()
            if h != c["crop_sha256"]: stats["crop_sha_mismatch"] += 1; continue
            if hashlib.sha256(c["text"].encode()).hexdigest() != c["label_sha256"]: stats["label_sha_mismatch"] += 1; continue
            rid = f'{PART}/{d["accession"]}/{d["id"]}/{role}/l{c["line"]:03d}'
            rows.append({"id": rid, "image": {"bytes": b, "path": f'{d["id"]}_{role}_{c["line"]:03d}.png'}, "text": c["text"], "ocr_text": "",
                         "cer_nomarks": float(c["cer_nomarks"]), "bbox": list(map(int, c["native_box"])), "source_id": f'{d["accession"]}:{d["id"]}',
                         "scan_url": leaf["url"], "scan_digest": leaf["sha256"], "scan_page": int(leaf["native_leaf"]), "transcription_id": wid,
                         "transcription_sha256": reg.get("witness_daf_sha256"), "image_sha256": h,
                         "tags": ["book_level", "vilna_romm_volumes", f"region:{role}", f"model:{c.get('recognition_model')}"],
                         "image_licence_basis": "pd_il", "text_licence": "CC-BY-SA" if role == "gemara" else "PD", "privacy_gate": None})
            prov.append({"id": rid, "printed_folio": leaf.get("printed_folio"), "route": c.get("route"), "quality_route": c.get("quality_route"),
                         "crop_route": c.get("crop_route"), "gutter_crossing_pixels": c.get("gutter_crossing_pixels"), "model_sha256": c.get("model_sha256"),
                         "label_sha256": c["label_sha256"], "queue_sha256": d["queue_sha256"], "volume_sha256": d["volume_sha256"]})
            stats[f"role:{role}"] += 1; stats[f"text:{'CC-BY-SA' if role == 'gemara' else 'PD'}"] += 1
rows.sort(key=lambda r: r["id"]); man = {"part": PART, "version": "v2", "rows": {"public": len(rows), "internal": 0}, "state": "private_pre_clean",
    "shards": {}, "by_licence_basis": {"public:pd_il": len(rows)}, "stats": dict(stats)}
for i in range(0, len(rows), 20000):
    buf = io.BytesIO(); pq.write_table(pa.Table.from_pylist(rows[i:i + 20000], schema=SCHEMA), buf, compression="zstd")
    n = f"public/train-{i // 20000:05d}.parquet"; open(f"{OUT}/{n}", "wb").write(buf.getvalue())
    man["shards"][n] = {"rows": len(rows[i:i + 20000]), "sha256": hashlib.sha256(buf.getvalue()).hexdigest()}
open(f"{OUT}/row-provenance.jsonl.gz", "wb").write(gzip.compress("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in prov).encode(), mtime=0))
open(f"{OUT}/private-tags.jsonl.gz", "wb").write(gzip.compress("".join(json.dumps({"id": r["id"], "tags": []}) + "\n" for r in rows).encode(), mtime=0))
json.dump(man, open(f"{OUT}/manifest.json", "w"), ensure_ascii=False, indent=1); print(json.dumps({"rows": len(rows), "stats": stats}))

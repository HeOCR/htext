"""(python -m htext.linepairs.release_editions) Package book-level (edition-pair) line pairs as Parquet shards with per-line provenance.
--gate: a privacy gate result (gate.jsonl); only lines it kept are packaged, and each row carries privacy_gate.
--basis / --public: licence basis for every row, and whether rows may be public (default: internal, training only).
Label normalisation for Word-sourced text: two gereshes (׳׳) become a gershayim (״), as printed."""
import argparse, collections, hashlib, io, json, os
from pathlib import Path
from htext.linepairs.editions import safe_id
import pyarrow as pa, pyarrow.parquet as pq
ap = argparse.ArgumentParser()
ap.add_argument("--manifest", type=Path, required=True); ap.add_argument("--work", type=Path, required=True)
ap.add_argument("--out", type=Path, required=True); ap.add_argument("--gate", type=Path, default=None)
ap.add_argument("--basis", required=True); ap.add_argument("--public", action="store_true"); ap.add_argument("--version", required=True)
ap.add_argument("--source-tag", required=True)
ap.add_argument("--part-id", default=None, help="v2 layout: id prefix and manifest part (docs/linepairs_release_v2.md)")
ap.add_argument("--text-licence", default=None, help="the transcriptions' licence (PD, CC0, CC-BY, CC-BY-SA)")
ap.add_argument("--skip-prefix", action="append", default=[])
ap.add_argument("--drop-extra-digits", action="store_true", help="drop lines whose label has a digit run the OCR did not read (PBY renumbers footnotes)")
a = ap.parse_args()
def atomic(p, data):
    p.parent.mkdir(parents=True, exist_ok=True); t = p.with_name(f".{p.name}.tmp")
    with open(t, "wb") as f: f.write(data); f.flush(); os.fsync(f.fileno())
    os.replace(t, p)
man = json.loads(a.manifest.read_text(encoding="utf-8"))
gate = {}
if a.gate:
    for l in open(a.gate, encoding="utf-8"):
        g = json.loads(l); gate[(g["book"], g["n"])] = (set(g["keep_lines"]), g["gate"])
rows, stats = [], collections.Counter()
for p in man["pairs"]:
    if any(p["id"].startswith(x) for x in a.skip_prefix): continue
    sid = safe_id(p["id"]); s, t = p["scan"], p["transcription"]
    for rf in sorted((a.work / "pilot" / "receipts" / sid).glob("p*.json")):
        r = json.load(open(rf))
        if a.gate and (sid, r["n"]) not in gate and r["kept"]:
            raise SystemExit(f"{sid}/{r['n']}: kept lines but no gate result")
        keep, gid = gate.get((sid, r["n"]), (None, None))
        for k in r["kept"]:
            stats["lines_in"] += 1
            if a.gate and k["line"] not in keep:
                stats["dropped:privacy_gate"] += 1; continue
            crop = a.work / "pilot" / "lines" / sid / f"p{r['n']:04d}" / f"p{r['n']:04d}_l{k['line']:03d}.png"
            if a.drop_extra_digits:
                import re as _re
                if set(_re.findall(r"[0-9]+", k["label"])) - set(_re.findall(r"[0-9]+", k["ocr"])):
                    stats["dropped:digits_extra"] += 1; continue
            img = crop.read_bytes(); label = k["label"].replace("׳׳", "״")
            stats["normalised_gershayim"] += label != k["label"]
            rows.append({"id": (f"{a.part_id}/" if a.part_id else "") + f"{sid}/p{r['n']:04d}/l{k['line']:03d}", "image": {"bytes": img, "path": crop.name}, "text": label,
                         "ocr_text": k["ocr"], "cer_nomarks": float(k["cer_nomarks"]), "bbox": list(map(int, k["bbox"])),
                         "source_id": p["id"], "scan_url": s["url"], "scan_digest": s.get("sha256") or s.get("sha1"), "scan_page": r["n"],
                         "transcription_id": t.get("id") or t["url"], "transcription_sha256": t["sha256"], "image_sha256": hashlib.sha256(img).hexdigest(),
                         "tags": ["book_level", a.source_tag], "image_licence_basis": a.basis, "text_licence": a.text_licence or a.basis,
                         "privacy_gate": gid, "public": a.public})
rows.sort(key=lambda r: r["id"])
part = "public" if a.public else "internal"
manifest = {"version": a.version, "part": a.part_id, "rows": {part: len(rows)}, "shard_part": part, "basis": a.basis, "stats": dict(stats), "shards": {},
            "inputs": {"manifest": str(a.manifest.name), "manifest_sha256": hashlib.sha256(a.manifest.read_bytes()).hexdigest()}}
side = "".join(json.dumps({"id": r["id"], "tags": r["tags"]}, ensure_ascii=False) + "\n" for r in rows)
import gzip as _g; atomic(a.out / "private-tags.jsonl.gz", _g.compress(side.encode(), mtime=0))
for i in range(0, len(rows), 20000):
    chunk = [{k: v for k, v in r.items() if k != "public"} for r in rows[i:i + 20000]]
    buf = io.BytesIO(); pq.write_table(pa.Table.from_pylist(chunk), buf, compression="zstd")
    name = f"{part}/train-{i // 20000:05d}.parquet"; atomic(a.out / name, buf.getvalue())
    manifest["shards"][name] = {"rows": len(chunk), "sha256": hashlib.sha256(buf.getvalue()).hexdigest()}
atomic(a.out / "manifest.json", (json.dumps(manifest, ensure_ascii=False, indent=1) + "\n").encode())
print(json.dumps({k: manifest[k] for k in ("rows", "part", "stats")}, ensure_ascii=False))

"""Write data/sefaria/v3/sources.v3.json from the rights-checked plan and the fetched version files.

Inputs (all local, from the fetch step):
  --plan      the rights-checked plan (works, versions, rights pass/basis; heocr-data coordination rev 3)
  --index     Sefaria's index tree (api/index), for the commentary/dependence flag
  --export    Sefaria-Export books.json at the pinned commit
  --ledger    one or more fetch ledgers (jsonl: path, url, sha256) for the version files
  --files     the directory the ledger paths are relative to

Per work it keeps one main version (most permissive lane first, then Sefaria's priority) and, when another version is
pointed, one pointed version too; both are recorded. Works whose versions all fail the rights rule are listed with
their reasons (the builder writes them to the card's "Left out" table).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

LANE_RANK = {"cc0": 0, "by": 1, "by-sa": 2}
POINTING = re.compile(r"[ְ-ׇּׁׂ]")
LETTER = re.compile(r"[א-ת]")
POINTED_RATIO = 0.25  # pointing marks per letter, over the whole version


def _walk(node, out):
    for x in node if isinstance(node, list) else [node]:
        if "title" in x and "contents" not in x:
            out[x["title"]] = x
        if "contents" in x:
            _walk(x["contents"], out)


def _text(x) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, list):
        return " ".join(_text(y) for y in x)
    if isinstance(x, dict):
        return " ".join(_text(y) for y in x.values())
    return ""


def aramaic_heavy(title: str, cats: list[str], entry: dict) -> bool:
    commentary = bool(entry.get("dependence") or entry.get("base_text_titles"))
    if cats[:1] == ["Talmud"] and len(cats) > 1 and cats[1] in ("Bavli", "Yerushalmi") and not commentary:
        return True
    return ("Targum" in cats and not commentary) or title.startswith("Zohar")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", type=Path, required=True)
    ap.add_argument("--index", type=Path, required=True)
    ap.add_argument("--export", type=Path, required=True)
    ap.add_argument("--export-commit", required=True)
    ap.add_argument("--ledger", type=Path, action="append", required=True)
    ap.add_argument("--files", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    plan = json.loads(a.plan.read_text(encoding="utf-8"))
    idx: dict = {}
    _walk(json.loads(a.index.read_text(encoding="utf-8")), idx)
    fetched = {}
    for led in a.ledger:
        for line in led.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if "sha256" in r:
                doc = json.loads((a.files / r["path"]).read_text(encoding="utf-8"))
                t = _text(doc.get("text"))
                ratio = len(POINTING.findall(t)) / max(1, len(LETTER.findall(t)))
                fetched[(doc["title"], doc["versionTitle"])] = {"file": r["path"], "sha256": r["sha256"], "url": r["url"],
                                                                "license_in_file": doc.get("license"), "priority": doc.get("priority") or 0,
                                                                "pointing_ratio": round(ratio, 3)}
    works, missing, mismatched = [], [], []
    for w in plan["works"]:
        if w["status"] != "planned":
            continue
        cand = []
        for v in w["versions"]:
            f = fetched.get((w["title"], v["versionTitle"]))
            if v["rights"]["pass"] and f is None:
                missing.append([w["title"], v["versionTitle"]])
                continue
            if f is not None and f["license_in_file"] != v["license"]:
                # Fail closed: the fetched file and the live API disagree on the licence; hold the version.
                v = dict(v, rights={"pass": False, "basis": f"licence_mismatch:api={v['license']}:file={f['license_in_file']}"})
                mismatched.append([w["title"], v["versionTitle"], v["rights"]["basis"]])
            cand.append((v, f))
        passing = [(v, f) for v, f in cand if v["rights"]["pass"]]
        failing = [{"versionTitle": v["versionTitle"], "license": v["license"], "file": None, "sha256": None, "rights": v["rights"]}
                   for v, _ in cand if not v["rights"]["pass"]]
        failing += [{"versionTitle": v["versionTitle"], "license": v["license"], "file": None, "sha256": None, "rights": v["rights"]}
                    for v in w["versions"] if not v["rights"]["pass"] and all(v["versionTitle"] != c["versionTitle"] for c in failing)]
        chosen = []
        if passing:
            passing.sort(key=lambda vf: (LANE_RANK[vf[0]["lane"]], -float(vf[1]["priority"]), vf[1]["pointing_ratio"]))
            chosen.append(passing[0])
            pointed = [vf for vf in passing[1:] if vf[1]["pointing_ratio"] >= POINTED_RATIO]
            if passing[0][1]["pointing_ratio"] < POINTED_RATIO and pointed:
                chosen.append(pointed[0])
        cats = w["categories"]
        works.append({
            "title": w["title"], "heTitle": w.get("heTitle"), "categories": cats, "tags": w.get("tags", []),
            "aramaic_heavy": aramaic_heavy(w["title"], cats, idx.get(w["title"], {})),
            "versions": [{"versionTitle": v["versionTitle"], "license": v["license"], "lane": v["lane"],
                          "versionSource": v.get("versionSource"), "role": "main" if i == 0 else "pointed",
                          "file": f["file"], "sha256": f["sha256"], "url": f["url"], "pointing_ratio": f["pointing_ratio"],
                          "rights": v["rights"]} for i, (v, f) in enumerate(chosen)] + failing,
        })
    out = {"schema": "htext_sefaria_sources.v3",
           "export": {"repo": "Sefaria/Sefaria-Export", "commit": a.export_commit,
                      "books_json_sha256": hashlib.sha256(a.export.read_bytes()).hexdigest(),
                      "generated_at": json.loads(a.export.read_text(encoding="utf-8"))["generated_at"]},
           "plan_sha256": hashlib.sha256(a.plan.read_bytes()).hexdigest(), "rights_rule": plan["rights_rule"],
           "missing_files": missing, "licence_mismatches": mismatched, "works": works}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"works {len(works)}, versions chosen {sum(1 for w in works for v in w['versions'] if v['file'])}, missing files {len(missing)}, licence mismatches {len(mismatched)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""CC0 prose pool for the hdocsyngen pilot, from published pby-v3 il_us plain.

Paragraph-sized chunks of consecutive lines of one work, joined with spaces.
"Modern" is a heuristic: genre prose/article/memoir/letters and period
(decade of the latest creator death) >= 1910. Seeded; reads only the
published release assets (checked against data/pby/v3/SHA256SUMS).
"""
import gzip, hashlib, json, random, sys
from collections import defaultdict
from pathlib import Path

src, out = Path(sys.argv[1]), Path(sys.argv[2])
SUMS = {"pby_lines_il_us_plain_v3.txt": "8de0454dfd135ff2987db8964e30e397f9d295f1335b995560e57764a2d961f0",
        "pby_line_index.v1.jsonl.gz": "52a5b359992a904bf210a3402d3fa79c99fac50ecd218662aa1ded0b34561ff4"}
for name, digest in SUMS.items():
    assert hashlib.sha256((src / name).read_bytes()).hexdigest() == digest, name
GENRES, MIN_PERIOD = {"prose", "article", "memoir", "letters"}, 1910
TARGET, PER_WORK, MIN_CHARS, MAX_CHARS, SEED = 4000, 25, 250, 450, 15

rows = [r for r in map(json.loads, gzip.open(src / "pby_line_index.v1.jsonl.gz", "rt"))
        if r["il_us"] and r["subset"] == "plain"]
lines = (src / "pby_lines_il_us_plain_v3.txt").read_text(encoding="utf-8").split("\n")[: len(rows)]
assert all(hashlib.sha256(l.encode()).hexdigest() == r["sha256"] for l, r in zip(lines, rows))

chunks = defaultdict(list)  # work -> [(first, last, text)]
i = 0
while i < len(rows):
    r = rows[i]
    if r["genre"] not in GENRES or r["period"] < MIN_PERIOD:
        i += 1; continue
    j, text = i, lines[i]
    while len(text) < MIN_CHARS and j + 1 < len(rows) and rows[j + 1]["pby_work_id"] == r["pby_work_id"]:
        j += 1; text += " " + lines[j]
    if MIN_CHARS <= len(text) <= MAX_CHARS:
        chunks[r["pby_work_id"]].append((i, j, text, r["genre"], r["period"]))
    i = j + 1

rng = random.Random(SEED)
picked = []
for work in sorted(chunks):
    c = chunks[work]
    picked += rng.sample(c, min(PER_WORK, len(c)))
rng.shuffle(picked)
picked = sorted(picked[:TARGET], key=lambda c: c[0])

with out.open("w", encoding="utf-8") as f, out.with_suffix(".meta.jsonl").open("w", encoding="utf-8") as m:
    for first, last, text, genre, period in picked:
        work = rows[first]["pby_work_id"]
        eid = f"pby-v3:il_us_plain:L{first + 1}-L{last + 1}"
        f.write(json.dumps({"id": eid, "text": text, "licence": "CC0-1.0",
                            "source": f"htext pby-v3 (https://github.com/HeOCR/htext/releases/tag/pby-v3), pby_lines_il_us_plain_v3.txt lines {first + 1}-{last + 1}, PBY work {work}"},
                           ensure_ascii=False) + "\n")
        m.write(json.dumps({"id": eid, "pby_work_id": work, "genre": genre, "period": period, "modern": True,
                            "line_sha256": [rows[k]["sha256"] for k in range(first, last + 1)]}) + "\n")
print(len(picked), "entries from", len({rows[c[0]]["pby_work_id"] for c in picked}), "works")

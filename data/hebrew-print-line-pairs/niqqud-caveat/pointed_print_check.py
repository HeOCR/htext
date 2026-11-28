#!/usr/bin/env python3
"""Count-only check, per book: are pointed labels sitting on pointed print?

Label side: niqqud marks per Hebrew letter in `text`. Image side: the same rate in `ocr_text`, the pairing model's
own pointed OCR of the crop (automatic, image-derived, NOT ground truth). A row is "pointed" at >= 0.3 marks per
letter; it is "scan not confirming" when its OCR rate is under 0.15 or under half its label rate. A book is flagged
when over 10% of its pointed rows are not confirmed. This detects unpointed or half-pointed print, not wrong marks.

Usage: pointed_print_check.py PARQUET... (needs columns text, ocr_text, source_id)"""
import collections, json, re, statistics, sys

import pyarrow.parquet as pq

NIQ = re.compile("[ְ-ׇּׁׂ]")


def rate(s):
    return len(NIQ.findall(s)) / max(1, sum("א" <= c <= "ת" for c in s))


books, total = collections.defaultdict(list), 0
for f in sys.argv[1:]:
    for r in pq.read_table(f, columns=["text", "ocr_text", "source_id"]).to_pylist():
        total += 1
        books[r["source_id"].split(":pby:")[0]].append((rate(r["text"]), rate(r["ocr_text"] or "")))
out = []
for b, v in sorted(books.items()):
    dense = [(a, o) for a, o in v if a >= 0.3]
    bad = [(a, o) for a, o in dense if o < 0.15 or o < a / 2]
    out.append({"book": b, "rows": len(v), "pointed_rows": len(dense), "scan_not_confirming": len(bad),
                "scan_shows_no_mark": sum(o == 0 for _, o in dense),
                "label_marks_per_letter": round(statistics.median(a for a, _ in v), 3),
                "scan_marks_per_letter": round(statistics.median(o for _, o in v), 3),
                "flagged": len(bad) > 0.1 * max(1, len(dense))})
keys = ("rows", "pointed_rows", "scan_not_confirming", "scan_shows_no_mark")
print(json.dumps({"rows": total, "books": len(out), "flagged_books": [x["book"] for x in out if x["flagged"]],
                  "totals": {k: sum(x[k] for x in out) for k in keys}, "per_book": out}, indent=1))

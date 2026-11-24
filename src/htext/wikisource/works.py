"""Load the manually reviewed allowlist used by the main-namespace builder."""

from __future__ import annotations

import json
from pathlib import Path

from htext.wikisource.dump import title_key

SCHEMA = "htext_wikisource_works.v1"


def load_works(path: Path, *, as_of: int) -> dict[str, dict]:
    """Return reviewed roots by normalized title; reject ambiguous records."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA or not isinstance(doc.get("works"), list):
        raise ValueError(f"expected {SCHEMA} with a works list")
    result = {}
    for row in doc["works"]:
        if not isinstance(row, dict):
            raise ValueError("each work must be an object")
        root, work, authors, basis, note = (row.get(k) for k in ("root", "work", "authors", "pd_israel_basis", "reviewer_note"))
        if not all(isinstance(x, str) and x.strip() for x in (root, work, note)):
            raise ValueError("work root, description and reviewer note are required")
        if "/" in root or ":" in root or not title_key(root):
            raise ValueError("work root must be a main-namespace root title")
        if not isinstance(authors, list) or not authors or any(not isinstance(x, str) or not x.strip() for x in authors):
            raise ValueError("each work must name its authors or describe their era")
        if basis != "ancient" and (type(basis) is not int or basis < 1800 or basis > as_of - 71):
            raise ValueError("rights basis must be ancient or a qualifying death year")
        if "page_revisions" in row:
            pins = row["page_revisions"]
            if not isinstance(pins, dict) or not pins or any(
                not page.isascii() or not page.isdecimal() or page.startswith("0")
                or type(revision) is not int or revision < 1 for page, revision in pins.items()
            ):
                raise ValueError("page_revisions must pin positive page IDs to positive revision IDs")
        key = title_key(root)
        if key in result:
            raise ValueError("duplicate normalized work root")
        result[key] = row
    return result

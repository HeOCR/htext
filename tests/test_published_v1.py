"""Consistency checks on the committed v1 build in data/pby/v1/.

The corpus files and the line index are release assets, not in git; their
sha256s are pinned here by SHA256SUMS and the card.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from htext.pby import PBY_DUMP_COMMIT

V1 = Path(__file__).resolve().parents[1] / "data" / "pby" / "v1"
IN_GIT = {"CORPUS_CARD.md", "corpus_card.json", "pby_excluded_works.v1.json", "pby_rights_index.v1.jsonl.gz"}
RELEASE_ASSETS = {
    "pby_lines_il_plain_v1.txt",
    "pby_lines_il_niqqud_v1.txt",
    "pby_lines_il_us_plain_v1.txt",
    "pby_lines_il_us_niqqud_v1.txt",
    "pby_line_index.v1.jsonl.gz",
}


def _sums() -> dict[str, str]:
    rows = (V1 / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    return {name: digest for digest, name in (row.split("  ") for row in rows)}


def test_sha256sums_cover_git_files_and_release_assets():
    sums = _sums()
    assert set(sums) == IN_GIT | RELEASE_ASSETS
    assert {path.name for path in V1.iterdir()} == IN_GIT | {"SHA256SUMS"}
    for name in IN_GIT:
        assert hashlib.sha256((V1 / name).read_bytes()).hexdigest() == sums[name], name


def test_card_and_exclusion_list_pin_the_same_corpus_files():
    sums = _sums()
    card = json.loads((V1 / "corpus_card.json").read_text(encoding="utf-8"))
    exclusion = json.loads((V1 / "pby_excluded_works.v1.json").read_text(encoding="utf-8"))
    assert {name: info["sha256"] for name, info in card["files"].items()} == {
        name: sums[name] for name in RELEASE_ASSETS if name.endswith(".txt")
    }
    assert exclusion["corpus_sha256"] == {name: info["sha256"] for name, info in card["files"].items()}
    assert card["source"]["commit"] == exclusion["pby_dump_commit"] == PBY_DUMP_COMMIT
    assert card["inputs"]["fit_check"]["ran"] is True
    assert card["inputs"]["fit_check"]["hocrsyngen_commit"] == "88c61af4c12cc4a462fc1f57a1c4027b3459366d"
    assert card["credit"] == {"text": "Project Ben-Yehuda volunteers", "url": "https://benyehuda.org"}
    assert card["parameters"]["content_screen"] == {"terms": 0, "source": None}


def test_rights_index_matches_the_card():
    rows = [json.loads(line) for line in gzip.decompress((V1 / "pby_rights_index.v1.jsonl.gz").read_bytes()).decode("utf-8").splitlines()]
    card = json.loads((V1 / "corpus_card.json").read_text(encoding="utf-8"))
    assert len(rows) == card["source"]["catalogue_rows"] == 26455
    assert sum(row["pd_us"] is True for row in rows) == card["rights"]["pd_us"]["published_before:1931"]
    # The two Davar issue numbers the parser used to read as 1242 and 1262.
    davar = {row["pby_work_id"]: row for row in rows if row["pby_work_id"] in (44082, 44083)}
    assert all(row["source_edition_year"] is None and row["pd_us"] == "unknown" for row in davar.values())
    assert all(row["source_edition_year"] is None or row["source_edition_year"] >= 1450 for row in rows)

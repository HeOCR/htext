"""Checks on the committed, pinned data files."""

from __future__ import annotations

import json
import re
from pathlib import Path

from htext.leakage import NORMALIZATION, Protected
from htext.pby import PBY_DUMP_COMMIT
from htext.pby.rights import Creators

ROOT = Path(__file__).resolve().parents[1]
CREATORS = ROOT / "data" / "pby" / "creators.json"
LEAKAGE = ROOT / "data" / "leakage"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HOCRSYNGEN_COMMIT = "88c61af4c12cc4a462fc1f57a1c4027b3459366d"
HOCRGEN_COMMIT = "c8fb74eb5d0afedd812a0da69562e4610a0b3394"


def test_creators_json_is_pinned_and_well_formed():
    document = json.loads(CREATORS.read_text(encoding="utf-8"))
    assert document["schema"] == "pby_creators.v1"
    assert document["source"]["dump_commit"] == PBY_DUMP_COMMIT
    assert document["source"]["properties"] == {"death": "P570", "birth": "P569"}
    rows = document["creators"]
    qids = [row["qid"] for row in rows]
    assert len(qids) == len(set(qids)) == 903
    assert qids == sorted(qids, key=lambda qid: int(qid[1:]))
    assert "Q0" not in qids
    for row in rows:
        assert isinstance(row["wikidata_revision"], int)
        assert row["death_year"] is None or isinstance(row["death_year"], int)
        assert row["death_year_precision"] in (None, "day", "month", "year", "decade", "century", "millennium")
        assert (row["death_year"] is None) == (row["death_year_precision"] is None)
    Creators(document)


def test_leakage_fixtures_are_pinned_hash_only_files():
    fixtures = {
        fixture["source"]["path"]: fixture
        for path in sorted(LEAKAGE.glob("*.hashes.json"))
        for fixture in json.loads(path.read_text(encoding="utf-8"))["fixtures"]
    }
    texts = "src/hocrsyngen/data/synthetic/texts/"
    assert set(fixtures) == {
        "docs/evaluation-fixtures/bidi-synthetic-corpus.txt",
        texts + "hebrew_lines.txt",
        texts + "hebrew_lines_eval_v1.txt",
        texts + "hebrew_lines_niqqud_eval_v1.txt",
        texts + "hebrew_mixed_lines_eval_v1.txt",
        texts + "hebrew_typographic_lines_eval_v1.txt",
    }
    for path, fixture in fixtures.items():
        source = fixture["source"]
        if path.startswith("docs/"):
            assert (source["repository"], source["commit"], source["lines"]) == ("HeOCR/hocrgen", HOCRGEN_COMMIT, 100)
        else:
            assert (source["repository"], source["commit"]) == ("HeOCR/hocrsyngen", HOCRSYNGEN_COMMIT)
        assert fixture["normalization"] == NORMALIZATION and fixture["stripped"] is True
        assert HEX64.match(source["sha256"])
        assert all(HEX64.match(digest) for digest in fixture["line_sha256"] + fixture["word3_sha256"])
        assert len(fixture["line_sha256"]) >= source["lines"]
    assert len(Protected.load(sorted(LEAKAGE.glob("*.hashes.json"))).sources) == 6

"""The works allowlist must reject unsafe or ambiguous rights records."""

import json
from pathlib import Path

import pytest

from htext.wikisource.works import load_works


def test_allowlist_requires_reviewed_roots(tmp_path):
    path = tmp_path / "works.json"
    row = {"root": "ספר בדוי", "work": "Invented work", "authors": ["Ancient author"],
           "pd_israel_basis": "ancient", "reviewer_note": "Fixture only"}

    def load(rows):
        path.write_text(json.dumps({"schema": "htext_wikisource_works.v1", "works": rows}))
        return load_works(path, as_of=2026)

    assert load([row])["ספר בדוי"] == row
    assert load([{**row, "pd_israel_basis": 1955}])
    for change in ({"pd_israel_basis": 1956}, {"pd_israel_basis": True}, {"authors": []},
                   {"reviewer_note": ""}, {"root": "ספר/פרק"}, {"root": "עמוד:ספר"}):
        with pytest.raises(ValueError):
            load([{**row, **change}])
    with pytest.raises(ValueError, match="duplicate"):
        load([row, {**row, "root": "ספר_בדוי"}])


def test_repository_allowlist_has_valid_entries():
    path = Path(__file__).parents[1] / "data/wikisource/works.v1.json"
    assert load_works(path, as_of=2026)

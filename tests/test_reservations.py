"""Whole-work eval reservations."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from htext.pby.build import build
from htext.reservations import SCHEMA, Reservations
from tests.test_build import _config


def _write(path: Path, works, **overrides) -> Path:
    document = {"schema": SCHEMA, "set": "TEST-v1", "registry": "example/registry#1", "works": works}
    document.update(overrides)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_load_and_lookup(tmp_path):
    path = _write(tmp_path / "r.json", [{"source": "pby", "work_id": 2}, {"source": "pby", "work_id": "8"}, {"source": "other", "work_id": "x"}])
    reservations = Reservations.load([path])
    assert reservations.reserved("pby", 2) and reservations.reserved("pby", "8")
    assert not reservations.reserved("pby", 1) and not reservations.reserved("other", 2)
    (row,) = reservations.card()
    assert row == {
        "set": "TEST-v1",
        "registry": "example/registry#1",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "works": {"other": 1, "pby": 2},
    }


@pytest.mark.parametrize(
    "overrides, works",
    [
        ({"schema": "something_else"}, [{"source": "pby", "work_id": 1}]),
        ({"set": ""}, [{"source": "pby", "work_id": 1}]),
        ({}, []),
        ({}, [{"source": "pby"}]),
        ({}, [{"work_id": 1}]),
    ],
)
def test_malformed_files_are_refused(tmp_path, overrides, works):
    with pytest.raises(ValueError):
        Reservations.load([_write(tmp_path / "r.json", works, **overrides)])


def test_a_reserved_work_is_left_out_whole(mini_dump, mini_creators, mini_leakage, tmp_path):
    reserved = _write(tmp_path / "reserved.json", [{"source": "pby", "work_id": 2}])
    output = tmp_path / "out"
    card = build(_config(mini_dump, mini_creators, mini_leakage, output, reservations=[reserved]))
    index = [json.loads(line) for line in gzip.decompress((output / "pby_line_index.v1.jsonl.gz").read_bytes()).decode("utf-8").splitlines()]
    assert {row["pby_work_id"] for row in index} == {1, 8}
    assert card["pipeline"]["works_skipped:eval_reserved"] == 1
    excluded = json.loads((output / "pby_excluded_works.v1.json").read_text(encoding="utf-8"))
    assert 2 not in {row["pby_work_id"] for row in excluded["works"]}
    # The card names the set and the file, never the reserved ids.
    (row,) = card["inputs"]["eval_reservations"]
    assert row["works"] == {"pby": 1} and row["set"] == "TEST-v1"
    assert '"work_id"' not in (output / "corpus_card.json").read_text(encoding="utf-8")
    assert "set `TEST-v1`" in (output / "CORPUS_CARD.md").read_text(encoding="utf-8")


def test_no_reservations_is_recorded(mini_dump, mini_creators, mini_leakage, tmp_path):
    output = tmp_path / "out"
    card = build(_config(mini_dump, mini_creators, mini_leakage, output))
    assert card["inputs"]["eval_reservations"] == []
    assert "Eval reservations: works reserved by HeOCR's evaluation are left out whole. none loaded." in (output / "CORPUS_CARD.md").read_text(encoding="utf-8")

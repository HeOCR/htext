"""Whole-unit eval reservations."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from htext.pby.build import build
from htext.reservations import EVAL_SCHEMA, SCHEMA, Reservations
from tests.test_build import _config


def _write(path: Path, works, **overrides) -> Path:
    document = {"schema": SCHEMA, "set": "TEST-v1", "registry": "example/registry#1", "works": works}
    document.update(overrides)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _eval_file(path: Path, sets, schema: str = EVAL_SCHEMA) -> Path:
    path.write_text(json.dumps({"schema": schema, "owner": "eval", "as_of": "2026-11-18", "reservations": sets,
                               "supersedes": {"file": "v1.json", "sha256": "0"}}), encoding="utf-8")
    return path


# Shaped like eval's reservations/eval_reservations_v1.json, with made-up ids.
EVAL_SETS = [
    {"set": "print_scan", "registration": "r", "fixture": "f.json", "pby_work_ids": [2, 77],
     "reshumot_booklets": {"kovetz_hatakanot": [100, 101], "yalkut_hapirsumim": [5]}},
    {"set": "midcentury", "splits": [{"file": "s.json", "sha256": "0"}], "unit_ids": ["plenary:K10_125", "reshumot_scanned:sefer_hachukim_9"]},
    {"set": "pmod", "unit_ids": ["knesset_protocol:398637", "plenary:K10_125"]},
    {"set": "dbench", "source_pages": 750, "note": "n", "reshumot_born_digital_booklets": ["kovetz_hatakanot_100", "sefer_hachukim_7"]},
    {"set": "phist", "labels": {"file": "l.json", "sha256": "0"},
     "item_ids": ["wikisource_he_proofread:ws_index_1725257__p0003", "wikisource_he_proofread:ws_index_1725257__p0011"]},
    {"set": "handwriting", "registration": "r", "note": "n", "hash_source_ids": ["hash_a", "hash_b"]},
    {"set": "line_verify", "pby_work_ids": [3, 4], "pby_work_ids_basis": "alignment", "item_ids": ["benyehuda_nli_aligned:nli_990018546440205171__c0014#L017", "wikisource_he_proofread:ws_index_42__p0002#L005"]},
]


def test_load_and_lookup(tmp_path):
    path = _write(tmp_path / "r.json", [{"source": "pby", "work_id": 2}, {"source": "pby", "work_id": "8"}, {"source": "other", "work_id": "x"}])
    reservations = Reservations.load([path])
    assert reservations.reserved("pby", 2) and reservations.reserved("pby", "8")
    assert not reservations.reserved("pby", 1) and not reservations.reserved("other", 2)
    (row,) = reservations.card()
    assert row == {"schema": SCHEMA, "set": "TEST-v1", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "units": {"other": 1, "pby": 2}}


def test_eval_schema_is_read_and_items_are_cut_to_units(tmp_path):
    reservations = Reservations.load([_eval_file(tmp_path / "eval.json", EVAL_SETS)])
    # v2 adds the PBY works behind line_verify's aligned records, and HASH units.
    assert reservations.units["pby"] == {"2", "77", "3", "4"}
    assert reservations.units["hash"] == {"hash_a", "hash_b"}
    # Scanned and born-digital Reshumot are the same booklets.
    assert reservations.units["reshumot"] == {"kovetz_hatakanot_100", "kovetz_hatakanot_101", "yalkut_hapirsumim_5", "sefer_hachukim_7", "sefer_hachukim_9"}
    assert "reshumot_scanned" not in reservations.units
    assert reservations.reserved("plenary", "K10_125") and reservations.reserved("knesset_protocol", "398637")
    # A Wikisource page reserves its whole Index; an aligned line reserves its whole record.
    assert reservations.units["wikisource"] == {"ws_index_1725257", "ws_index_42"}
    assert "wikisource_he_proofread" not in reservations.units
    assert reservations.units["benyehuda_nli_aligned"] == {"nli_990018546440205171"}
    assert [row["set"] for row in reservations.card()] == [row["set"] for row in EVAL_SETS]
    assert reservations.card()[0]["units"] == {"pby": 2, "reshumot": 3}


# Shaped like eval's v3 P-hist hold-out set, with made-up ids.
PHIST_SET = {
    "set": "P-hist eval hold-out",
    "registration": {"file": "candidates.json", "sha256": "0"},
    "rule": "Each book is held out whole, with every other edition.",
    "books": ["ws_index_900", "someiabook00test"],
    "wikisource_indexes": ["ws_index_900", "ws_index_901"],
    "ia_identifiers": ["someiabook00test", "rashibook00test"],
    "strata": {"rashi_stratum": ["rashibook00test"]},
    "pby_work_ids": [5, 6],
    "sefaria_works": ["Made Up Responsa"],
}


def test_eval_schema_v3_reads_the_phist_holdout(tmp_path):
    path = _eval_file(tmp_path / "v3.json", [*EVAL_SETS, PHIST_SET], schema="heocr_eval_reservations.v3")
    reservations = Reservations.load([path])
    assert reservations.units["wikisource"] == {"ws_index_1725257", "ws_index_42", "ws_index_900", "ws_index_901"}
    assert reservations.units["ia"] == {"someiabook00test", "rashibook00test"}
    assert reservations.units["sefaria"] == {"Made Up Responsa"}
    assert reservations.reserved("pby", 5) and reservations.reserved("pby", "6") and reservations.reserved("pby", 77)
    assert reservations.card()[-1] == {
        "schema": "heocr_eval_reservations.v3",
        "set": "P-hist eval hold-out",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "units": {"ia": 2, "pby": 2, "sefaria": 1, "wikisource": 2},
    }


@pytest.mark.parametrize(
    "sets",
    [
        [],
        [{"set": "x", "wikisource_indexes": ["900"]}],  # not an Index id
        [{"set": "x", "books": ["wikisource:ws_index_900"]}],  # books are bare ids
        [{"set": "x", "new_kind_of_ids": [1]}],  # unknown field: fail closed
        [{"pby_work_ids": [1]}],  # no set name
        [{"set": "x", "note": "only metadata"}],  # reserves nothing
        [{"set": "x", "unit_ids": ["no-prefix"]}],
    ],
)
def test_eval_schema_fails_closed(tmp_path, sets):
    with pytest.raises(ValueError):
        Reservations.load([_eval_file(tmp_path / "eval.json", sets)])


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
    reserved = _eval_file(tmp_path / "eval.json", [{"set": "print_scan", "pby_work_ids": [2]}])
    output = tmp_path / "out"
    card = build(_config(mini_dump, mini_creators, mini_leakage, output, reservations=[reserved]))
    index = [json.loads(line) for line in gzip.decompress((output / "pby_line_index.v1.jsonl.gz").read_bytes()).decode("utf-8").splitlines()]
    assert {row["pby_work_id"] for row in index} == {1, 8}
    assert card["pipeline"]["works_skipped:eval_reserved"] == 1
    excluded = json.loads((output / "pby_excluded_works.v1.json").read_text(encoding="utf-8"))
    assert 2 not in {row["pby_work_id"] for row in excluded["works"]}
    # The card names the set and the file, never the reserved ids.
    (row,) = card["inputs"]["eval_reservations"]
    assert row["units"] == {"pby": 1} and row["set"] == "print_scan"
    assert "pby_work_ids" not in (output / "corpus_card.json").read_text(encoding="utf-8")
    assert "set `print_scan`: 1 pby units" in (output / "CORPUS_CARD.md").read_text(encoding="utf-8")


def test_no_reservations_is_recorded(mini_dump, mini_creators, mini_leakage, tmp_path):
    output = tmp_path / "out"
    card = build(_config(mini_dump, mini_creators, mini_leakage, output))
    assert card["inputs"]["eval_reservations"] == []
    assert "none loaded." in (output / "CORPUS_CARD.md").read_text(encoding="utf-8")

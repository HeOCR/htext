"""Consistency checks on the committed v3 build in data/pby/v3/.

The corpus files and the line index are assets of the ``pby-v3`` release, not
in git; SHA256SUMS and the card pin their sha256s.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from htext.pby import PBY_DUMP_COMMIT

V3 = Path(__file__).resolve().parents[1] / "data" / "pby" / "v3"
IN_GIT = {"CORPUS_CARD.md", "corpus_card.json", "pby_excluded_works.v1.json", "pby_rights_index.v1.jsonl.gz"}
RELEASE_ASSETS = {
    "pby_lines_il_plain_v3.txt",
    "pby_lines_il_niqqud_v3.txt",
    "pby_lines_il_us_plain_v3.txt",
    "pby_lines_il_us_niqqud_v3.txt",
    "pby_line_index.v1.jsonl.gz",
}
# Died 1970, after as_of - 71 = 1955 (manual row in data/pby/creators.json).
CREATOR_IN_TERM = "יהושע השל ייבין"
CREATOR_IN_TERM_WORKS = {47860, 47861, 47862, 47863, 47864, 47865, 48017}


def _sums() -> dict[str, str]:
    rows = (V3 / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    return {name: digest for digest, name in (row.split("  ") for row in rows)}


def _card() -> dict:
    return json.loads((V3 / "corpus_card.json").read_text(encoding="utf-8"))


def _exclusion() -> dict:
    return json.loads((V3 / "pby_excluded_works.v1.json").read_text(encoding="utf-8"))


def _rights() -> list[dict]:
    raw = gzip.decompress((V3 / "pby_rights_index.v1.jsonl.gz").read_bytes()).decode("utf-8")
    return [json.loads(line) for line in raw.splitlines()]


def test_sha256sums_cover_git_files_and_release_assets():
    sums = _sums()
    assert set(sums) == IN_GIT | RELEASE_ASSETS
    assert {path.name for path in V3.iterdir()} == IN_GIT | {"SHA256SUMS"}
    for name in IN_GIT:
        assert hashlib.sha256((V3 / name).read_bytes()).hexdigest() == sums[name], name


def test_card_and_exclusion_list_pin_the_same_corpus_files():
    sums, card, exclusion = _sums(), _card(), _exclusion()
    assert {name: info["sha256"] for name, info in card["files"].items()} == {
        name: sums[name] for name in RELEASE_ASSETS if name.endswith(".txt")
    }
    assert exclusion["corpus_sha256"] == {name: info["sha256"] for name, info in card["files"].items()}
    assert card["source"]["commit"] == exclusion["pby_dump_commit"] == PBY_DUMP_COMMIT
    assert card["corpus_version"] == "v3"
    assert card["parameters"]["max_lines_per_work"] is None
    assert card["inputs"]["fit_check"]["ran"] is True
    assert card["inputs"]["fit_check"]["hocrsyngen_commit"] == "88c61af4c12cc4a462fc1f57a1c4027b3459366d"
    assert card["parameters"]["content_screen"] == {"terms": 0, "source": None}
    assert card["inputs"]["eval_reservations"], "v3 was built with eval's reservations"
    assert card["pipeline"]["source_lines_split:verse_break_mark"] > 0


def test_only_works_with_lines_are_in_htext_cc0():
    rows, card = _rights(), _card()
    with_lines = {work["pby_work_id"] for work in _exclusion()["works"]}
    assert len(rows) == card["source"]["catalogue_rows"] == 26455
    assert len(with_lines) == card["rights"]["works_in_corpus"] == card["release"]["entries_admitted"]
    for row in rows:
        assert row["htext_release"] == ("cc0" if row["pby_work_id"] in with_lines else None), row["pby_work_id"]
        if row["pby_work_id"] in with_lines:
            assert row["pd_israel"] is True


def test_the_creator_who_died_in_1970_is_not_in_htext_cc0():
    rows = {row["pby_work_id"]: row for row in _rights()}
    works = {
        work_id
        for work_id, row in rows.items()
        if any(creator["name"] == CREATOR_IN_TERM for creator in (*row["authors"], *row["translators"]))
    }
    assert works == CREATOR_IN_TERM_WORKS
    for work_id in works:
        row = rows[work_id]
        assert row["pd_israel"] is False and row["pd_israel_basis"] == "creator_in_term"
        assert row["htext_release"] is None
    assert not works & {work["pby_work_id"] for work in _exclusion()["works"]}
    listed = {row["name"]: row for row in _card()["rights"]["creators_in_term"]}
    assert listed[CREATOR_IN_TERM]["death_year"] == 1970
    assert listed[CREATOR_IN_TERM]["works"] == 7 and listed[CREATOR_IN_TERM]["works_in_corpus"] == 0
    assert all(row["works_in_corpus"] == 0 for row in listed.values())


V2 = V3.parent / "v2"
RESERVATIONS_V4_SHA256 = "c8842a90f442c8b8ab5a1951018084776e68164e792fa8e7156834cf0c263a36"
# The P-hist eval hold-out v1 and its top-up, both new in reservations v4
# after v2 was built, hold out 15 works that have lines in v2.
WORKS_DROPPED_SINCE_V2 = 15


def _works_with_lines(version: Path) -> set[int]:
    exclusion = json.loads((version / "pby_excluded_works.v1.json").read_text(encoding="utf-8"))
    return {work["pby_work_id"] for work in exclusion["works"]}


def test_built_with_eval_reservations_v4():
    card = _card()
    reservations = card["inputs"]["eval_reservations"]
    assert {row["schema"] for row in reservations} == {"heocr_eval_reservations.v4"}
    assert {row["sha256"] for row in reservations} == {RESERVATIONS_V4_SHA256}
    assert sum(row["units"].get("pby", 0) for row in reservations) == 31
    assert card["pipeline"]["works_skipped:eval_reserved"] == 31


def test_v3_drops_the_newly_reserved_works_and_nothing_else():
    v2, v3 = _works_with_lines(V2), _works_with_lines(V3)
    assert v3 <= v2
    dropped = v2 - v3
    assert len(dropped) == WORKS_DROPPED_SINCE_V2
    rows = {row["pby_work_id"]: row for row in _rights()}
    for work_id in dropped:
        assert rows[work_id]["pd_israel"] is True, work_id
        assert rows[work_id]["htext_release"] is None, work_id


def test_il_us_files_are_unchanged_from_v2():
    sums = _sums()
    v2 = {
        name: digest
        for digest, name in (row.split("  ") for row in (V2 / "SHA256SUMS").read_text(encoding="utf-8").splitlines())
    }
    for subset in ("plain", "niqqud"):
        assert sums[f"pby_lines_il_us_{subset}_v3.txt"] == v2[f"pby_lines_il_us_{subset}_v2.txt"]

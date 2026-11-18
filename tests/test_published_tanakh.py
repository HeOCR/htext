"""Consistency checks on the committed tanakh v1 build in data/tanakh/v1/.

The two corpus files and the line index are assets of the ``tanakh-v1``
release, not in git; SHA256SUMS and the card pin their sha256s.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from htext import tanakh
from htext.release import lexicon_eligible

V1 = Path(__file__).resolve().parents[1] / "data" / "tanakh" / "v1"
IN_GIT = {"CORPUS_CARD.md", "corpus_card.json", "tanakh_rights_index.v1.jsonl.gz"}
RELEASE_ASSETS = {"tanakh_lines_niqqud_v1.txt", "tanakh_lines_plain_v1.txt", "tanakh_line_index.v1.jsonl.gz"}


def _sums() -> dict[str, str]:
    rows = (V1 / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    return {name: digest for digest, name in (row.split("  ") for row in rows)}


def _card() -> dict:
    return json.loads((V1 / "corpus_card.json").read_text(encoding="utf-8"))


def _rights() -> list[dict]:
    raw = gzip.decompress((V1 / "tanakh_rights_index.v1.jsonl.gz").read_bytes()).decode("utf-8")
    return [json.loads(line) for line in raw.splitlines()]


def test_sha256sums_cover_git_files_and_release_assets():
    sums = _sums()
    assert set(sums) == IN_GIT | RELEASE_ASSETS
    assert {path.name for path in V1.iterdir()} == IN_GIT | {"SHA256SUMS"}
    for name in IN_GIT:
        assert hashlib.sha256((V1 / name).read_bytes()).hexdigest() == sums[name], name


def test_card_pins_the_source_and_the_corpus_files():
    sums, card = _sums(), _card()
    assert {name: info["sha256"] for name, info in card["files"].items()} == {name: sums[name] for name in RELEASE_ASSETS if name.endswith(".txt")}
    assert card["source"]["repository"] == tanakh.WLC_REPOSITORY and card["source"]["commit"] == tanakh.WLC_COMMIT
    assert card["source"]["wlc_versions"] == ["4.20"] and "not UXLC" in card["source"]["edition"]
    assert [row["text"] for row in card["source"]["public_domain_statements"]] == [row["text"] for row in tanakh.PD_STATEMENTS]
    assert any("CLEAN" in note for note in card["notes"])
    assert card["corpus_version"] == "v1"
    assert card["inputs"]["fit_check"]["ran"] is True
    assert card["inputs"]["fit_check"]["hocrsyngen_commit"] == "88c61af4c12cc4a462fc1f57a1c4027b3459366d"
    # Built with eval's reservations v3, which carries the P-hist eval hold-out.
    assert any(row["schema"] == "heocr_eval_reservations.v3" for row in card["inputs"]["eval_reservations"])
    assert any(row["set"].startswith("P-hist eval hold-out") for row in card["inputs"]["eval_reservations"])
    for info in card["files"].values():
        assert all(info["length_profile_passes"].values()), info


def test_every_book_is_public_domain_cc0_with_the_oshb_credit():
    rows, card = _rights(), _card()
    assert [row["book"] for row in rows] == [book for book, _ in tanakh.BOOKS]
    assert card["books"] == {"total": 39, "with_lines": 39, "skipped": {}, "verses": 23213}
    for row in rows:
        assert row["source_licence"] == "Public Domain" and row["htext_release"] == "cc0"
        assert row["pd_israel"] is True and row["pd_us"] is True
        assert row["credit"] == card["credit"] == tanakh.CREDIT.as_dict()
        assert row["text_quality"] == "transcription" and lexicon_eligible(row)
        assert row["file"]["file"] == f"wlc/{row['book']}.xml" and len(row["file"]["sha256"]) == 64

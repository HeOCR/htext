"""Consistency checks on the committed knesset-laws v1 build in data/knesset_laws/v1/.

The corpus file and the line index were assets of the ``knesset-laws-v1``
release, never in git; SHA256SUMS and the card pin their sha256s. They were
withdrawn on 2026-11-20 (overlap with HeOCR evaluation text) and HeOCR keeps a
private backup; these files stay as the record of what was published. The eye-check
verdicts (the fresh sample the card reports, and the build-1 tuning sample the
rules were tuned on) are in ``eye_check/``.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from htext.knesset.laws import eye_check_summary
from htext.release import S6_LABEL, lexicon_eligible

DATA = Path(__file__).resolve().parents[1] / "data" / "knesset_laws"
V1 = DATA / "v1"
EYE = V1 / "eye_check"
IN_GIT = {
    "CORPUS_CARD.md",
    "corpus_card.json",
    "knesset_laws_excluded.v1.json",
    "knesset_laws_rights_index.v1.jsonl.gz",
    "knesset_laws_eye_check_sample.v1.jsonl",
}
RELEASE_ASSETS = {"knesset_laws_lines_plain_v1.txt", "knesset_laws_line_index.v1.jsonl.gz"}
EYE_FILES = {"eye_check_build4.json", "eye_sample_build1.jsonl", "eye_check_build1_tuning.json"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sums() -> dict[str, str]:
    rows = (V1 / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    return {name: digest for digest, name in (row.split("  ") for row in rows)}


def _card() -> dict:
    return json.loads((V1 / "corpus_card.json").read_text(encoding="utf-8"))


def _rights() -> list[dict]:
    raw = gzip.decompress((V1 / "knesset_laws_rights_index.v1.jsonl.gz").read_bytes()).decode("utf-8")
    return [json.loads(line) for line in raw.splitlines()]


def _sample_rows(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return [row for row in rows if "sha256" in row]


def test_sha256sums_cover_git_files_and_release_assets():
    sums = _sums()
    assert set(sums) == IN_GIT | RELEASE_ASSETS
    assert {path.name for path in V1.iterdir()} == IN_GIT | {"SHA256SUMS", "eye_check", "KNOWN_ISSUES.md"}
    for name in IN_GIT:
        assert _sha(V1 / name) == sums[name], name


def test_card_pins_the_corpus_the_manifest_and_the_exclusion_list():
    sums, card = _sums(), _card()
    exclusion = json.loads((V1 / "knesset_laws_excluded.v1.json").read_text(encoding="utf-8"))
    assert {name: info["sha256"] for name, info in card["files"].items()} == {"knesset_laws_lines_plain_v1.txt": sums["knesset_laws_lines_plain_v1.txt"]}
    assert exclusion["corpus_sha256"] == {name: info["sha256"] for name, info in card["files"].items()}
    assert card["source"]["fetch_manifest"]["sha256"] == _sha(DATA / "sources.v1.json")
    assert card["corpus_version"] == "v1"
    assert card["inputs"]["eval_reservations"], "v1 was built with eval's reservations"
    assert card["inputs"]["fit_check"]["ran"] is True
    assert card["laws"]["skipped"]["eval_reserved"] > 0
    assert all(info["length_profile_passes"] and all(info["length_profile_passes"].values()) for info in card["files"].values())
    assert len(exclusion["laws"]) == card["laws"]["with_lines"] == card["release"]["entries_admitted"]


def test_every_law_is_s6_cc0_ocr_layer_and_only_laws_with_lines_are_released():
    rows, card = _rights(), _card()
    with_lines = {law["bill_id"] for law in json.loads((V1 / "knesset_laws_excluded.v1.json").read_text(encoding="utf-8"))["laws"]}
    assert len(rows) == card["laws"]["total"]
    assert card["text_quality"] == "ocr_layer" and card["lexicon_eligible"] is False
    for row in rows:
        assert row["source_licence"] == S6_LABEL
        assert row["text_quality"] == "ocr_layer" and not lexicon_eligible(row)
        assert row["credit"] == card["credit"]
        assert row["htext_release"] == ("cc0" if row["bill_id"] in with_lines else None), row["bill_id"]
        assert (row["skipped"] is None) == (row["bill_id"] in with_lines), row["bill_id"]


def test_the_card_eye_check_is_the_committed_verdict_on_the_committed_sample():
    card, sums = _card(), _sums()
    eye = card["eye_check"]
    assert {path.name for path in EYE.iterdir()} == EYE_FILES
    verdict = EYE / "eye_check_build4.json"
    assert eye["ran"] is True and eye["file"] == {"name": verdict.name, "sha256": _sha(verdict)}
    sample = V1 / "knesset_laws_eye_check_sample.v1.jsonl"
    recomputed = eye_check_summary(verdict, sums[sample.name], _sample_rows(sample))
    assert {key: eye[key] for key in recomputed if key != "file"} == {key: value for key, value in recomputed.items() if key != "file"}
    # Lead's bar for v1: look-alike errors at most 2% of checked lines, at most 5 in 100 unverifiable.
    assert eye["errors_by_kind"].get("look_alike", 0) <= 0.02 * eye["lines_checked"]
    assert eye["unverifiable_lines"] <= 5


def test_the_fresh_sample_excludes_the_tuning_sample():
    eye = _card()["eye_check"]
    tuning = EYE / "eye_sample_build1.jsonl"
    assert eye["excluded_samples"] == [{"file": tuning.name, "sha256": _sha(tuning), "lines": len(_sample_rows(tuning))}]
    tuning_verdict = json.loads((EYE / "eye_check_build1_tuning.json").read_text(encoding="utf-8"))
    assert tuning_verdict["sample_file_sha256"] == _sha(tuning)
    fresh = {row["sha256"] for row in _sample_rows(V1 / "knesset_laws_eye_check_sample.v1.jsonl")}
    assert not fresh & {row["sha256"] for row in _sample_rows(tuning)}


def test_v1_is_marked_withdrawn_in_the_registry():
    registry = json.loads((DATA.parent / "releases.json").read_text(encoding="utf-8"))
    row = next(r for r in registry["corpora"] if r["corpus"] == "knesset-laws" and r["version"] == "v1")
    assert row["superseded_by"] == "knesset-laws-v2" and row["withdrawn"]["date"] == "2026-11-20"
    assert "Withdrawn 2026-11-20" in (V1 / "KNOWN_ISSUES.md").read_text(encoding="utf-8")


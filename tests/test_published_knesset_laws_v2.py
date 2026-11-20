"""Consistency checks on the committed knesset-laws v2 build in data/knesset_laws/v2/.

v2 is v1 minus the lines and laws that overlap HeOCR's evaluation text (the drop list's sha256 is on the card; the
list itself stays private, since it points at public lines that overlap private sets). The corpus file and the line
index are assets of the ``knesset-laws-v2`` release. The eye check is v1's, inherited for the sample lines still in v2.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from htext.release import S6_LABEL, lexicon_eligible

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "knesset_laws"
V1, V2 = DATA / "v1", DATA / "v2"
IN_GIT = {
    "CORPUS_CARD.md",
    "corpus_card.json",
    "knesset_laws_excluded.v1.json",
    "knesset_laws_rights_index.v1.jsonl.gz",
    "knesset_laws_eye_check_sample.v1.jsonl",
}
RELEASE_ASSETS = {"knesset_laws_lines_plain_v2.txt", "knesset_laws_line_index.v1.jsonl.gz"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sums(folder: Path) -> dict[str, str]:
    rows = (folder / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    return {name: digest for digest, name in (row.split("  ") for row in rows)}


def _card() -> dict:
    return json.loads((V2 / "corpus_card.json").read_text(encoding="utf-8"))


def _rights() -> list[dict]:
    return [json.loads(line) for line in gzip.decompress((V2 / "knesset_laws_rights_index.v1.jsonl.gz").read_bytes()).decode("utf-8").splitlines()]


def test_sha256sums_cover_git_files_and_release_assets():
    sums = _sums(V2)
    assert set(sums) == IN_GIT | RELEASE_ASSETS
    assert {path.name for path in V2.iterdir()} == IN_GIT | {"SHA256SUMS"}
    for name in IN_GIT:
        assert _sha(V2 / name) == sums[name], name


def test_v2_is_v1_minus_the_overlap_drop():
    card, v1 = _card(), json.loads((V1 / "corpus_card.json").read_text(encoding="utf-8"))
    assert card["corpus_version"] == "v2"
    drop = card["inputs"]["eval_overlap_drop"]
    assert drop["derived_from"]["sha256"] == _sums(V1)["knesset_laws_lines_plain_v1.txt"]
    assert drop["run_threshold"] == 5 and drop["units"] == card["laws"]["skipped"]["eval_overlap"] > 0
    assert isinstance(drop["targets"], int), "the card gives a count of evaluation targets, never their names"
    assert card["source"] == v1["source"]
    assert card["laws"]["with_lines"] + card["laws"]["skipped"]["eval_overlap"] <= v1["laws"]["with_lines"]
    v2_lines = card["files"]["knesset_laws_lines_plain_v2.txt"]["lines"]
    assert v2_lines < v1["files"]["knesset_laws_lines_plain_v1.txt"]["lines"]
    assert drop["segments_dropped"] > 0 and drop["segments_dropped_with_laws"] > 0


def test_every_law_is_s6_cc0_ocr_layer_and_only_laws_with_lines_are_released():
    rows, card = _rights(), _card()
    with_lines = {law["bill_id"] for law in json.loads((V2 / "knesset_laws_excluded.v1.json").read_text(encoding="utf-8"))["laws"]}
    assert len(rows) == card["laws"]["total"] and len(with_lines) == card["laws"]["with_lines"] == card["release"]["entries_admitted"]
    for row in rows:
        assert row["source_licence"] == S6_LABEL and row["text_quality"] == "ocr_layer" and not lexicon_eligible(row)
        assert row["htext_release"] == ("cc0" if row["bill_id"] in with_lines else None), row["bill_id"]


def test_the_eye_check_is_v1s_verdict_on_the_lines_still_in_v2():
    eye = _card()["eye_check"]
    sample, verdict = V1 / "knesset_laws_eye_check_sample.v1.jsonl", V1 / "eye_check" / "eye_check_build4.json"
    assert eye["inherited"]["sample_file"]["sha256"] == _sha(sample) == _sums(V1)[sample.name]
    assert eye["file"] == {"name": verdict.name, "sha256": _sha(verdict)}
    kept = eye["inherited"]["lines_still_in_build"]
    # Lead's bar for inheriting (2026-11-20): at least about 90 of the 100 sample lines remain.
    assert kept >= 90 and eye["lines_checked"] + eye["unverifiable_lines"] == kept


def test_no_evaluation_target_names_in_the_overlap_record():
    card = _card()
    overlap = [line for line in (V2 / "CORPUS_CARD.md").read_text(encoding="utf-8").splitlines() if "Overlap with evaluation text" in line]
    text = json.dumps(card["inputs"]["eval_overlap_drop"]) + "".join(overlap)
    assert len(overlap) == 1
    for name in ("tenders", "vendor_midcentury", "midcentury_test_pages", "pmod_", "dbench", "nq1", "ps_v1", "line_verify", "wave1", "olb_", "rseries"):
        assert name not in text, name

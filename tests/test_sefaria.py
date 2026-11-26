"""Offline tests for the sefaria v3 builder. All text is invented; nothing is fetched."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from htext import sefaria as s

BODY = "זה הוא משפט ראשון בקטע שנכתב לצורך הבדיקה בלבד והוא נמשך עוד מעט עד סופו של העניין הבדוי"


def test_clean_segment_drops_footnotes_with_their_content_and_markup():
    raw = 'פתיחה <b>מודגשת</b><sup class="footnote-marker">1</sup><i class="footnote">הערה <i>פנימית</i> שאינה נכנסת</i> וסוף&nbsp;הקטע'
    out = s.clean_segment(raw)
    assert "הערה" not in out and "פנימית" not in out and "1" not in out
    assert out == "פתיחה מודגשת וסוף הקטע"


def test_segments_walk_lists_and_complex_dicts_in_order():
    text = {"Introduction": ["א", ""], "": [["ב", "ג"], ["ד"]]}
    assert list(s.segments(text)) == [("Introduction.1", "א"), ("_.1.1", "ב"), ("_.1.2", "ג"), ("_.2.1", "ד")]


def _version_file(inputs: Path, title: str, vt: str, licence: str, text) -> str:
    raw = json.dumps({"title": title, "versionTitle": vt, "license": licence, "language": "he", "text": text}, ensure_ascii=False).encode()
    sha = hashlib.sha256(raw).hexdigest()
    (inputs / f"{sha}.json").write_bytes(raw)
    return sha


def _setup(tmp_path: Path, lane: str = "cc0", bad_sha: bool = False) -> s.SefariaConfig:
    inputs = tmp_path / "in"
    inputs.mkdir()
    a = _version_file(inputs, "Invented Work", "Invented Edition, 1850", "Public Domain", [[BODY, BODY + " שוב"]])
    b = _version_file(inputs, "Invented Commentary", "Invented CC-BY", "CC-BY", [BODY + " פירוש"])
    c = _version_file(inputs, "Invented Tractate", "Invented Edition", "CC0", [["תנן " + BODY]])
    works = [
        {"title": "Invented Work", "categories": ["Halakhah"], "tags": [], "versions": [
            {"versionTitle": "Invented Edition, 1850", "license": "Public Domain", "file": f"{a}.json", "sha256": "0" * 64 if bad_sha else a,
             "rights": {"pass": True, "basis": "all_authors:invented:d1850"}}]},
        {"title": "Invented Commentary", "categories": ["Halakhah"], "tags": [], "versions": [
            {"versionTitle": "Invented CC-BY", "license": "CC-BY", "file": f"{b}.json", "sha256": b, "rights": {"pass": True, "basis": "licence_grant:CC-BY"}}]},
        {"title": "Invented Tractate", "categories": ["Talmud", "Bavli"], "aramaic_heavy": True, "tags": ["family_shared_with_wikisource"],
         "versions": [{"versionTitle": "Invented Edition", "license": "CC0", "file": f"{c}.json", "sha256": c, "rights": {"pass": True, "basis": "licence_grant:CC0"}}]},
        {"title": "Invented Modern", "categories": ["Halakhah"], "tags": [], "versions": [
            {"versionTitle": "Modern", "license": "Public Domain", "file": "missing.json", "sha256": "1" * 64, "rights": {"pass": False, "basis": "author_death_unknown:x"}}]},
    ]
    src = {"schema": s.SOURCES_SCHEMA, "export": {"repo": "Sefaria/Sefaria-Export", "commit": "0" * 40}, "works": works}
    (tmp_path / "sources.json").write_text(json.dumps(src, ensure_ascii=False), encoding="utf-8")
    reserved = {"schema": "heocr_eval_reservations.v1", "owner": "eval", "as_of": "2026-11-26",
                "reservations": [{"set": "s", "sefaria_works": ["Invented Work"]}], "supersedes": {"file": "v0.json", "sha256": "0"}}
    (tmp_path / "reserved.json").write_text(json.dumps(reserved), encoding="utf-8")
    return s.SefariaConfig(sources=tmp_path / "sources.json", inputs=inputs, output=tmp_path / "out", lane=lane,
                           length_profile=[20, 25, 30, 35, 40], length_profile_source="test", reservations=[tmp_path / "reserved.json"])


def _index(out: Path) -> list[list[str]]:
    with gzip.open(out / s.LINE_INDEX_FILE, "rt", encoding="utf-8") as f:
        return [l.rstrip("\n").split("\t") for l in f][1:]


def test_cc0_build_keeps_lane_routes_aramaic_and_tags_reserved_work(tmp_path):
    card = s.build(_setup(tmp_path))
    files = card["files"]
    he = files[s.corpus_file_name("plain", "he", "cc0")]["lines"]
    arc = files[s.corpus_file_name("plain", "arc", "cc0")]["lines"]
    assert he > 0 and arc > 0
    rows = _index(tmp_path / "out")
    assert {r[2] for r in rows} == {"Invented Work", "Invented Tractate"}  # the CC-BY work is not in the cc0 lane
    assert all("eval_reserved_work" in r[5] for r in rows if r[2] == "Invented Work")  # a tag, not a drop
    assert all(r[1] == "arc" and "family_shared_with_wikisource" in r[5] for r in rows if r[2] == "Invented Tractate")
    assert [o["reason"] for o in card["out"]] == ["author_death_unknown:x"]
    assert card["htext_release"] == "cc0"


def test_by_lane_takes_only_the_cc_by_version(tmp_path):
    card = s.build(_setup(tmp_path, lane="by"))
    assert {r[2] for r in _index(tmp_path / "out")} == {"Invented Commentary"} and card["htext_release"] == "by"


def test_a_changed_file_is_refused(tmp_path):
    with pytest.raises(ValueError, match="sha256"):
        s.build(_setup(tmp_path, bad_sha=True))


def test_duplicates_and_other_release_lines_are_removed(tmp_path):
    config = _setup(tmp_path)
    first = s.build(config)
    name = s.corpus_file_name("plain", "he", "cc0")
    lines = (tmp_path / "out" / name).read_text(encoding="utf-8").splitlines()
    other = tmp_path / "other.txt"
    other.write_text(lines[0] + "\n", encoding="utf-8")
    config.output, config.dedup_against = tmp_path / "out2", [other]
    second = s.build(config)
    assert second["files"][name]["lines"] == first["files"][name]["lines"] - 1
    assert second["pipeline"]["segments_dropped:in_other_htext_release"] >= 1

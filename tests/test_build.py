"""End-to-end build on the synthetic mini dump (no hocrsyngen needed)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from htext.hebrew import NIQQUD, PLAIN_CHARSET
from htext.pby.build import BuildConfig, build, corpus_file_name
from tests.conftest import PROTECTED_LINE

PROFILE = list(range(12, 48))


def _config(mini_dump, mini_creators, mini_leakage, output, **overrides):
    values = dict(
        dump=mini_dump,
        creators=mini_creators,
        leakage_fixtures=[mini_leakage],
        output=output,
        length_profile=PROFILE,
        length_profile_source="test profile",
    )
    values.update(overrides)
    return BuildConfig(**values)


def _lines(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    assert text == "" or (text.endswith("\n") and not text.endswith("\n\n"))
    return text.split("\n")[:-1]


@pytest.fixture
def built(mini_dump, mini_creators, mini_leakage, tmp_path):
    output = tmp_path / "out"
    card = build(_config(mini_dump, mini_creators, mini_leakage, output))
    return output, card


def test_outputs_exist_and_checksums_match(built):
    output, _card = built
    expected = {
        *(corpus_file_name(variant, subset) for variant in ("il", "il_us") for subset in ("plain", "niqqud")),
        "pby_line_index.v1.jsonl",
        "pby_rights_index.v1.jsonl",
        "pby_excluded_works.v1.json",
        "corpus_card.json",
        "CORPUS_CARD.md",
        "SHA256SUMS",
    }
    assert {path.name for path in output.iterdir()} == expected
    for row in (output / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = row.split("  ")
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest


def test_build_is_deterministic(mini_dump, mini_creators, mini_leakage, tmp_path):
    first = tmp_path / "a"
    second = tmp_path / "b"
    build(_config(mini_dump, mini_creators, mini_leakage, first))
    build(_config(mini_dump, mini_creators, mini_leakage, second))
    assert (first / "SHA256SUMS").read_text() == (second / "SHA256SUMS").read_text()


def test_only_pd_israel_allowlisted_works_contribute(built):
    output, card = built
    index = [json.loads(row) for row in (output / "pby_line_index.v1.jsonl").read_text(encoding="utf-8").splitlines()]
    # 1 (prose, PD), 2 (poetry, PD and pre-1931 edition), 8 (poetry, PD).
    # 3: translator in term; 4: anonymous; 5: no QID; 6: reference genre;
    # 7: misaligned files.
    assert {row["pby_work_id"] for row in index} == {1, 2, 8}
    assert card["pipeline"]["works_skipped:genre"] == 1
    assert card["pipeline"]["works_skipped:not_pd_israel"] == 3
    assert card["pipeline"]["works_dropped:misaligned"] == 1


def test_il_us_is_the_pre_1931_subset(built):
    output, _card = built
    il = set(_lines(output / corpus_file_name("il", "niqqud"))) | set(_lines(output / corpus_file_name("il", "plain")))
    il_us = set(_lines(output / corpus_file_name("il_us", "niqqud"))) | set(_lines(output / corpus_file_name("il_us", "plain")))
    assert il_us and il_us < il
    rights = {row["pby_work_id"]: row for row in map(json.loads, (output / "pby_rights_index.v1.jsonl").read_text(encoding="utf-8").splitlines())}
    assert rights[2]["source_edition_year"] == 1912 and rights[2]["pd_us"] is True
    assert rights[1]["pd_us"] == "unknown"


def test_rights_index_covers_the_whole_catalogue(built):
    output, _card = built
    rows = [json.loads(row) for row in (output / "pby_rights_index.v1.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [row["pby_work_id"] for row in rows] == list(range(1, 9))
    by_id = {row["pby_work_id"]: row for row in rows}
    assert by_id[3]["pd_israel_basis"] == "creator_in_term"
    assert by_id[4]["pd_israel_basis"] == "anonymous_unresolved"
    assert by_id[5]["pd_israel_basis"] == "creator_death_year_unknown"
    assert by_id[1]["pd_israel_basis"] == "all_creators_died_by:1955"


def test_footnotes_footer_title_and_rejected_lines_are_gone(built):
    output, _card = built
    text = "\n".join(_lines(output / corpus_file_name("il", "plain")) + _lines(output / corpus_file_name("il", "niqqud")))
    for absent in ("הערה ארוכה", "ממשיכה", "פרויקט", "Latin", "ישות", "בוקר\n", "שִׁיר", "︎", "↩"):
        assert absent not in text
    # The footnote reference digit is removed; the sentence stays.
    assert "העתיקה ועל" in text.replace("\n", " ")


def test_niqqud_and_plain_subsets(built):
    output, _card = built
    niqqud = _lines(output / corpus_file_name("il", "niqqud"))
    plain = _lines(output / corpus_file_name("il", "plain"))
    assert niqqud and all(any(char in NIQQUD for char in line) for line in niqqud)
    assert all(char in PLAIN_CHARSET for line in plain for char in line)
    # The cantillated verse is in the plain subset only.
    assert "המים זורמים בנחל" in plain
    assert all(len(line) <= 55 for line in plain)


def test_protected_text_is_dropped(built):
    output, card = built
    text = (output / corpus_file_name("il", "plain")).read_text(encoding="utf-8")
    assert PROTECTED_LINE not in text
    assert card["pipeline"]["segments_dropped:leak_line"] == 1


def test_exclusion_list_and_card(built):
    output, card = built
    exclusion = json.loads((output / "pby_excluded_works.v1.json").read_text(encoding="utf-8"))
    assert [work["pby_work_id"] for work in exclusion["works"]] == [1, 2, 8]
    assert exclusion["corpus_sha256"] == {name: info["sha256"] for name, info in card["files"].items()}
    assert card["attribution"].startswith("Text from Project Ben-Yehuda")
    assert card["licence"]["outputs"] == "CC0-1.0"
    assert card["inputs"]["fit_check"] == {"ran": False}
    markdown = (output / "CORPUS_CARD.md").read_text(encoding="utf-8")
    assert "Project Ben-Yehuda volunteers" in markdown and "test/protected" in markdown


def test_fit_failures_and_cap_drop_lines(mini_dump, mini_creators, mini_leakage, tmp_path):
    card = build(
        _config(
            mini_dump,
            mini_creators,
            mini_leakage,
            tmp_path / "fit",
            fit=lambda line: "printed_letter:word_too_wide" if "הגשר" in line else None,
            fit_provenance={"ran": True},
            max_lines_per_work=2,
        )
    )
    text = (tmp_path / "fit" / corpus_file_name("il", "plain")).read_text(encoding="utf-8")
    assert "הגשר" not in text
    assert card["pipeline"]["segments_dropped:per_work_cap"] > 0
    index = [json.loads(row) for row in (tmp_path / "fit" / "pby_line_index.v1.jsonl").read_text(encoding="utf-8").splitlines()]
    assert max(sum(row["pby_work_id"] == work for row in index) for work in (1, 2, 8)) <= 2

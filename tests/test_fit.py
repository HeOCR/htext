"""The no-loss wrap check against the real generator code.

These tests need ``hocrsyngen`` and Pillow with libraqm (the ``fit`` CI job
installs both). They skip otherwise.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

hocrsyngen = pytest.importorskip("hocrsyngen")
features = pytest.importorskip("PIL.features")
if not features.check("raqm"):
    pytest.skip("Pillow libraqm support is required", allow_module_level=True)

from htext.fit import ARCHIVE_CARD_ROW_CAP, LEDGER_ROW_CAP, FitChecker, wrapping_bodies  # noqa: E402


@pytest.fixture(scope="module")
def checker() -> FitChecker:
    return FitChecker()


def test_region_table_matches_hocrsyngen_tests():
    source = os.environ.get("HOCRSYNGEN_SOURCE")
    if not source:
        pytest.skip("set HOCRSYNGEN_SOURCE to a hocrsyngen checkout to compare region tables")
    tests_dir = Path(source) / "tests"
    sys.path.insert(0, str(tests_dir))
    try:
        spec = importlib.util.spec_from_file_location("hocrsyngen_corpus_tests", tests_dir / "test_training_text_corpus.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(tests_dir))
    ours = [(body.template_id, body.font_file, body.size, body.width) for body in wrapping_bodies()]
    theirs = [(template_id, font, size, width) for template_id, font, size, width, _cap in module.WRAPPING_BODIES]
    assert ours == theirs
    assert ARCHIVE_CARD_ROW_CAP == module.ARCHIVE_CARD_ROW_CAP
    assert LEDGER_ROW_CAP == dict((row[0], row[4]) for row in module.WRAPPING_BODIES)["ledger"]


def test_short_line_fits(checker):
    assert checker.failure("בבוקר יצאנו לדרך") is None


def test_overwide_word_fails(checker):
    assert checker.failure("א" * 80) == "printed_letter:word_too_wide"


def test_archive_card_row_cap(checker):
    line = " ".join(["מילה"] * 16)
    assert checker.failure(line) == "archive_card:too_many_rows"


def test_glyph_check(checker):
    assert checker.has_glyph("א")
    assert not checker.has_glyph("")
    assert isinstance(checker.maqaf_allowed(), bool)

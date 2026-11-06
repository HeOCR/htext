"""Repository-level checks: licence scopes and package metadata."""

from __future__ import annotations

import tomllib
from pathlib import Path

import htext


ROOT = Path(__file__).resolve().parents[1]


def test_code_licence_is_mit() -> None:
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License")


def test_data_licence_is_cc0() -> None:
    text = (ROOT / "LICENSE-DATA").read_text(encoding="utf-8")
    assert "CC0 1.0 Universal" in text


def test_readme_states_both_licence_scopes() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "| Code |" in readme and "MIT" in readme
    assert "| Data |" in readme and "CC0-1.0" in readme


def test_readme_gives_the_linked_pby_credit() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "[Project Ben-Yehuda volunteers](https://benyehuda.org)" in readme


def test_package_version_matches_pyproject() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == htext.__version__

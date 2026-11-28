import json
import subprocess
from pathlib import Path

import pytest

from htext.public_guard import FORBIDDEN_NAME, PublicStagingError, assert_public_safe, check_public_files

ROOT = Path(__file__).resolve().parents[1]


def _w(p: Path, obj) -> Path:
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


def test_exclusion_file_by_name_is_refused(tmp_path):
    p = _w(tmp_path / "exclusions.json", {"x": 1})
    with pytest.raises(PublicStagingError):
        assert_public_safe([p], tokens=set())


def test_target_name_is_checked_too(tmp_path):
    p = _w(tmp_path / "a.json", {"x": 1})
    assert check_public_files([p], targets=["recipe/reservations_v3.json"], tokens=set())


def test_private_list_keys_are_refused_under_any_name(tmp_path):
    p = _w(tmp_path / "manifest.json", {"meta": {"release_row_ids": ["r1"]}})
    f = check_public_files([p], tokens=set())
    assert f and "keys" in f[0]


def test_private_tokens_are_found_and_not_echoed(tmp_path):
    priv = _w(tmp_path / "priv.json", {"note": "generic words here", "ia_ids": ["secretscan00abc"], "rules": [{"text": "a rule"}]})
    pub = tmp_path / "README.md"
    pub.write_text("lines from secretscan00abc page 3", encoding="utf-8")
    from htext.public_guard import private_tokens
    f = check_public_files([pub], tokens=private_tokens([priv]))
    assert f and "secretscan00abc" not in f[0]


def test_note_and_rules_text_are_not_tokens(tmp_path):
    from htext.public_guard import private_tokens
    priv = _w(tmp_path / "priv.json", {"note": "generic words here", "rules": [{"text": "a rule text"}], "sets": ["abcdef"]})
    assert private_tokens([priv]) == {"abcdef"}


def test_allow_tokens(tmp_path):
    pub = tmp_path / "manifest.json"
    pub.write_text(json.dumps({"src": "ownscan00x:pby:1"}), encoding="utf-8")
    assert check_public_files([pub], tokens={"ownscan00x"})
    assert not check_public_files([pub], tokens={"ownscan00x"}, allow_tokens={"ownscan00x"})


def test_reference_fields_pass(tmp_path):
    p = _w(tmp_path / "corpus_card.json", {"inputs": {"reservations": {"file": "r.json", "sha256": "ab"}}, "roster": "x.json"})
    assert check_public_files([p], tokens=set()) == []


def test_clean_files_pass(tmp_path):
    p = _w(tmp_path / "manifest.json", {"rows": 3, "release_row_drop": {"rows_removed": 2, "reason": "overlap"}})
    assert check_public_files([p], tokens=set()) == []


def test_cli_exit_status(tmp_path):
    bad = _w(tmp_path / "exclusions.json", {})
    r = subprocess.run(["python", "-m", "htext.public_guard", str(bad)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 1


def test_repository_data_has_no_custody_material():
    """Everything under data/ is public: no custody names and no private-list keys."""
    files = [p for p in (ROOT / "data").rglob("*") if p.is_file()]
    assert files
    findings = check_public_files(files, targets=[str(p.relative_to(ROOT)) for p in files], tokens=set())
    assert findings == [], findings


def test_existing_public_lists_are_not_custody_names():
    for n in ("pby_excluded_works.v1.json", "knesset_laws_excluded.v1.json", "exclude_pages.json"):
        assert not FORBIDDEN_NAME.search(n)


def test_composite_row_ids_match_bare_ids(tmp_path):
    from htext.public_guard import private_tokens
    priv = _w(tmp_path / "priv.json", {"release_row_ids": ["v1.1|Book_ab12/p0036/l010"]})
    pub = tmp_path / "rows.jsonl"
    pub.write_text(json.dumps({"part": "v1.1", "id": "Book_ab12/p0036/l010"}) + "\n", encoding="utf-8")
    assert check_public_files([pub], targets=["x.jsonl"], tokens=private_tokens([priv]))


def test_drop_id_file_names_are_refused():
    assert FORBIDDEN_NAME.search("release-drop-ids.jsonl")

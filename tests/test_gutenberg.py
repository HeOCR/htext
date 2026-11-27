"""Offline tests for the gutenberg builder. All text is invented; nothing is fetched."""

from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from htext import gutenberg as g

HEADER = "The Project Gutenberg eBook of an invented book\n\nLicence text that must never reach the corpus.\n\n"
START = "*** START OF THE PROJECT GUTENBERG EBOOK INVENTED ***\n"
END = "*** END OF THE PROJECT GUTENBERG EBOOK INVENTED ***\n"
FOOTER = "\nMore licence text after the end marker.\n"
BODY = "\n".join([
    "",
    "                              ספר בדוי לבדיקה",
    "                                 מאת",
    "                     INVENTED IMPRINT, 1850.",
    "",
    "זה הוא משפט ראשון בפסקה שנכתבה לצורך הבדיקה בלבד והוא נמשך",
    "אל השורה הבאה בלי *הדגשה* מיוחדת[1] וממשיך עד סופו של העניין.",
    "",
    "[1] הערת שוליים שאינה נכנסת לקורפוס.",
    "",
    "פסקה שנייה וקצרה יותר שגם היא נכתבה לצורך הבדיקה.",
    "",
])
TEXT = HEADER + START + BODY + END + FOOTER


def test_body_keeps_only_the_text_between_the_markers():
    text = g.body(TEXT)
    assert "Licence text" not in text and "More licence" not in text and "ספר בדוי" in text
    with pytest.raises(ValueError):
        g.body("no markers here")


def test_body_stops_at_the_electronic_edition_notes():
    notes = "\n                       הערות על המהדורה אלקטרונית\n\nהטעויות דפוס הבאות תוקנו:\n\n  * ע׳ 1, ש׳ 2: שגיאה ← תיקון\n"
    text = g.body(HEADER + START + BODY + notes + END + FOOTER)
    assert "פסקה שנייה" in text and "הטעויות דפוס" not in text and "תיקון" not in text


def test_paragraphs_drop_footnotes_markup_and_latin_and_split_headings():
    stats = Counter()
    paras = g.paragraphs(TEXT, stats)
    texts = [p.text for p in paras]
    assert ("ספר בדוי לבדיקה", "heading") in [(p.text, p.kind) for p in paras]
    assert not any("INVENTED" in t or "הערת שוליים" in t for t in texts)
    body = next(p.text for p in paras if p.kind == "body")
    assert "*" not in body and "[1]" not in body and "בלי הדגשה מיוחדת וממשיך" in body
    assert stats["blocks_dropped:footnote"] == 1


@pytest.mark.parametrize(("years", "ok"), [([1851], True), ([1905, 1955], True), ([1952, None], False), ([1956], False), ([], False)])
def test_every_contributor_must_have_died_by_the_cutoff(years, ok):
    work = {"contributors": [{"death_year": y} for y in years]}
    assert g.eligible(work, 2026)[0] is ok


def _setup(tmp_path: Path, sha: str | None = None) -> g.GutenbergConfig:
    inputs = tmp_path / "in"
    inputs.mkdir()
    (inputs / "pg101.txt").write_text(TEXT, encoding="utf-8")
    digest = sha or hashlib.sha256((inputs / "pg101.txt").read_bytes()).hexdigest()
    sources = {"schema": g.SOURCES_SCHEMA, "catalogue": {"file": "pg_catalog.csv.gz", "sha256": "0" * 64},
               "works": [
                   {"pg": 101, "title": "ספר בדוי", "contributors": [{"name": "Invented, A.", "death_year": 1850}],
                    "mirror_url": "https://example.invalid/101.txt", "sha256": digest},
                   {"pg": 102, "title": "Translated", "contributors": [{"death_year": 1900}, {"death_year": None}]},
                   {"pg": 103, "title": "Audio", "contributors": [], "exclude": "audio_only"},
               ]}
    (tmp_path / "sources.json").write_text(json.dumps(sources, ensure_ascii=False), encoding="utf-8")
    reserved = {"schema": "heocr_eval_reservations.v1", "owner": "eval", "as_of": "2026-11-25",
                "reservations": [{"set": "s", "unit_ids": ["gutenberg:999"]}], "supersedes": {"file": "v0.json", "sha256": "0"}}
    (tmp_path / "reserved.json").write_text(json.dumps(reserved), encoding="utf-8")
    return g.GutenbergConfig(sources=tmp_path / "sources.json", inputs=inputs, output=tmp_path / "out",
                             length_profile=[20, 25, 30, 35, 40], length_profile_source="test", reservations=[tmp_path / "reserved.json"])


def test_build_writes_lines_rights_and_the_out_list(tmp_path):
    card = g.build(_setup(tmp_path))
    lines = (tmp_path / "out" / g.corpus_file_name("plain")).read_text(encoding="utf-8").splitlines()
    assert lines and not any("Licence" in l or "הערת שוליים" in l for l in lines)
    assert {o["pg"]: o["reason"] for o in card["out"]} == {102: "contributor_death_unknown", 103: "audio_only"}
    assert card["htext_release"] == "cc0" and card["source_tag"] == "gutenberg"
    with gzip.open(tmp_path / "out" / g.RIGHTS_INDEX_FILE, "rt", encoding="utf-8") as f:
        rights = [json.loads(l) for l in f]
    assert [r["pg"] for r in rights] == [101] and rights[0]["pd_israel_basis"] == "all_contributors_died_by:1955"
    assert rights[0]["credit"]["text"] == "Project Gutenberg"


def test_a_changed_file_is_refused(tmp_path):
    with pytest.raises(ValueError, match="sha256"):
        g.build(_setup(tmp_path, sha="0" * 64))


def test_dedup_against_another_corpus(tmp_path):
    config = _setup(tmp_path)
    first = g.build(config)
    lines = (tmp_path / "out" / g.corpus_file_name("plain")).read_text(encoding="utf-8").splitlines()
    other = tmp_path / "other.txt"
    other.write_text(lines[0] + "\n", encoding="utf-8")
    config.output = tmp_path / "out2"
    config.dedup_against = [other]
    second = g.build(config)
    assert second["files"][g.corpus_file_name("plain")]["lines"] == first["files"][g.corpus_file_name("plain")]["lines"] - 1
    assert second["pipeline"]["segments_dropped:in_other_corpus"] == 1

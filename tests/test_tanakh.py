"""Offline tests for the tanakh builder.

The OSIS files below are invented for these tests, in the shape of OSHB's
``wlc/*.xml``: words with lemma and morphology attributes and ``/`` morpheme
dividers, maqaf, sof pasuq, paseq, section markers, a ketiv with its qere in a
note, and cantillation marks. None of the words is a real verse.
"""

from __future__ import annotations

import gzip
from collections import Counter
import json
from pathlib import Path

import pytest

from htext import cli, tanakh
from htext.leakage import NORMALIZATION, corpus_hashes

# Marks used below: U+0596 tipeha and U+0591 etnahta (cantillation), U+05BD meteg, and S10b vowels.
TIPEHA, ETNAHTA, METEG = "֖", "֑", "ֽ"
PATAH, QAMATS, SHEVA, HIRIQ = "ַ", "ָ", "ְ", "ִ"

LEMMA = "9999 z"  # an attribute value that must never reach the corpus
NS = "http://www.bibletechnologies.net/2003/OSIS/namespace"


def _verse(book: str, chapter: int, number: int, body: str) -> str:
    return f'<verse osisID="{book}.{chapter}.{number}">{body}</verse>'


def _word(text: str, **attrs: str) -> str:
    extra = "".join(f' {key}="{value}"' for key, value in attrs.items())
    return f'<w lemma="{LEMMA}" morph="HNcmsa" id="x1"{extra}>{text}</w>'


def _book_xml(book: str, verses: list[str]) -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<osis xmlns="{NS}"><osisText xml:lang="he">'
        "<header><revisionDesc><date>2016.03.03</date><p>Updated to WLC version 4.20.</p></revisionDesc></header>"
        f'<div type="book" osisID="{book}"><chapter osisID="{book}.1">' + "".join(verses) + "</chapter></div></osisText></osis>\n"
    )


def _first_verse(book: str) -> str:
    # "ו/דבר" with cantillation and meteg, maqaf to "של", paseq, a ketiv with a qere note, sof pasuq and a pe.
    return _verse(
        book,
        1,
        1,
        _word(f"וְ{METEG}/דָ{TIPEHA}בָר")
        + '<seg type="x-maqqef">־</seg>'
        + _word(f"שֶׁל{ETNAHTA}")
        + '<seg type="x-paseq">׀</seg>'
        + _word("גַּנִּים")
        + _word("כתיב", type="x-ketiv")
        + '<note type="variant"><catchWord>כתיב</catchWord><rdg type="x-qere">' + _word("קְרִי") + "</rdg></note>"
        + "<note>An editorial note.</note>"
        + _word(f"פְּרָחִים{TIPEHA}")
        + '<seg type="x-sof-pasuq">׃</seg><seg type="x-pe">פ</seg>',
    )


def _write_wlc(root: Path, extra: dict[str, list[str]] | None = None) -> Path:
    wlc = root / "wlc"
    wlc.mkdir(parents=True)
    for book, _ in tanakh.BOOKS:
        verses = [_first_verse(book)]
        # A second verse, different in every book so that deduplication keeps it.
        letters = "".join("אבגדהוזחטיכלמנסעפצקרשת"[index % 22] for index in range(tanakh.BOOKS.index((book, _)) + 3))
        verses.append(_verse(book, 1, 2, _word(f"מִלָּה{letters}") + _word("שְׁנִיָּה") + '<seg type="x-sof-pasuq">׃</seg>'))
        verses += (extra or {}).get(book, [])
        (wlc / f"{book}.xml").write_text(_book_xml(book, verses), encoding="utf-8")
    return wlc


def _config(tmp_path: Path, **overrides) -> tanakh.TanakhConfig:
    values = {
        "wlc": _write_wlc(tmp_path / "src"),
        "leakage_fixtures": [],
        "output": tmp_path / "out",
        "length_profile": [20, 25, 30, 35, 40],
        "length_profile_source": "test",
        "allow_maqaf": True,
    }
    values.update(overrides)
    return tanakh.TanakhConfig(**values)


def _jsonl_gz(path: Path) -> list[dict]:
    return [json.loads(line) for line in gzip.decompress(path.read_bytes()).decode("utf-8").splitlines()]


def test_read_book_keeps_words_and_drops_oshb_layers_notes_and_marks(tmp_path):
    wlc = _write_wlc(tmp_path)
    stats = Counter()
    verses, version = tanakh.read_book(wlc / "Gen.xml", stats)
    assert version == "4.20"
    first = verses[0]
    assert first.ref == "Gen.1.1"
    joined = " ".join(first.words)
    assert "/" not in joined and LEMMA not in joined
    assert len(first.words) == 4  # maqaf joins two words; the qere in the note is not read
    assert "־" in first.words[0] and first.words[2] == "כתיב"
    assert "קרי" not in tanakh.strip_marks(joined)
    assert not any(mark in joined for mark in "׃׀")
    assert stats["notes_skipped:variant"] == 1 and stats["notes_skipped:editorial"] == 1
    assert stats["marks_removed:pe"] == 1 and stats["words:ketiv"] == 1


def test_pointed_form_keeps_vowels_and_drops_cantillation_and_meteg():
    word = f"וְ{METEG}דָ{TIPEHA}בָר"
    assert tanakh.pointed_form(word) == "וְדָבָר"
    assert tanakh.strip_marks(word) == "ודבר"


def test_build_writes_both_forms_rights_and_card(tmp_path):
    config = _config(tmp_path)
    card = tanakh.build(config)
    niqqud = (config.output / "tanakh_lines_niqqud_v1.txt").read_text(encoding="utf-8").splitlines()
    plain = (config.output / "tanakh_lines_plain_v1.txt").read_text(encoding="utf-8").splitlines()
    # The first verse repeats in every book: kept once per file.
    assert len(niqqud) == len(plain) == 1 + len(tanakh.BOOKS)
    assert [tanakh.strip_marks(line) for line in niqqud] == plain
    assert niqqud[0].startswith("וְדָבָר־שֶׁל")
    for line in niqqud + plain:
        assert "/" not in line and not any(char in tanakh.OTHER_MARKS for char in line)
    rights = _jsonl_gz(config.output / tanakh.RIGHTS_INDEX_FILE)
    assert [row["book"] for row in rights] == [book for book, _ in tanakh.BOOKS]
    assert {row["htext_release"] for row in rights} == {"cc0"}
    assert {row["source_licence"] for row in rights} == {"Public Domain"}
    assert all(row["file"]["sha256"] for row in rights)
    index = _jsonl_gz(config.output / tanakh.LINE_INDEX_FILE)
    assert {row["subset"] for row in index} == {"niqqud", "plain"} and len(index) == len(niqqud) + len(plain)
    assert card["source"]["commit"] == tanakh.WLC_COMMIT and card["source"]["wlc_versions"] == ["4.20"]
    assert "not UXLC" in card["source"]["edition"]
    assert [row["text"] for row in card["source"]["public_domain_statements"]][0] == "The text of the WLC remains in the Public Domain."
    assert any("CLEAN" in note for note in card["notes"])
    assert card["pipeline"]["segments_dropped:duplicate"] == len(tanakh.BOOKS) - 1
    rendered = (config.output / "CORPUS_CARD.md").read_text(encoding="utf-8")
    assert "not UXLC" in rendered and "CLEAN" in rendered
    sums = (config.output / "SHA256SUMS").read_text(encoding="utf-8")
    assert "tanakh_lines_niqqud_v1.txt" in sums and "corpus_card.json" in sums


def test_a_reserved_book_is_left_out_whole(tmp_path):
    reserved = tmp_path / "reserved.json"
    reserved.write_text(
        json.dumps({"schema": "htext_reservations.v1", "set": "test", "registry": "test", "works": [{"source": "tanakh", "work_id": "Ruth"}]}),
        encoding="utf-8",
    )
    config = _config(tmp_path, reservations=[reserved])
    card = tanakh.build(config)
    rights = {row["book"]: row for row in _jsonl_gz(config.output / tanakh.RIGHTS_INDEX_FILE)}
    assert rights["Ruth"]["skipped"] == "eval_reserved" and rights["Ruth"]["htext_release"] is None
    assert card["books"]["skipped"] == {"eval_reserved": 1}
    refs = {row["ref"].split(".")[0] for row in _jsonl_gz(config.output / tanakh.LINE_INDEX_FILE)}
    assert "Ruth" not in refs


def test_a_line_that_matches_eval_text_is_dropped_in_both_forms(tmp_path):
    first = tanakh.build(_config(tmp_path / "a"))
    plain = (tmp_path / "a" / "out" / "tanakh_lines_plain_v1.txt").read_text(encoding="utf-8").splitlines()
    fixture = tmp_path / "eval.hashes.json"
    fixture.write_text(json.dumps({"source": {"repository": "test", "path": "eval.txt", "commit": "0", "sha256": "0", "lines": 1}, "normalization": NORMALIZATION, "stripped": True, **corpus_hashes([plain[1]])}), encoding="utf-8")
    config = _config(tmp_path / "b", leakage_fixtures=[fixture])
    second = tanakh.build(config)
    assert second["files"]["tanakh_lines_plain_v1.txt"]["lines"] == first["files"]["tanakh_lines_plain_v1.txt"]["lines"] - 1
    assert second["files"]["tanakh_lines_niqqud_v1.txt"]["lines"] == first["files"]["tanakh_lines_niqqud_v1.txt"]["lines"] - 1
    assert plain[1] not in (config.output / "tanakh_lines_plain_v1.txt").read_text(encoding="utf-8").splitlines()


def test_a_missing_book_fails(tmp_path):
    config = _config(tmp_path)
    (config.wlc / "Obad.xml").unlink()
    with pytest.raises(FileNotFoundError):
        tanakh.build(config)


def test_cli_refuses_an_unpinned_commit(tmp_path):
    with pytest.raises(SystemExit, match="not the pinned WLC commit"):
        cli.main(["tanakh", "build", "--wlc", str(tmp_path), "--source-commit", "0" * 40, "--output", str(tmp_path / "out"), "--no-reservations", "--no-fit-check"])

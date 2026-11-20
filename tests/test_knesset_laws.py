"""Offline tests for the knesset-laws builder.

The law text below is invented for these tests, in the shape of an OCR'd law:
running headers, margin notes, footnotes and typical OCR slips.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from htext.knesset import laws
from htext.knesset.extract import TEXTS_SCHEMA, extract_all, read_texts
from htext.knesset.fetch import MANIFEST_SCHEMA
from htext.knesset.lexicon import Lexicon, is_hebrew_numeral, word_keys
from htext.leakage import sha256_text
from htext.knesset.text import paragraphs
from htext.leakage import corpus_hashes
from htext.release import S6_LABEL

LAW_TEXT = "\n".join(
    [
        'חוק שמירת הגנים העירוניים, תשי"ב-1952 *',
        "",
        "1. בחוק זה - \"גן\" - שטח פתוח שהרשות המקומית קבעה אותו כגן ציבורי בתחום העיר'",
        "לרבות השבילים והספסלים שבו.",
        "הגדרות",
        "2, הרשות המקומית רשאית לקבוע כללים בדבר השמירה על הגנים, הניקיון והשקיה' וכן",
        "בדבר שעות הפתיחה של הגן לציבור הרחב.",
        "סמכויות הרשות",
        "",
        '* נתקבל בכנסת ביום ה\' בטבת תשי"ב (3 בינואר 1952); הצעת החוק פורסמה בה\'\'ח 90.',
        "",
        '4                                            ספר החוקים 92                  ט"ו בטבת התשי"ב 13.01.1952',
        "",
        "שמירת זכויות",
        ".3 . אין בחוק זה כדי לגרוע מכל דין אחר, ובכלל זה פקודת העיריות, תרצ\"ד-1934 1 (להלן - הפקודה).",
        "4. תחילתו של חוק זה ביום פרסומו ברשומות.",
        "תחילה",
        "",
        '1 ע"ר 1934, תוס\' 1, עמ\' 1.',
        "נדפס בדפוס הממשלה",
    ]
)

LEXICON_TEXT = """
חוק שמירת הגנים העירוניים בחוק זה גן שטח פתוח שהרשות המקומית קבעה אותו כגן ציבורי בתחום העיר
לרבות השבילים והספסלים שבו הגדרות הרשות המקומית רשאית לקבוע כללים בדבר השמירה על הגנים הניקיון והשקיה וכן
בדבר שעות הפתיחה של הגן לציבור הרחב סמכויות הרשות שמירת זכויות אין בחוק זה כדי לגרוע מכל דין אחר ובכלל זה
פקודת העיריות להלן הפקודה תחילתו של חוק זה ביום פרסומו ברשומות תחילה
"""


def _lexicon() -> Lexicon:
    return Lexicon.from_lines([LEXICON_TEXT, LEXICON_TEXT], min_count=2)


def test_paragraphs_drop_headers_footnotes_and_printer_line():
    stats: dict[str, int] = {}
    found = paragraphs(LAW_TEXT, stats)
    texts = [paragraph.text for paragraph in found]
    assert not any("ספר החוקים" in text or "נדפס" in text or "נתקבל" in text or 'ע"ר' in text for text in texts)
    assert stats["lines_dropped:page_header"] == 1
    assert stats["lines_dropped:printer"] == 1
    assert stats["lines_dropped:footnote"] == 2


def test_margin_notes_are_their_own_paragraphs():
    found = paragraphs(LAW_TEXT)
    notes = [paragraph.text for paragraph in found if paragraph.kind == "note"]
    assert notes == ["הגדרות", "סמכויות הרשות", "שמירת זכויות", "תחילה"]
    bodies = [paragraph.text for paragraph in found if paragraph.kind == "body"]
    assert bodies[1].endswith("לרבות השבילים והספסלים שבו.")
    assert not any("הגדרות" in body for body in bodies)


def test_ocr_fixes_and_section_labels():
    stats: dict[str, int] = {}
    bodies = [paragraph.text for paragraph in paragraphs(LAW_TEXT, stats) if paragraph.kind == "body"]
    assert bodies[0] == 'חוק שמירת הגנים העירוניים, תשי"ב-1952'
    assert bodies[1].startswith('בחוק זה - "גן" -') and "בתחום העיר, לרבות" in bodies[1]
    assert "הניקיון והשקיה, וכן" in bodies[2]
    assert bodies[3].startswith("אין בחוק זה") and 'תרצ"ד-1934 (להלן' in bodies[3]
    assert bodies[4] == "תחילתו של חוק זה ביום פרסומו ברשומות."
    assert stats["ocr_fix:apostrophe_comma"] == 2
    assert stats["ocr_fix:footnote_reference"] == 1
    assert stats["section_labels_removed"] == 4
    assert "*" not in " ".join(bodies)


def test_double_apostrophe_is_gershayim():
    stats: dict[str, int] = {}
    text = "הצעת החוק פורסמה בה''ח מספר תשעים וכל זה נכתב כאן לשם הבדיקה בלבד."
    assert 'בה"ח' in paragraphs(text, stats)[0].text
    assert stats["ocr_fix:double_apostrophe"] == 1


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ('תש"ט', True),
        ('תשי"א', True),
        ('בתשל"ג', True),
        ('התשט"ו', True),
        ("ה'", True),
        ('תשכ"ט,', True),
        ('י"ה', False),
        ('יה"ה', False),
        ("מדיבת", False),
        ('תשי"ח-1958', False),
    ],
)
def test_hebrew_numerals(token, expected):
    assert is_hebrew_numeral(token) is expected


def test_word_keys_strip_punctuation_split_joiners_skip_numbers():
    assert word_keys('("גן")') == ["גן"]
    assert word_keys("הפיתוח-הוצאה") == ["הפיתוח", "הוצאה"]
    assert word_keys('תשי"ח-1958') == []
    assert word_keys("(א)") == []
    assert word_keys("20%") == []


def test_lexicon_min_count_and_unknown_words():
    lexicon = Lexicon.from_lines(["מדינת ישראל", "מדינת"], min_count=2)
    assert lexicon.words == {"מדינת"}
    assert lexicon.unknown("איגרות מדיבת ישראל") == ["איגרות", "מדיבת", "ישראל"]
    assert lexicon.unknown('מדינת, תשי"ט (א) 1958') == []


def test_booklet_units_are_series_qualified():
    assert laws.booklet_unit({"publication_series_id": 6071, "magazine_number": 263}) == "sefer_hachukim_263"
    assert laws.booklet_unit({"publication_series_id": 6075, "magazine_number": 70}) == "chukei_taktziv_70"
    assert laws.booklet_unit({"publication_series_id": 9999, "magazine_number": 1}) is None
    assert laws.booklet_unit({"publication_series_id": 6071, "magazine_number": None}) is None


# ---- end to end -------------------------------------------------------------


def _bill(bill_id, series, magazine, documents, knesset=2):
    return {
        "bill_id": bill_id,
        "knesset": knesset,
        "name": f"חוק בדיקה {bill_id}",
        "publication_date": "1952-01-13",
        "publication_series_id": series,
        "publication_series": "ספר החוקים" if series == 6071 else "חוקי תקציב",
        "magazine_number": magazine,
        "page_number": 4,
        "odata_last_updated": None,
        "documents": documents,
    }


def _doc(path, fmt, body: bytes):
    return {"document_bill_id": "1", "format": fmt, "url": f"https://fs.knesset.gov.il//2/law/{Path(path).name}", "file": path, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}


@pytest.fixture
def law_inputs(tmp_path: Path):
    bodies = {name: name.encode() for name in ("2/2_lsr_1.DOC", "2/2_lsr_2.PDF", "2/2_lsr_3.DOC", "2/2_lsr_4.DOC", "2/2_lsr_5.DOC", "2/2_lsr_6.DOC")}
    bills = [
        _bill(1, 6071, 92, [_doc("2/2_lsr_1.DOC", "DOC", bodies["2/2_lsr_1.DOC"])]),
        _bill(2, 6075, 70, [_doc("2/2_lsr_2.PDF", "PDF", bodies["2/2_lsr_2.PDF"])]),  # PDF only: no_doc
        _bill(3, 6071, 263, [_doc("2/2_lsr_3.DOC", "DOC", bodies["2/2_lsr_3.DOC"])]),  # reserved booklet
        _bill(4, 6075, 6075, [_doc("2/2_lsr_4.DOC", "DOC", bodies["2/2_lsr_4.DOC"])]),  # trap: kovetz_hatakanot_6075
        _bill(5, 7777, 5, [_doc("2/2_lsr_5.DOC", "DOC", bodies["2/2_lsr_5.DOC"])]),  # unmapped series
        _bill(6, 6071, 6075, [_doc("2/2_lsr_6.DOC", "DOC", bodies["2/2_lsr_6.DOC"])]),  # SH booklet 6075: not the trap
        _bill(7, 6071, None, [_doc("2/2_lsr_5.DOC", "DOC", bodies["2/2_lsr_5.DOC"])]),  # no booklet number
    ]
    manifest = {"schema": MANIFEST_SCHEMA, "source": {"odata": "https://knesset.gov.il/Odata/ParliamentInfo.svc", "fetched_at": "2026-11-18T00:00:00Z"}, "knessets": [2], "bills": bills}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    other = "הרשות המקומית רשאית לקבוע כללים בדבר שעות הפתיחה של הגן לציבור הרחב וכן בדבר השמירה על השבילים."
    texts = {
        "2/2_lsr_1.DOC": LAW_TEXT,
        "2/2_lsr_3.DOC": other,
        "2/2_lsr_4.DOC": other.replace("הרחב", "הרחב והשבילים"),
        "2/2_lsr_5.DOC": other,
        "2/2_lsr_6.DOC": "תחילתו של חוק זה ביום פרסומו ברשומות, ובכלל זה הפקודה וכל דין אחר שבו.",
    }
    with gzip.open(tmp_path / "texts.jsonl.gz", "wt", encoding="utf-8") as handle:
        handle.write(json.dumps({"schema": TEXTS_SCHEMA, "extractor": "test"}) + "\n")
        for name, text in texts.items():
            handle.write(json.dumps({"file": name, "sha256": hashlib.sha256(bodies[name]).hexdigest(), "extractor": "test", "text": text}, ensure_ascii=False) + "\n")
    reservations = {
        "schema": "heocr_eval_reservations.v1",
        "reservations": [{"set": "test-set", "reshumot_booklets": {"sefer_hachukim": [263], "kovetz_hatakanot": [6075]}}],
    }
    (tmp_path / "reserved.json").write_text(json.dumps(reservations), encoding="utf-8")
    protected_line = "הרשות המקומית רשאית לקבוע כללים"
    fixture = {"source": {"repository": "test", "path": "eval.txt", "commit": "0" * 40, "sha256": "0" * 64, "lines": 1}, "normalization": "NFC lines; word 3-grams are whitespace-split words joined by one space; sha256 of UTF-8", "stripped": True, **corpus_hashes([protected_line])}
    (tmp_path / "fixture.hashes.json").write_text(json.dumps(fixture), encoding="utf-8")
    return tmp_path


def _config(root: Path, **overrides) -> laws.LawsConfig:
    values = dict(
        manifest=root / "manifest.json",
        texts=root / "texts.jsonl.gz",
        lexicon_corpora=(),
        lexicon=_lexicon(),
        leakage_fixtures=[root / "fixture.hashes.json"],
        reservations=[root / "reserved.json"],
        output=root / "out",
        length_profile=[20, 25, 30, 35, 40, 45],
        length_profile_source="test",
        eye_sample_size=5,
    )
    values.update(overrides)
    return laws.LawsConfig(**values)


def _rights(root: Path) -> dict[int, dict]:
    with gzip.open(root / "out" / laws.RIGHTS_INDEX_FILE, "rt", encoding="utf-8") as handle:
        return {row["bill_id"]: row for row in map(json.loads, handle)}


def test_build_end_to_end(law_inputs: Path):
    card = laws.build(_config(law_inputs))
    rights = _rights(law_inputs)
    assert {bill_id: row["skipped"] for bill_id, row in rights.items()} == {
        1: None,
        2: "no_doc",
        3: "eval_reserved",
        4: None,
        5: "series_unmapped",
        6: None,
        7: "no_booklet_number",
    }
    for bill_id, row in rights.items():
        assert row["source_licence"] == S6_LABEL and row["text_quality"] == "ocr_layer"
        assert row["htext_release"] == ("cc0" if row["skipped"] is None else None)
    assert rights[4]["booklet"] == "chukei_taktziv_6075" and rights[6]["booklet"] == "sefer_hachukim_6075"
    assert card["htext_release"] == "cc0" and card["text_quality"] == "ocr_layer" and card["lexicon_eligible"] is False
    assert card["laws"]["skipped"] == {"eval_reserved": 1, "no_booklet_number": 1, "no_doc": 1, "series_unmapped": 1}
    assert card["inputs"]["eval_reservations"][0]["set"] == "test-set"
    assert "263" not in json.dumps(card["inputs"]["eval_reservations"])

    corpus = (law_inputs / "out" / laws.corpus_file_name()).read_text(encoding="utf-8").splitlines()
    assert corpus and len(corpus) == len(set(corpus))
    assert all(len(line) <= 55 for line in corpus)
    assert not any("ספר החוקים" in line for line in corpus)
    assert "הרשות המקומית רשאית לקבוע כללים" not in corpus
    excluded = json.loads((law_inputs / "out" / laws.EXCLUSION_FILE).read_text(encoding="utf-8"))
    assert excluded["booklets"] == ["chukei_taktziv_6075", "sefer_hachukim_6075", "sefer_hachukim_92"]
    sums = (law_inputs / "out" / "SHA256SUMS").read_text().splitlines()
    assert {line.split()[1] for line in sums} >= {laws.corpus_file_name(), laws.RIGHTS_INDEX_FILE, laws.LINE_INDEX_FILE, laws.EYE_SAMPLE_FILE, "corpus_card.json"}
    assert card["eye_check"]["ran"] is False
    assert "Eye check:** not yet run" in (law_inputs / "out" / "CORPUS_CARD.md").read_text(encoding="utf-8")


def test_lexicon_filter_drops_lines_with_unknown_words(law_inputs: Path):
    tiny = Lexicon.from_lines(["חוק זה"] * 2, min_count=2)
    card = laws.build(_config(law_inputs, lexicon=tiny))
    assert card["lexicon_filter"]["segments_dropped"] > 0
    assert card["lexicon_filter"]["drop_rate"] > 0.5
    corpus = (law_inputs / "out" / laws.corpus_file_name()).read_text(encoding="utf-8").splitlines()
    assert all(not tiny.unknown(line) for line in corpus)


def test_build_refuses_texts_not_matching_the_pins(law_inputs: Path):
    manifest = json.loads((law_inputs / "manifest.json").read_text(encoding="utf-8"))
    manifest["bills"][0]["documents"][0]["sha256"] = "f" * 64
    (law_inputs / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="no extracted text for the pinned file"):
        laws.build(_config(law_inputs))


def _eye_check(root: Path, *, errors_for: int = 1, sample_sha: str | None = None, unverifiable: int = -1) -> Path:
    sample_path = root / "out" / laws.EYE_SAMPLE_FILE
    rows = [json.loads(line) for line in sample_path.read_text(encoding="utf-8").splitlines()[1:]]
    document = {
        "schema": laws.EYE_CHECK_SCHEMA,
        "sample_file_sha256": sample_sha or hashlib.sha256(sample_path.read_bytes()).hexdigest(),
        "checked_by": "test",
        "checked_at": "2026-11-18",
        "method": "each line read against the page scan",
        "lines": [
            {"sha256": row["sha256"], "errors": [{"kind": "letter", "words": 1}] if index < errors_for else [], "unverifiable": index == unverifiable}
            for index, row in enumerate(rows)
        ],
    }
    path = root / "eye_check.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_eye_check_goes_on_the_card(law_inputs: Path):
    laws.build(_config(law_inputs))
    card = laws.build(_config(law_inputs, eye_check=_eye_check(law_inputs)))
    eye = card["eye_check"]
    assert eye["ran"] and eye["lines_with_error"] == 1 and eye["sample_lines"] == 5
    assert eye["line_error_rate"] == 0.2 and eye["errors_by_kind"] == {"letter": 1}
    assert "Lines with at least one error: 1 (20.0%)" in (law_inputs / "out" / "CORPUS_CARD.md").read_text(encoding="utf-8")


def test_eye_check_for_another_sample_is_refused(law_inputs: Path):
    laws.build(_config(law_inputs))
    with pytest.raises(ValueError, match="another sample"):
        laws.build(_config(law_inputs, eye_check=_eye_check(law_inputs, sample_sha="0" * 64)))


def test_build_is_deterministic(law_inputs: Path):
    laws.build(_config(law_inputs))
    first = (law_inputs / "out" / "SHA256SUMS").read_text()
    laws.build(_config(law_inputs))
    assert (law_inputs / "out" / "SHA256SUMS").read_text() == first


def test_extract_checks_pins_and_records_failures(tmp_path: Path):
    (tmp_path / "in" / "2").mkdir(parents=True)
    (tmp_path / "in" / "2" / "a.DOC").write_bytes(b"a")
    (tmp_path / "in" / "2" / "b.DOC").write_bytes(b"b")
    manifest = {"bills": [_bill(1, 6071, 1, [_doc("2/a.DOC", "DOC", b"a"), _doc("2/b.DOC", "DOC", b"b"), _doc("2/c.PDF", "PDF", b"c")])]}

    def fake(path: Path) -> str:
        if path.name == "b.DOC":
            raise OSError("cannot read")
        return "טקסט " + path.name

    counts = extract_all(manifest, tmp_path / "in", tmp_path / "texts.jsonl.gz", extractor=("fake", fake))
    assert counts == {"extracted": 1, "failed": 1}
    header, rows = read_texts(tmp_path / "texts.jsonl.gz")
    assert header["extractor"] == "fake" and rows["2/a.DOC"]["text"] == "טקסט a.DOC" and rows["2/b.DOC"]["text"] is None
    assert "2/c.PDF" not in rows
    manifest["bills"][0]["documents"][0]["sha256"] = "0" * 64
    with pytest.raises(SystemExit, match="does not match the manifest"):
        extract_all(manifest, tmp_path / "in", tmp_path / "texts2.jsonl.gz", extractor=("fake", fake))


# ---- quality fixes from the first eye-check pass ----------------------------


def test_table_cells_cut_paragraphs_and_are_dropped():
    stats: dict[str, int] = {}
    text = "660\nציוד משרדי\n(13)\nהוצאות שונות\n1,000"
    found = [paragraph.text for paragraph in paragraphs(text, stats)]
    assert found == ["ציוד משרדי", "הוצאות שונות"]
    assert stats["lines_dropped:table_cell"] == 3


def test_line_end_hyphen_is_mended_only_into_a_known_word():
    from htext.knesset.text import UNRESOLVED_BREAK

    text = "בכל אחד מן המקרים האלה יוצגו לפני הוועדה הנס-\nפחים כאמור בסעיף הקודם לחוק זה."
    stats: dict[str, int] = {}
    mended = paragraphs(text, stats, is_word=lambda word: word == "הנספחים")[0].text
    assert "הנספחים כאמור" in mended and stats["line_breaks:mended"] == 1
    stats = {}
    unresolved = paragraphs(text, stats, is_word=lambda word: False)[0].text
    assert f"הנס{UNRESOLVED_BREAK}פחים" in unresolved and stats["line_breaks:unresolved"] == 1
    assert UNRESOLVED_BREAK in paragraphs(text)[0].text


def test_suspect_words_are_confusions_of_far_more_common_words():
    lexicon = Lexicon.from_lines(["זכאי"] * 100 + ["זבאי"] * 2 + ["כזאת בזאת"] * 100, min_count=2)
    assert lexicon.suspects("הוא זבאי לכך") == [("זבאי", "זכאי")]
    assert lexicon.suspects("הוא זכאי לכך") == []
    assert lexicon.suspects("בזאת וכזאת") == []
    assert lexicon.is_word("זכאי") and not lexicon.is_word("זאכי")


@pytest.mark.parametrize(
    ("text", "dropped"),
    [("לפי סעיפים 75,74 או 75א", True), ("פרט לסעיפים 40,22ב", True), ("סכום של 1,000 לירות", False), ("סכום של 12,500,000 לירות", False), ("סעיפים 74, 75", False)],
)
def test_reversed_number_lists_are_detected(text, dropped):
    assert bool(laws._NUMBER_LIST.search(text)) is dropped


def test_build_reports_suspect_drops(law_inputs: Path, monkeypatch: pytest.MonkeyPatch):
    # The two-corpus veto off: the drop path itself is under test here.
    monkeypatch.setattr("htext.knesset.lexicon.LOCAL_RATIO", 0)
    lexicon = _lexicon()
    # ג/נ is a confusion pair: make "הננים" far more common than "הגנים", so lines with "הגנים" become suspect.
    lexicon.counts = {**lexicon.counts, "הננים": 1000}
    card = laws.build(_config(law_inputs, lexicon=lexicon))
    assert card["lexicon_filter"]["segments_dropped_suspect"] >= 1
    assert "Look-alike words" in (law_inputs / "out" / "CORPUS_CARD.md").read_text(encoding="utf-8")


def test_unverifiable_lines_leave_the_rates(law_inputs: Path):
    laws.build(_config(law_inputs))
    card = laws.build(_config(law_inputs, eye_check=_eye_check(law_inputs, errors_for=1, unverifiable=4)))
    eye = card["eye_check"]
    assert eye["unverifiable_lines"] == 1 and eye["lines_checked"] == 4
    assert eye["line_error_rate"] == 0.25


def test_confusion_pair_names():
    assert laws.confusion_pair("זבאי", "זכאי") == "ב/כ"
    assert laws.confusion_pair("מעיף", "סעיף") == "ס/מ"
    with pytest.raises(ValueError):
        laws.confusion_pair("אבג", "אבד")


def test_suspect_drops_are_counted_by_pair(law_inputs: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("htext.knesset.lexicon.LOCAL_RATIO", 0)
    lexicon = _lexicon()
    lexicon.counts = {**lexicon.counts, "הננים": 1000}
    card = laws.build(_config(law_inputs, lexicon=lexicon))
    by_pair = card["lexicon_filter"]["suspect_drops_by_pair"]
    assert by_pair.get("ג/נ", 0) >= 1 and sum(by_pair.values()) >= card["lexicon_filter"]["segments_dropped_suspect"]
    assert "Dropped by pair: ג/נ" in (law_inputs / "out" / "CORPUS_CARD.md").read_text(encoding="utf-8")


def test_fresh_eye_sample_excludes_earlier_samples(law_inputs: Path):
    laws.build(_config(law_inputs))
    old = law_inputs / "old_sample.jsonl"
    old.write_bytes((law_inputs / "out" / laws.EYE_SAMPLE_FILE).read_bytes())
    old_shas = {json.loads(line)["sha256"] for line in old.read_text(encoding="utf-8").splitlines()[1:]}
    card = laws.build(_config(law_inputs, eye_exclude=[old]))
    new_rows = [json.loads(line) for line in (law_inputs / "out" / laws.EYE_SAMPLE_FILE).read_text(encoding="utf-8").splitlines()]
    assert new_rows[0]["excluded_samples"][0]["lines"] == len(old_shas)
    assert not old_shas & {row["sha256"] for row in new_rows[1:]}
    assert card["eye_check"]["excluded_samples"][0]["file"] == "old_sample.jsonl"
    assert "Fresh sample" in (law_inputs / "out" / "CORPUS_CARD.md").read_text(encoding="utf-8")


def test_two_corpus_rule_rescues_words_common_in_the_corpus():
    lexicon = Lexicon.from_lines(["ברשימות"] * 300 + ["ברשומות"] * 3 + ["זכאי"] * 300 + ["זבאי"] * 2, min_count=2)
    assert lexicon.suspects("פורסם ברשומות") == [("ברשומות", "ברשימות")]
    local = {"ברשומות": 500, "ברשימות": 4, "זכאי": 400, "זבאי": 5}
    assert lexicon.look_alikes("פורסם ברשומות", local) == [("ברשומות", "ברשימות", True)]
    assert lexicon.suspects("פורסם ברשומות", local) == []
    assert lexicon.suspects("הוא זבאי", local) == [("זבאי", "זכאי")]


def test_build_reports_rescued_look_alikes(law_inputs: Path):
    lexicon = _lexicon()
    # "הגנים" is a look-alike of "הננים" in the lexicon, but common in the corpus and "הננים" absent: rescued.
    lexicon.counts = {**lexicon.counts, "הננים": 1000}
    card = laws.build(_config(law_inputs, lexicon=lexicon))
    lex = card["lexicon_filter"]
    assert lex["segments_rescued"] >= 1 and lex["rescued_by_pair"].get("ג/נ", 0) >= 1
    assert lex["rescued_top"][0]["word"] == "הגנים" and lex["rescued_top"][0]["variant"] == "הננים"
    card_md = (law_inputs / "out" / "CORPUS_CARD.md").read_text(encoding="utf-8")
    assert "Rescued by the corpus counts" in card_md and "at least 10 times more common in this corpus" in card_md


def test_samekh_pe_is_a_confusion():
    lexicon = Lexicon.from_lines(["לפי"] * 500 + ["לסי למי"] * 3 + ["למי"] * 20, min_count=2)
    local = {"לסי": 263, "לפי": 12664, "למי": 423}
    assert ("לסי", "לפי") in lexicon.suspects("לסי החוק", local)
    assert laws.confusion_pair("לסי", "לפי") == "ס/פ"


def _write_drop(root: Path, shas, units, **overrides) -> Path:
    drop = {
        "schema": laws.DROP_SCHEMA,
        "corpus": "laws",
        "derived_from": {"file": "knesset_laws_lines_plain_v1.txt", "sha256": "0" * 64, "lines": 1},
        "reservations": {"file": "eval_reservations_v7.json", "sha256": "1" * 64},
        "targets": {"target_a": 1},
        "run_threshold": 5,
        "line_sha256": list(shas),
        "units": list(units),
        **overrides,
    }
    path = root / "drop.json"
    path.write_text(json.dumps(drop), encoding="utf-8")
    return path


def test_overlap_drop_removes_lines_and_whole_laws(law_inputs: Path):
    laws.build(_config(law_inputs))
    before = (law_inputs / "out" / laws.corpus_file_name()).read_text(encoding="utf-8").splitlines()
    with gzip.open(law_inputs / "out" / laws.LINE_INDEX_FILE, "rt", encoding="utf-8") as handle:
        index = [json.loads(line) for line in handle]
    by_law = {}
    for line, row in zip(before, index):
        by_law.setdefault(row["bill_id"], []).append(line)
    assert len(by_law) >= 2
    first_law, other_law = sorted(by_law)[:2]
    dropped_line = by_law[other_law][0]
    drop = _write_drop(law_inputs, [sha256_text(dropped_line)], [first_law])
    card = laws.build(_config(law_inputs, output=law_inputs / "out2", eval_overlap_drop=drop))
    after = (law_inputs / "out2" / laws.corpus_file_name()).read_text(encoding="utf-8").splitlines()
    # Exactly the listed line and the listed law's lines go; every other line stays, in order.
    expected = [line for line in before if line != dropped_line and line not in by_law[first_law]]
    assert after == expected
    with gzip.open(law_inputs / "out2" / laws.RIGHTS_INDEX_FILE, "rt", encoding="utf-8") as handle:
        rights = {row["bill_id"]: row for row in map(json.loads, handle)}
    assert rights[first_law]["skipped"] == "eval_overlap" and rights[first_law]["htext_release"] is None
    info = card["inputs"]["eval_overlap_drop"]
    assert info["line_sha256s"] == 1 and info["units"] == 1 and info["segments_dropped"] == 1
    assert info["segments_dropped_with_laws"] == len(by_law[first_law])
    assert info["sha256"] == hashlib.sha256(drop.read_bytes()).hexdigest()
    card_text = (law_inputs / "out2" / "CORPUS_CARD.md").read_text(encoding="utf-8")
    assert "(1 private development, test and held-out targets)" in card_text and "target_a" not in card_text
    assert info["targets"] == 1 and "target_a" not in json.dumps(card)


def test_build_without_overlap_drop_says_so(law_inputs: Path):
    card = laws.build(_config(law_inputs))
    assert card["inputs"]["eval_overlap_drop"] == {"ran": False}
    assert "Overlap with evaluation text:** not checked" in (law_inputs / "out" / "CORPUS_CARD.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("overrides", [{"schema": "other"}, {"corpus": "pby"}, {"line_sha256": "x"}])
def test_overlap_drop_file_is_checked(law_inputs: Path, overrides):
    drop = _write_drop(law_inputs, [], [])
    drop.write_text(json.dumps({**json.loads(drop.read_text()), **overrides}), encoding="utf-8")
    with pytest.raises(ValueError):
        laws.build(_config(law_inputs, eval_overlap_drop=drop))


def test_inherited_eye_check_keeps_only_lines_still_in_the_build(law_inputs: Path):
    laws.build(_config(law_inputs))
    check = _eye_check(law_inputs, errors_for=2)
    sample = law_inputs / "eye_sample_v1.jsonl"
    sample.write_bytes((law_inputs / "out" / laws.EYE_SAMPLE_FILE).read_bytes())
    rows = [json.loads(line) for line in sample.read_text(encoding="utf-8").splitlines()[1:]]
    # Drop the first sampled line (one that has an error) from the next build.
    drop = _write_drop(law_inputs, [rows[0]["sha256"]], [])
    card = laws.build(_config(law_inputs, output=law_inputs / "out2", eval_overlap_drop=drop, eye_check_inherited=(sample, check)))
    eye = card["eye_check"]
    assert eye["ran"] and eye["inherited"]["lines_still_in_build"] == len(rows) - 1
    assert eye["inherited"]["sample_file"]["lines"] == len(rows)
    assert eye["lines_checked"] == len(rows) - 1 and eye["lines_with_error"] == 1
    text = (law_inputs / "out2" / "CORPUS_CARD.md").read_text(encoding="utf-8")
    assert f"Eye check (inherited):** {len(rows) - 1} of the {len(rows)} lines" in text


def test_inherited_eye_check_must_match_its_sample(law_inputs: Path):
    laws.build(_config(law_inputs))
    check = _eye_check(law_inputs, sample_sha="0" * 64)
    sample = law_inputs / "eye_sample_v1.jsonl"
    sample.write_bytes((law_inputs / "out" / laws.EYE_SAMPLE_FILE).read_bytes())
    with pytest.raises(ValueError):
        laws.build(_config(law_inputs, output=law_inputs / "out2", eye_check_inherited=(sample, check)))
    with pytest.raises(ValueError):
        laws.build(_config(law_inputs, output=law_inputs / "out3", eye_check=check, eye_check_inherited=(sample, check)))

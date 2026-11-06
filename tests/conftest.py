"""Shared test fixtures: a tiny synthetic PBY-shaped dump, and no network.

The mini dump's text is written for these tests. It has the dump's shape
(catalogue columns, ``txt/`` and ``txt_stripped/`` line alignment, footnote
blocks and the credit footer) but no PBY text.
"""

from __future__ import annotations

import csv
import json
import socket
from pathlib import Path

import pytest

from htext.hebrew import strip_marks


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args, **_kwargs):
        raise RuntimeError("tests must not use the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


FOOTER = "את הטקסט לעיל הפיקו מתנדבי פרויקט בן־יהודה באינטרנט. הכל זמין תמיד בכתובת הבאה:https://benyehuda.org/read/1"

PROSE_BODY = [
    "\t",
    "",
    "1",
    "",
    "בבוקר יצאנו לדרך ארוכה אל הכפר שבעמק. השמיים היו בהירים והאוויר היה קר מאוד, ואיש לא דיבר עד שהגענו אל הגשר הישן שעל הנחל.",
    "",
    "המורה סיפר לנו על העיר העתיקה3 ועל השווקים שלה. הוא אמר כי בימים ההם היו הסוחרים באים מארצות רחוקות.",
    "",
    "This line is Latin and is dropped.",
    "",
    "שורה עם ישות &nbsp; נשמטת.",
    "",
    "ובערב חזרנו הביתה עייפים ושמחים\ufe0e, ואמא הכינה לנו מרק חם.",
    "",
    "ה' תשרי תרנ\"ג",
]
PROSE_NOTES = [
    "",
    "",
    "",
    "",
    "הערה ארוכה שאין בה סימן חזרה",
    "ממשיכה כאן ומסתיימת. &nbsp;↩︎",
    "",
]

POEM_POINTED = [
    "הַשֶּׁמֶשׁ עוֹלָה עַל הֶהָרִים",
    "",
    "וְהָרוּחַ נוֹשֶׁבֶת בַּשָּׂדֶה הַיָּרֹק",
    "",
    "הַיְלָדִים שָׁרִים בַּגַּן הַגָּדוֹל וְהַצִּפּוֹרִים עוֹנוֹת לָהֶם מִן הָעֵצִים הַגְּבוֹהִים שֶׁעַל יַד הַבַּיִת",
    "",
    "הַמַּיִם֙ זוֹרְמִים בַּנַּחַל",
    "",
    "שורה בלי ניקוד בשיר",
]


def _work_text(title: str, body: list[str], notes: list[str] | None = None) -> str:
    return "\n".join([title, *body, *(notes or []), FOOTER, ""])


def _plain(text: str) -> str:
    return "\n".join(strip_marks(line) for line in text.split("\n"))


WORKS = [
    # id, path, title, authors, translators, author_uris, translator_uris, language, genre, edition
    (1, "/p1/m1", "בוקר", "סופר ראשון", "", "https://wikidata.org/wiki/Q1", "", "", "prose", ""),
    (2, "/p2/m2", "שיר", "משורר שני", "", "https://wikidata.org/wiki/Q2", "", "", "poetry", 'ורשה: הוצאה, תרע"ב'),
    (3, "/p1/m3", "תרגום", "סופר ראשון", "מתרגם שלישי", "https://wikidata.org/wiki/Q1", "https://wikidata.org/wiki/Q3", "de", "prose", ""),
    (4, "/p4/m4", "עלום", "אלמוני/ת", "", "", "", "", "prose", ""),
    (5, "/p5/m5", "בלי מזהה", "כותב חמישי", "", "https://wikidata.org/wiki/Q0", "", "", "prose", ""),
    (6, "/p1/m6", "מילון", "סופר ראשון", "", "https://wikidata.org/wiki/Q1", "", "", "reference", ""),
    (7, "/p1/m7", "שבור", "סופר ראשון", "", "https://wikidata.org/wiki/Q1", "", "", "prose", "1890"),
    (8, "/p2/m8", "דליפה", "משורר שני", "", "https://wikidata.org/wiki/Q2", "", "", "poetry", ""),
]

PROTECTED_LINE = "הקו הזה מוגן מפני דליפה"


@pytest.fixture
def mini_dump(tmp_path: Path) -> Path:
    dump = tmp_path / "dump"
    texts = {
        1: _work_text("בוקר", PROSE_BODY, PROSE_NOTES),
        2: _work_text("שִׁיר", ["", *POEM_POINTED]),
        3: _work_text("תרגום", ["", "המתרגם עדיין מוגן ולכן השורה הזאת לא תיכנס לקורפוס."]),
        4: _work_text("עלום", ["", "מחבר לא ידוע כתב את השורות האלה בזמן לא ידוע."]),
        5: _work_text("בלי מזהה", ["", "לכותב אין מזהה ולכן אין לו שנת פטירה ידועה."]),
        6: _work_text("מילון", ["", "ערך במילון אינו נכנס כי הסוגה אינה ברשימה."]),
        7: _work_text("שבור", ["", "שורה אחת בלבד בקובץ המנוקד."]),
        8: _work_text("דליפה", ["", PROTECTED_LINE, "", "הַשּׁוּרָה הַזֹּאת נִשְׁאֶרֶת בַּקּוֹרְפּוּס"]),
    }
    with_columns = ["ID", "path", "title", "authors", "translators", "author_uris", "translator_uris", "original_language", "genre", "source_edition"]
    dump.mkdir()
    with (dump / "pseudocatalogue.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(with_columns)
        for row in WORKS:
            writer.writerow([*row[:8], f"Translation missing: he.{row[8]}", row[9]])
    for work_id, path, *_ in WORKS:
        pointed = texts[work_id]
        plain = _plain(pointed)
        if work_id == 7:
            plain += "שורה עודפת\n"
        for folder, content in (("txt", pointed), ("txt_stripped", plain)):
            target = dump / folder / f"{path.lstrip('/')}.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
    return dump


@pytest.fixture
def mini_creators(tmp_path: Path) -> Path:
    document = {
        "schema": "pby_creators.v1",
        "source": {"wikidata_api": "test", "dump_commit": "test"},
        "creators": [
            {"qid": "Q1", "death_year": 1900, "death_year_precision": "day", "birth_year": 1840, "wikidata_revision": 11},
            {"qid": "Q2", "death_year": 1920, "death_year_precision": "year", "birth_year": 1860, "wikidata_revision": 12},
            {"qid": "Q3", "death_year": 1980, "death_year_precision": "day", "birth_year": 1900, "wikidata_revision": 13},
        ],
        "manual": [],
    }
    path = tmp_path / "creators.json"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def mini_leakage(tmp_path: Path) -> Path:
    from htext.leakage import fixture_for_file

    source = tmp_path / "protected.txt"
    source.write_text(PROTECTED_LINE + "\n", encoding="utf-8")
    fixture = fixture_for_file(source, repository="test/protected", source_path="protected.txt", commit="0" * 40)
    path = tmp_path / "protected.hashes.json"
    path.write_text(json.dumps({"fixtures": [fixture]}, ensure_ascii=False), encoding="utf-8")
    return path

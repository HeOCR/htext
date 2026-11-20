"""Offline ProofreadPage export fixtures, with invented titles and text."""

import bz2
import gzip
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from xml.sax.saxutils import escape

import mwparserfromhell
import pytest

from htext.cli import main
from htext.leakage import NORMALIZATION, corpus_hashes, sha256_text
from htext.wikisource import RIGHTS_INDEX, BuildConfig, DumpPin, build, render_card
from htext.wikisource import dump, text, __name__ as module_name


def revision(page_id, namespace, title, content, *, model="wikitext", fmt="text/x-wiki", redirect=False):
    return (
        f"<page><title>{escape(title)}</title><ns>{namespace}</ns><id>{page_id}</id>"
        + ('<redirect title="אל יעד" />' if redirect else "")
        + f"<revision><id>{page_id + 1000}</id><parentid>17</parentid><contributor><id>99</id></contributor>"
        f"<model>{model}</model><format>{fmt}</format><text>{escape(content)}</text></revision></page>"
    )


def proof(page_id, name, body, *, quality=3, basis="{{PD-old}}", redirect=False):
    content = f'<noinclude><pagequality level="{quality}" user="fixture" />{basis}</noinclude>{body}<noinclude>כותרת תחתית</noinclude>'
    return revision(page_id, dump.PAGE, "עמוד:" + name, content, model="proofread-page", redirect=redirect)


@pytest.fixture
def config(tmp_path, monkeypatch):
    pages = [
        # Related work and its other volume appear before the reserved Index.
        revision(10, dump.ARTICLE, "ספר שמור/א", '<pages index="Reserved_volume.pdf" from="1" to="3" />'),
        revision(11, dump.ARTICLE, "ספר שמור/ב", '<pages index=Other_volume.djvu/>'),
        proof(20, "Reserved volume.pdf/1", "אסור למסור למפרש"),
        proof(21, "Reserved volume.pdf/2", "אסור למסור למפרש", quality=4),
        proof(22, "Other volume.djvu/3", "אסור למסור למפרש"),
        revision(30, dump.INDEX, "מפתח:Reserved volume.pdf", "אסור למסור למפרש <pagelist />", model="proofread-index"),
        revision(31, dump.INDEX, "מפתח:Other volume.djvu", "אסור למסור למפרש <pagelist />", model="proofread-index"),
        proof(32, "Separate.pdf/1", "אסור למסור למפרש"),
        proof(33, "Separate.pdf/2", "אסור למסור למפרש"),
        proof(34, "Separate.pdf/3", "בלילה ירד טל\nיש כאן משפט לעמוד השני", quality=4),
        proof(35, "Separate.pdf/4", "נדחה לפי שלמות ההגהה", quality=2),
        proof(36, "Separate.pdf/5", "נדחה בגלל היעדר סימון", basis=""),
        proof(37, "Separate.pdf/6", "נדחתה הפניה", redirect=True),
        proof(38, "Separate.pdf/7", "טל ירד על [[שדה נסיוני|השדה]] {{הערה|נסתר}}<ref>הערה</ref>\n"
              "<div class=navbox>קודם הבא</div>\n"
              "<!-- נסתר -->[[קטגוריה:נחלת הכלל]]\n=== כותרת ניווט ===\n"
              "שָׁלוֹם עוֹלָם\n<references />\n"
              "זה משפט דליפה בדוי"),
        revision(39, dump.PAGE, "עמוד:Separate.pdf/8", "טקסט שאינו עמוד מוגה {{PD-old}}"),
        revision(40, dump.ARTICLE, "נוסח עיקרי", "טקסט מאמר שלא יעבור בהגהה {{PD-old}}"),
    ]
    raw = ('<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/">'
           '<siteinfo><dbname>hewikisource</dbname></siteinfo>' + "".join(pages) + "</mediawiki>")
    source = tmp_path / "fixture.xml.bz2"
    source.write_bytes(bz2.compress(raw.encode("utf-8")))
    pin = DumpPin("20261101", hashlib.sha256(source.read_bytes()).hexdigest(), source.stat().st_size)
    monkeypatch.setattr(f"{module_name}.DumpPin", lambda: pin)

    reserved = tmp_path / "reserved.json"
    reserved.write_text(json.dumps({
        "schema": "heocr_eval_reservations.v7",
        "reservations": [{"set": "fixture", "item_ids": ["wikisource_he_proofread:ws_index_30__p0001#L001"]}],
    }), encoding="utf-8")
    drop = tmp_path / "overlap.json"
    drop.write_text(json.dumps({
        "schema": "htext_eval_overlap_drop.v1", "corpus": "wikisource", "units": [32, "עמוד:Separate.pdf/2"],
        "line_sha256": [sha256_text("בלילה ירד טל")],
    }), encoding="utf-8")
    leakage = tmp_path / "fixture.hashes.json"
    leakage.write_text(json.dumps({
        "source": {"repository": "fixture"}, "normalization": NORMALIZATION, "stripped": True,
        **corpus_hashes(["משפט דליפה בדוי"]),
    }), encoding="utf-8")
    return BuildConfig(source, tmp_path / "output", [reserved], drop, [36, 39], "fixture", [leakage])


def test_build_skips_reserved_payloads_and_writes_attribution(config, monkeypatch):
    real_scan = dump.scan
    pass_number = 0

    def verify_reader(path, *, select, finish):
        nonlocal pass_number
        pass_number += 1

        def checked_select(page):
            consume = select(page)
            # Check the XML reader receives no consumer for reserved Indexes
            # or proofread pages, including the second volume mapped by work.
            if page.id in {20, 21, 22, 30, 31, 32, 33}:
                assert consume is None
            if pass_number == 2 and page.namespace == dump.ARTICLE:
                assert consume is None
            return consume

        real_scan(path, select=checked_select, finish=finish)

    monkeypatch.setattr(dump, "scan", verify_reader)
    card = build(config)
    assert pass_number == 2
    assert card["release"]["release_name"] == "htext-by-sa"
    assert card["eval_reservations"]["units"] == 1
    assert card["eval_reservations"]["reserved_indexes"] == 1
    assert card["eval_reservations"]["works_excluded"] == 1
    assert card["eval_reservations"]["pages_excluded"] == 5
    assert card["eval_reservations"]["article_pages_excluded"] == 2
    assert card["counts"]["pages_not_proofread"] == 2
    assert card["counts"]["pages_without_rights_basis"] == 1
    assert card["counts"]["lines_dropped:leak_word3"] == 1
    assert card["eval_overlap_drop"] == {"units": 2, "line_sha256s": 1, "lines_dropped": 1}

    plain_lines = ["יש כאן משפט לעמוד השני", "טל ירד על השדה"]
    niqqud_lines = ["שָׁלוֹם עוֹלָם"]
    assert (config.output / "wikisource_plain_v1.txt").read_text().splitlines() == plain_lines
    assert (config.output / "wikisource_niqqud_v1.txt").read_text().splitlines() == niqqud_lines
    assert card["totals"] == {"pages": 2, "lines": 3, "characters": sum(map(len, plain_lines + niqqud_lines))}
    assert (config.output / "CORPUS_CARD.md").read_text() == render_card(card)
    assert "CC BY-SA 4.0" in (config.output / "NOTICE.md").read_text()

    with gzip.open(config.output / RIGHTS_INDEX, "rt", encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle]
    assert [record["page_id"] for record in records] == [34, 38]
    page = records[1]
    assert page["title"] == "עמוד:Separate.pdf/7"
    assert page["revision_id"] == 1038
    assert page["revision_url"].endswith("oldid=1038")
    assert page["credit"] == {"text": "Hebrew Wikisource contributors", "url": page["history_url"]}
    assert page["history_url"].endswith("action=history")
    assert page["source_licence"] == "CC BY-SA 4.0"
    assert page["htext_release"] == "by-sa"
    assert page["text_quality"] == "transcription"
    assert page["underlying_work_rights_basis"] == [
        {"kind": "category", "marking": "נחלת הכלל"}, {"kind": "template", "marking": "PD-old"},
    ]
    assert page["line_ranges"] == {"plain": {"first_line": 2, "lines": 1}, "niqqud": {"first_line": 1, "lines": 1}}


def test_cli_build_is_reproducible_and_card_matches_registry(config, capsys):
    profile = config.output.parent / "profile.txt"
    profile.write_text("א" * 36 + "\n" + "ב" * 39 + "\n", encoding="utf-8")
    args = [
        "wikisource", "build", "--dump", str(config.dump), "--reserved", str(config.reservations[0]),
        "--eval-overlap-drop", str(config.eval_overlap_drop), "--length-profile", str(profile),
        "--no-fit-check", "--leakage", str(config.leakage_fixtures[0]),
    ]
    other = config.output.with_name("second")
    assert main([*args, "--output", str(config.output)]) == 0
    assert main([*args, "--output", str(other)]) == 0
    assert "Total: 2 pages, 3 lines" in capsys.readouterr().out
    for file in config.output.iterdir():
        assert file.read_bytes() == (other / file.name).read_bytes()
    for line in (config.output / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ")
        assert hashlib.sha256((config.output / name).read_bytes()).hexdigest() == digest

    plan = json.loads((Path(__file__).parents[1] / "data/wikisource/v1/corpus_card.json").read_text())
    card = json.loads((config.output / "corpus_card.json").read_text())
    for field in ("credit", "htext_release", "source_licence", "text_quality", "status"):
        assert card[field] == plan[field]


def test_required_inputs_and_identity_fail_closed(config):
    with pytest.raises(ValueError, match="eval-overlap-drop is required"):
        build(replace(config, eval_overlap_drop=None))
    doc = json.loads(config.eval_overlap_drop.read_text())
    config.eval_overlap_drop.write_text(json.dumps({**doc, "corpus": "laws"}))
    with pytest.raises(ValueError, match="for corpus 'wikisource'"):
        build(config)
    config.eval_overlap_drop.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="must include Hebrew Wikisource units"):
        build(replace(config, reservations=[]))
    config.reservations[0].write_text(json.dumps({
        "schema": "heocr_eval_reservations.v7", "reservations": [{"set": "fixture", "wikisource_indexes": ["ws_index_999"]}],
    }))
    with pytest.raises(ValueError, match="absent from the pinned dump"):
        build(config)
    config.dump.write_bytes(b"wrong source")
    with pytest.raises(ValueError, match="size and SHA-256 pin"):
        build(config)
    assert not config.output.exists()


@pytest.mark.parametrize(("marker", "admitted"), [
    ("{{זכויות יוצרים|שנת פטירה=1955}}", True),
    ("{{זכויות יוצרים|שנת פטירה=1956}}", False),
    ("{{PD-US}}", False),
    ("{{PD-old}}{{CC-BY-NC}}", False),
    ("<ref>{{PD-old}}</ref><!-- [[קטגוריה:נחלת הכלל]] -->", False),
    ("{{CC-BY-SA-4.0}}", True),
])
def test_explicit_rights_marking_and_cutoff(marker, admitted):
    page = text.ProofreadPage(3, "", marker, "")
    assert bool(text.rights_basis(page, mwparserfromhell.parse(marker), as_of=2026)) is admitted


def test_json_serialization_and_real_quality_field():
    raw = json.dumps({"header": "{{PD-Israel}}", "body": "מילים לדוגמה", "footer": "", "level": {"level": 4}})
    assert text.proofread_page(raw, "proofread-page", "application/json") == text.ProofreadPage(
        4, "{{PD-Israel}}", "מילים לדוגמה", "",
    )
    fake = 'שורה עם <pagequality level="4" /> {{PD-Israel}}'
    assert text.proofread_page(fake, "proofread-page", "text/x-wiki") is None


def test_transclusion_targets_across_chunk_boundaries():
    references = dump.References()
    for ch in '<pages index="מפתח:Some_book.pdf"/> {{:עמוד:Other_book.djvu/3}} <pages index=third.pdf/>':
        references.feed(ch)
    assert references.indexes == {"Some book.pdf", "Other book.djvu", "Third.pdf"}


def test_navigation_sections_and_unclosed_references():
    code = mwparserfromhell.parse(
        "משפט פתיחה\n== ראו גם ==\n[[קישור ניווט]]\n=== כותרת משנה ===\nעוד ניווט\n"
        "== פרק ==\nהנה משפט תקין<ref>הערה לא סגורה\nטקסט הערה נמשך"
    )
    assert list(text.text_lines(code)) == ["משפט פתיחה", "הנה משפט תקין"]

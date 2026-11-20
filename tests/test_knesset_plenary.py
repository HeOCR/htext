"""Offline tests for the knesset-plenary builder. All text is invented; the roster and the tagger spans are fakes.

hocrgen (the plenary paragraph rules and the private-names gate) comes from the ``plenary`` extra; without it these
tests skip. CI runs them in the ``plenary`` job.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

pytest.importorskip("hocrgen.privacy.plenary_names")

from hocrgen.privacy.plenary_names import Roster  # noqa: E402

from htext.knesset import plenary as pl  # noqa: E402
from htext.knesset.extract import PLENARY_TEXTS_SCHEMA  # noqa: E402
from htext.knesset.lexicon import Lexicon  # noqa: E402
from htext.knesset.plenary_fetch import MANIFEST_SCHEMA  # noqa: E402

# An invented MK, in terms 2 and 20.
ROSTER = Roster.from_people([{"first": "רונן", "last": "גלבוע", "knessets": [2, 20]}])
PRIVATE = "פלוני אלמוני"

K2_TEXT = "\n".join([
    "",
    "דיון על גני ילדים ומורות",
    "הבוקר נעסוק בגני הילדים בערי הפיתוח ובמספר המורות החדשות",
    "שהתחילו לעבוד השנה בכל אחד מהגנים האלה ובבתי הספר.",
    '•) "דברי הכנסת" חוב׳ א, עמ׳ 3.',
    "12",
    "הנושא השני הוא תקציב המשרד שנדון בוועדה בשבוע שע-",
    "בר ואושר ברוב קולות של כל חברי הוועדה לאחר דיון ארוך.",
    f"חבר הכנסת גלבוע אמר כי מר {PRIVATE} כתב לו מכתב על הנושא.",
    "",
])
K20_TEXT = "\n".join([
    "תוכן העניינים",
    "דברי פתיחה\t PAGEREF _Toc1 \\h 3",
    '<< יור >> היו"ר רונן גלבוע: << יור >>',
    "אני פותח את הישיבה של הכנסת היום ונעבור לסדר היום שנקבע בוועדה.",
    "<< דובר >> רונן גלבוע (הסיעה): << דובר >>",
    "הצעת החוק הזאת תעבור לוועדה והיא תדון בה בשבוע הבא בישיבה מיוחדת.",
])
WORDS = " ".join(K2_TEXT.split() + K20_TEXT.split() + ["שעבר"])


def _doc(path: str, fmt: str, body: bytes) -> dict:
    return {"format": fmt, "url": f"https://fs.knesset.gov.il/{path}", "file": path, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}


def _session(pid: int, knesset: int, number: int, docs: list) -> dict:
    return {"plenum_session_id": pid, "knesset": knesset, "number": number, "name": f"ישיבה {number}", "start_date": "1953-01-01T16:00:00",
            "documents": docs}


@pytest.fixture
def inputs(tmp_path: Path) -> Path:
    bodies = {"2/2_ptm_1.doc": b"k2", "2/2_ptm_1.pdf": b"k2pdf", "20/20_ptm_2.doc": b"k20", "20/20_ptm_3.doc": b"k20b"}
    sessions = [
        _session(1, 2, 30, [_doc("2/2_ptm_1.doc", "DOC", bodies["2/2_ptm_1.doc"]), _doc("2/2_ptm_1.pdf", "PDF", bodies["2/2_ptm_1.pdf"])]),
        _session(2, 20, 5, [_doc("20/20_ptm_2.doc", "DOC", bodies["20/20_ptm_2.doc"])]),
        _session(3, 20, 6, [_doc("20/20_ptm_3.doc", "DOC", bodies["20/20_ptm_3.doc"])]),  # never tagged
    ]
    manifest = {"schema": MANIFEST_SCHEMA, "source": {"fetched_at": "2026-11-19T00:00:00Z"},
                "counts": {"selection": {"reserved_sittings": 1, "no_unit_id": 0}}, "sessions": sessions}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    texts = {"2/2_ptm_1.doc": K2_TEXT, "20/20_ptm_2.doc": K20_TEXT, "20/20_ptm_3.doc": K20_TEXT.replace("מיוחדת", "נוספת")}
    with gzip.open(tmp_path / "texts.jsonl.gz", "wt", encoding="utf-8") as handle:
        handle.write(json.dumps({"schema": PLENARY_TEXTS_SCHEMA, "extractor": "test"}) + "\n")
        for name, text in texts.items():
            handle.write(json.dumps({"file": name, "sha256": hashlib.sha256(bodies[name]).hexdigest(), "extractor": "test", "text": text},
                                    ensure_ascii=False) + "\n")
    (tmp_path / "lexicon.txt").write_text((WORDS + "\n") * 2, encoding="utf-8")
    reserved = {"schema": "heocr_eval_reservations.v1", "owner": "eval", "as_of": "2026-11-18",
                "reservations": [{"set": "pmod", "unit_ids": ["plenary:K2_99"]}], "supersedes": {"file": "v0.json", "sha256": "0"}}
    (tmp_path / "reserved.json").write_text(json.dumps(reserved), encoding="utf-8")
    return tmp_path


def _candidates(root: Path) -> dict:
    lexicon = Lexicon.from_lines([WORDS] * 2, min_count=2)
    return pl.candidates(pl.CandidatesConfig(
        manifest=root / "manifest.json", texts=root / "texts.jsonl.gz", output=root / "work", length_profile=[30, 40, 50, 55],
        length_profile_source="test", lexicon=lexicon))


def _spans(root: Path, skip: set[str] = frozenset()) -> Path:
    """Fake tagger: the invented private name and the MK's full name, wherever they occur in a stream."""
    out = []
    for line in (root / "work" / "ner_input.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["id"] in skip:
            continue
        spans = []
        for name in (PRIVATE, "רונן גלבוע"):
            start = row["text"].find(name)
            while start >= 0:
                spans.append({"start": start, "end": start + len(name), "text": name, "score": 0.99})
                start = row["text"].find(name, start + 1)
        out.append(json.dumps({"id": row["id"], "person_spans": spans}, ensure_ascii=False))
    path = root / "spans.jsonl"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path


def _config(root: Path, **overrides) -> pl.PlenaryConfig:
    values = dict(manifest=root / "manifest.json", candidates=root / "work" / "candidates.jsonl.gz", spans=root / "spans.jsonl",
                  output=root / "out", reservations=[root / "reserved.json"], lexicon_corpora=[root / "lexicon.txt"], roster=ROSTER, eye_sample_size=3)
    values.update(overrides)
    return pl.PlenaryConfig(**values)


def _lines(root: Path, quality: str, out: str = "out") -> list[str]:
    return (root / out / pl.corpus_file(quality)).read_text(encoding="utf-8").splitlines()


# --- paragraphs ---------------------------------------------------------------------------------------------------


def test_ocr_paragraphs_drop_footnotes_and_page_numbers_and_mend_hyphens():
    stats: dict = {}
    paragraphs = pl.ocr_paragraphs(K2_TEXT, stats, Lexicon.from_lines([WORDS] * 2, min_count=2).is_word)
    texts = [p.text for p in paragraphs]
    assert not any("דברי הכנסת" in t for t in texts), "the footnote is dropped"
    assert stats["lines_dropped:footnote"] == 1 and stats["lines_dropped:no_text"] == 1
    assert any("שעבר ואושר" in t for t in texts), "the line-end hyphen is mended into a known word"
    # A sentence that ends on a short line closes its paragraph.
    assert any(t.endswith("ובבתי הספר.") for t in texts)


def test_born_digital_paragraphs_cut_the_front_matter_and_keep_marker_headings():
    stats: dict = {}
    paragraphs = pl.born_digital_paragraphs(K20_TEXT, stats)
    assert paragraphs[0].kind == "heading" and paragraphs[0].structural
    assert not any("PAGEREF" in p.text or "תוכן העניינים" in p.text for p in paragraphs)
    assert stats["paragraphs_dropped:front_matter"] >= 1
    assert all("<<" not in p.text for p in paragraphs)


# --- candidates and build -------------------------------------------------------------------------------------------


def test_candidates_write_lines_and_streams(inputs: Path):
    result = _candidates(inputs)
    streams = [json.loads(line) for line in (inputs / "work" / "ner_input.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {s["id"] for s in streams} == {"K2_30", "K20_5", "K20_6"}
    assert result["stats"]["sittings:with_candidates"] == 3


def test_build_gates_private_names_and_splits_files_by_text_quality(inputs: Path):
    _candidates(inputs)
    _spans(inputs, skip={"K20_6"})
    card = pl.build(_config(inputs))
    ocr, transcription = _lines(inputs, "ocr_layer"), _lines(inputs, "transcription")
    everything = ocr + transcription
    assert not any(PRIVATE.split()[0] in line for line in everything), "a line naming a private person goes whole"
    assert ocr and transcription
    assert any("פותח את הישיבה של הכנסת" in line for line in transcription)
    # The untagged sitting is dropped whole, fail closed.
    assert card["privacy"]["lines_dropped_by_reason"].get("untagged", 0) > 0
    assert not any("נוספת" in line for line in transcription)
    assert card["text_quality"] == {pl.corpus_file("ocr_layer"): "ocr_layer", pl.corpus_file("transcription"): "transcription"}
    with gzip.open(inputs / "out" / pl.RIGHTS_INDEX_FILE, "rt", encoding="utf-8") as handle:
        rights = {row["unit_id"]: row for row in map(json.loads, handle)}
    assert rights["K2_30"]["text_quality"] == "ocr_layer" and rights["K20_5"]["text_quality"] == "transcription"
    assert rights["K20_6"]["htext_release"] is None and rights["K20_6"]["skipped"]
    assert card["inputs"]["reserved_sittings_in_corpus"] == 0
    assert "K2_99" not in json.dumps(card) and "K2_99" not in (inputs / "out" / pl.RIGHTS_INDEX_FILE).read_bytes().decode("latin-1")


def test_ocr_lines_never_feed_the_lexicon_and_unknown_words_go(inputs: Path):
    _candidates(inputs)
    _spans(inputs)
    # A lexicon corpus without the K2 words: every OCR line has an unknown word, so the OCR file is empty,
    # because its own lines are never counted into the lexicon.
    (inputs / "lexicon.txt").write_text(" ".join(K20_TEXT.split()) + "\n", encoding="utf-8")
    card = pl.build(_config(inputs))
    assert _lines(inputs, "ocr_layer") == []
    assert card["pipeline"]["lines_dropped:lexicon"] > 0
    assert "the gated K13-25 lines" in card["inputs"]["lexicon"]["built_from"]


def test_a_reserved_sitting_in_the_manifest_is_refused(inputs: Path):
    manifest = json.loads((inputs / "manifest.json").read_text(encoding="utf-8"))
    manifest["sessions"].append(_session(9, 2, 99, []))
    (inputs / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    _candidates(inputs)
    _spans(inputs)
    with pytest.raises(ValueError, match="eval-reserved"):
        pl.build(_config(inputs))


def test_overlap_drop_removes_lines_and_whole_sittings_and_the_card_gives_counts_only(inputs: Path):
    _candidates(inputs)
    _spans(inputs)
    pl.build(_config(inputs))
    first = _lines(inputs, "transcription")
    drop = {"schema": pl.DROP_SCHEMA, "corpus": "plenary", "targets": {"target_a": 1, "target_b": 2}, "run_threshold": 5,
            "line_sha256": [hashlib.sha256(first[0].encode()).hexdigest()], "units": ["K2_30"]}
    (inputs / "drop.json").write_text(json.dumps(drop), encoding="utf-8")
    card = pl.build(_config(inputs, output=inputs / "out2", eval_overlap_drop=inputs / "drop.json"))
    assert first[0] not in _lines(inputs, "transcription", "out2")
    assert _lines(inputs, "ocr_layer", "out2") == []
    info = card["inputs"]["eval_overlap_drop"]
    # The listed line occurs in both K20 sittings; both copies go.
    assert info["targets"] == 2 and info["units"] == 1 and info["lines_dropped"] == 2
    text = json.dumps(card) + (inputs / "out2" / "CORPUS_CARD.md").read_text(encoding="utf-8")
    assert "target_a" not in text and "target_b" not in text


def test_lines_are_unique_and_the_eye_sample_comes_from_pdf_sittings(inputs: Path):
    _candidates(inputs)
    _spans(inputs)
    pl.build(_config(inputs))
    lines = _lines(inputs, "ocr_layer") + _lines(inputs, "transcription")
    assert len(lines) == len(set(lines))
    rows = [json.loads(line) for line in (inputs / "out" / pl.EYE_SAMPLE_FILE).read_text(encoding="utf-8").splitlines()[1:]]
    assert rows and all(row["unit_id"] == "K2_30" and row["pdf"] == "2/2_ptm_1.pdf" for row in rows)
    sums = (inputs / "out" / "SHA256SUMS").read_text().splitlines()
    assert {line.split()[1] for line in sums} >= {pl.corpus_file("ocr_layer"), pl.corpus_file("transcription"), pl.LINE_INDEX_FILE, pl.RIGHTS_INDEX_FILE}


def test_a_bad_drop_file_is_refused(inputs: Path):
    _candidates(inputs)
    _spans(inputs)
    (inputs / "drop.json").write_text(json.dumps({"schema": pl.DROP_SCHEMA, "corpus": "laws", "line_sha256": [], "units": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        pl.build(_config(inputs, eval_overlap_drop=inputs / "drop.json"))

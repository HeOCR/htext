import json

from htext.leakage import NORMALIZATION, Protected, corpus_hashes, fixture_for_file, sha256_text


def test_fixture_stores_hashes_only(tmp_path):
    source = tmp_path / "eval.txt"
    source.write_text("אחת שתיים שלוש ארבע\nשָׁלוֹם לָכֶם חֲבֵרִים\n", encoding="utf-8")
    fixture = fixture_for_file(source, repository="r", source_path="p", commit="c" * 40)
    assert fixture["source"]["lines"] == 2 and fixture["normalization"] == NORMALIZATION
    text = json.dumps(fixture, ensure_ascii=False)
    assert "שתיים" not in text and "שָׁלוֹם" not in text
    # Pointed lines are hashed in their stripped form too.
    assert sha256_text("שלום לכם חברים") in fixture["line_sha256"]


def test_protected_leak_checks_lines_and_trigrams(tmp_path):
    path = tmp_path / "f.hashes.json"
    hashes = corpus_hashes(["אחת שתיים שלוש ארבע"])
    path.write_text(
        json.dumps({"source": {"repository": "r"}, "normalization": NORMALIZATION, "stripped": True, **hashes}),
        encoding="utf-8",
    )
    protected = Protected.load([path])
    assert protected.leak("אחת שתיים שלוש ארבע") == "line"
    assert protected.leak("ואז אחת שתיים שלוש") == "word3"
    assert protected.leak("אחת שתיים חמש") is None
    assert protected.leak("שורה אחרת", "שתיים שלוש ארבע") == "word3"

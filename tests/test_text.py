import pytest

from htext.pby.text import (
    AlignmentError,
    LengthSampler,
    SourceLine,
    body_line_range,
    choose_segment,
    line_rejection,
    normalise,
    source_lines,
    word_spans,
)

FOOTER = "הפיקו מתנדבי פרויקט בן־יהודה https://benyehuda.org/read/1"


def test_body_ends_at_footer_without_notes():
    assert body_line_range(["title", "a", "b", FOOTER, ""]) == (1, 3)


def test_body_ends_before_a_multi_line_footnote_block():
    lines = ["title", "body", "", "", "", "note start", "note end ↩︎", FOOTER]
    assert body_line_range(lines) == (1, 2)


def test_footnote_without_a_blank_gap_drops_the_work():
    assert body_line_range(["title", "body", "note ↩︎", FOOTER]) is None


def test_normalise_strips_selectors_references_and_spacing():
    assert normalise("עיר\ufe0e  עתיקה3 ,\tוזהו ", strip_references=True) == "עיר עתיקה , וזהו"
    assert normalise("עתיקה3 שם", strip_references=False) == "עתיקה3 שם"


def test_source_lines_require_alignment():
    with pytest.raises(AlignmentError):
        source_lines("t\na\n" + FOOTER, "t\na\nb\n" + FOOTER)


@pytest.mark.parametrize(
    "pointed, reason",
    [
        ("This is Latin", "latin"),
        ("שורה &nbsp; כאן", "entity"),
        ("ראו www.example.com", "url"),
        ("עיר3 עתיקה", "letter_digit"),
        ("שורה רגילה בהחלט", None),
    ],
)
def test_line_rejection(pointed, reason):
    assert line_rejection(SourceLine(1, pointed, pointed)) == reason


def test_verse_lines_are_kept_or_split_in_balance():
    words = "אחת שתיים שלוש".split()
    assert word_spans(words, verse=True, targets=LengthSampler([30], 1)) == [(0, 3)]
    long_words = ("מילה " * 20).split()
    spans = word_spans(long_words, verse=True, targets=LengthSampler([30], 1))
    lengths = [len(" ".join(long_words[a:b])) for a, b in spans]
    assert len(spans) == 2 and max(lengths) <= 55 and abs(lengths[0] - lengths[1]) <= 5


def test_prose_is_packed_to_the_closest_boundary_and_breaks_at_long_enough_sentences():
    words = "אחת שתיים שלוש. ארבע חמש שש שבע שמונה".split()
    # Target 11: "אחת שתיים" (9) is closer than "אחת שתיים שלוש." (15).
    spans = word_spans(words, verse=False, targets=LengthSampler([11], 1))
    pieces = [" ".join(words[a:b]) for a, b in spans]
    assert pieces[0] == "אחת שתיים"
    assert " ".join(pieces) == " ".join(words)
    # Target 18: the sentence end at 15 characters (>= 80% of 18) closes the line.
    spans = word_spans(words, verse=False, targets=LengthSampler([18], 1))
    assert " ".join(words[slice(*spans[0])]) == "אחת שתיים שלוש."
    # Target 40: a short sentence does not close the line.
    spans = word_spans(words, verse=False, targets=LengthSampler([40], 1))
    assert spans == [(0, len(words))]
    # A short last line joins the line before it.
    words = "אחת שתיים שלוש ארבע חמש שש".split()
    assert word_spans(words, verse=False, targets=LengthSampler([20], 1)) == [(0, 6)]
    # Lines never pass the cap.
    many = ("מילה " * 30).split()
    assert all(len(" ".join(many[a:b])) <= 55 for a, b in word_spans(many, verse=False, targets=LengthSampler([200], 1)))


def test_length_sampler_is_deterministic():
    assert [LengthSampler(range(10, 50), "15:3").next() for _ in range(3)] == [LengthSampler(range(10, 50), "15:3").next() for _ in range(3)]


def test_niqqud_split():
    segment, _ = choose_segment("שָׁלוֹם לָכֶם", "שלום לכם", threshold=0.5, allow_maqaf=False)
    assert segment.subset == "niqqud" and segment.text == "שָׁלוֹם לָכֶם"
    # Sparse pointing goes to the plain subset, from the stripped form.
    segment, _ = choose_segment("סבּות רבות כאן", "סבות רבות כאן", threshold=0.5, allow_maqaf=False)
    assert segment.subset == "plain" and segment.text == "סבות רבות כאן"
    # Cantillation sends a fully pointed line to the plain subset only.
    segment, _ = choose_segment("הַמַּיִם֙ זוֹרְמִים", "המים זורמים", threshold=0.5, allow_maqaf=False)
    assert segment.subset == "plain" and segment.text == "המים זורמים"
    # Marks left in txt_stripped are removed from plain lines.
    segment, _ = choose_segment(None, "ארגׇמן ותכלת", threshold=0.5, allow_maqaf=False)
    assert segment.text == "ארגמן ותכלת"


def test_segment_character_rules():
    assert choose_segment(None, "עלילת־הדם הזאת", threshold=0.5, allow_maqaf=False) == (None, "maqaf")
    segment, _ = choose_segment(None, "עלילת־הדם הזאת", threshold=0.5, allow_maqaf=True)
    assert segment is not None
    assert choose_segment(None, "א", threshold=0.5, allow_maqaf=False) == (None, "too_few_letters")
    assert choose_segment(None, "שורה [בסוגריים]", threshold=0.5, allow_maqaf=False) == (None, "charset")
    assert choose_segment(None, "מספר 12345678 ארוך", threshold=0.5, allow_maqaf=False) == (None, "long_digit_run")
    assert choose_segment(None, "מילה " * 12, threshold=0.5, allow_maqaf=False) == (None, "too_long")
    segment, _ = choose_segment(None, "“כך” אמר — והלך…", threshold=0.5, allow_maqaf=False)
    assert segment is not None

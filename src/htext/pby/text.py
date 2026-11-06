"""Clean PBY works and cut them into corpus lines (S15a §7, steps 1-4).

``txt/`` and ``txt_stripped/`` are line-aligned, and an aligned pair of lines
has the same words in the same order. A line is therefore cut once, at word
boundaries, and each cut segment exists in both forms: pointed (from ``txt/``)
and plain (from ``txt_stripped/``). The niqqud split then picks one form per
segment.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Iterable, Sequence

from htext.hebrew import (
    MAQAF,
    NIQQUD_CHARSET,
    PLAIN_CHARSET,
    has_medial_final_form,
    has_other_marks,
    hebrew_letter_count,
    nfc,
    pointing_density,
    strip_marks,
)

MAX_LINE_CHARS = 55
DEFAULT_NIQQUD_THRESHOLD = 0.5
# Poetry keeps its verse lines; every other allowlisted genre is cut by
# sentence and packed to the target length profile.
VERSE_GENRES = frozenset({"poetry"})

FOOTNOTE_MARK = "↩"
FOOTER_MARKERS = ("benyehuda.org", "פרויקט בן־יהודה", "פרויקט בן-יהודה")
# A footnote block follows a run of at least this many blank lines.
FOOTNOTE_GAP = 3
_VARIATION_SELECTORS = re.compile("[︀-️]")
_ENTITY = re.compile(r"&[A-Za-z]+;|&#\d+;")
_URL = re.compile(r"https?:|www\.", re.IGNORECASE)
_LATIN = re.compile(r"[A-Za-z]")
_SPACES = re.compile(r"[\s  -   　]+")
_BIDI_AND_ZERO_WIDTH = re.compile("[​-‏‪-‮⁦-⁩﻿­]")
# A footnote reference: digits right after a Hebrew letter or point, or after
# punctuation that follows one ("הַחַיִים.1").
_FOOTNOTE_REFERENCE = re.compile(
    r"(?<=[\u05D0-\u05EA\u0591-\u05C7])([.,:;!?\"'”’׳״)]?)\d{1,3}(?=$|[\s.,:;!?)\]\"'׳״”’–—…])"
)
_LETTER_DIGIT = re.compile(r"[\u05D0-\u05EA\u0591-\u05C7][.,:;!?\"'”’׳״)]?\d")
_SENTENCE_END = re.compile(r"[.!?…][\"'”’״׳)]*$")
_LONG_DIGIT_RUN = re.compile(r"\d{7,}")


class AlignmentError(ValueError):
    """``txt/`` and ``txt_stripped/`` disagree on line count."""


@dataclass(frozen=True)
class SourceLine:
    index: int
    pointed: str
    plain: str


@dataclass(frozen=True)
class Segment:
    text: str
    subset: str  # "plain" or "niqqud"
    density: float
    plain_form: str


def body_line_range(lines: Sequence[str]) -> tuple[int, int] | None:
    """Return ``(start, end)`` of the work's body, or None when it cannot be found.

    Line 0 is the title. The body ends at the PBY credit footer, or at the
    footnote block before it. A footnote block starts after a run of blank
    lines and contains the ``↩`` back-links; multi-line footnotes have text
    lines without ``↩``, so the cut is at the blank run, not the first ``↩``.
    """

    end = len(lines)
    for index, line in enumerate(lines):
        if any(marker in line for marker in FOOTER_MARKERS):
            end = index
            break
    notes = [index for index in range(1, end) if FOOTNOTE_MARK in lines[index]]
    if notes:
        cut = None
        blanks = 0
        for index in range(notes[0] - 1, 0, -1):
            if lines[index].strip():
                if blanks >= FOOTNOTE_GAP:
                    cut = index + 1
                    break
                blanks = 0
            else:
                blanks += 1
        if cut is None:
            return None
        end = cut
    return (1, end)


def normalise(line: str, *, strip_references: bool) -> str:
    line = _VARIATION_SELECTORS.sub("", line)
    line = _BIDI_AND_ZERO_WIDTH.sub("", line)
    if strip_references:
        line = _FOOTNOTE_REFERENCE.sub(r"\1", line)
    return nfc(_SPACES.sub(" ", line).strip())


def source_lines(pointed_text: str, plain_text: str) -> list[SourceLine]:
    """Aligned, normalised body lines of one work (blank lines dropped)."""

    pointed = pointed_text.split("\n")
    plain = plain_text.split("\n")
    if len(pointed) != len(plain):
        raise AlignmentError(f"{len(pointed)} txt lines vs {len(plain)} txt_stripped lines")
    span = body_line_range(pointed)
    if span is None:
        raise AlignmentError("footnote block without a blank-line gap")
    has_notes = any(FOOTNOTE_MARK in line for line in pointed)
    out = []
    for index in range(*span):
        a = normalise(pointed[index], strip_references=has_notes)
        b = normalise(plain[index], strip_references=has_notes)
        if a or b:
            out.append(SourceLine(index, a, b))
    return out


def line_rejection(line: SourceLine) -> str | None:
    """Why a whole source line is unusable, or None."""

    text = line.pointed + " " + line.plain
    if FOOTNOTE_MARK in text:
        return "footnote"
    if _ENTITY.search(text) or "&" in text:
        return "entity"
    if _URL.search(text):
        return "url"
    if _LATIN.search(text):
        return "latin"
    # Digits glued to a letter in a work without footnotes are unexplained.
    if _LETTER_DIGIT.search(text):
        return "letter_digit"
    return None


def word_spans(words: Sequence[str], *, verse: bool, targets: "LengthSampler", max_chars: int = MAX_LINE_CHARS) -> list[tuple[int, int]]:
    """Cut one source line, given as plain words, into ``(start, end)`` word spans."""

    if not words:
        return []
    if verse:
        return _verse_spans(words, max_chars)
    return _pack(words, targets, max_chars)


def _joined_length(words: Sequence[str], start: int, end: int) -> int:
    return sum(len(word) for word in words[start:end]) + (end - start - 1)


# A sentence end closes a line once the line has this share of its target.
SENTENCE_BREAK_SHARE = 0.8
# A paragraph's last line shorter than this joins the line before it, when
# the two fit in ``max_chars``.
MIN_TAIL_CHARS = 12


def _pack(words: Sequence[str], targets: "LengthSampler", max_chars: int) -> list[tuple[int, int]]:
    """Pack prose words into lines whose lengths follow the target profile.

    Each line draws a target length. A line ends at the word boundary closest
    to its target, never past ``max_chars``, and ends early at a sentence end
    once it is long enough. A short last line joins the one before it.
    Greedy "fill up to the target" would bias every line short of its target.
    """

    spans = []
    start = 0
    target = min(targets.next(), max_chars)
    for index in range(len(words)):
        here = _joined_length(words, start, index + 1)
        last = index == len(words) - 1
        after = None if last else here + 1 + len(words[index + 1])
        if (
            last
            or after > max_chars
            or here >= target
            or (after > target and target - here <= after - target)
            or (_SENTENCE_END.search(words[index]) and here >= SENTENCE_BREAK_SHARE * target)
        ):
            spans.append((start, index + 1))
            start = index + 1
            target = min(targets.next(), max_chars)
    if len(spans) > 1 and _joined_length(words, *spans[-1]) < MIN_TAIL_CHARS:
        if _joined_length(words, spans[-2][0], spans[-1][1]) <= max_chars:
            spans[-2:] = [(spans[-2][0], spans[-1][1])]
    return spans


def _verse_spans(words: Sequence[str], max_chars: int) -> list[tuple[int, int]]:
    total = _joined_length(words, 0, len(words))
    parts = -(-total // max_chars)
    if parts <= 1:
        return [(0, len(words))]
    # Balanced split: break near each 1/parts of the verse's length.
    spans = []
    start = 0
    for part in range(1, parts):
        goal = total * part / parts
        best = None
        for stop in range(start + 1, len(words)):
            distance = abs(_joined_length(words, 0, stop) - goal)
            if best is None or distance < best[0]:
                best = (distance, stop)
        if best is None:
            break
        spans.append((start, best[1]))
        start = best[1]
    spans.append((start, len(words)))
    return spans


class LengthSampler:
    """Deterministic draws of target line lengths from a length histogram."""

    def __init__(self, lengths: Iterable[int], seed: int | str) -> None:
        self.population = sorted(lengths)
        if not self.population:
            raise ValueError("length profile is empty")
        self.rng = random.Random(seed)

    def next(self) -> int:
        return self.rng.choice(self.population)


def choose_segment(pointed: str | None, plain: str, *, threshold: float, allow_maqaf: bool) -> tuple[Segment | None, str | None]:
    """Apply the niqqud split and the character rules to one cut segment."""

    plain = strip_marks(plain)
    density = pointing_density(pointed) if pointed else 0.0
    if pointed and density >= threshold and not has_other_marks(pointed):
        segment = Segment(pointed, "niqqud", density, plain)
        charset = NIQQUD_CHARSET
    else:
        segment = Segment(plain, "plain", density, plain)
        charset = PLAIN_CHARSET
    if allow_maqaf:
        charset = charset | {MAQAF}
    text = segment.text
    if len(segment.plain_form) > MAX_LINE_CHARS:
        return None, "too_long"
    if hebrew_letter_count(text) < 2:
        return None, "too_few_letters"
    if any(char not in charset for char in text):
        return None, "maqaf" if MAQAF in text and not allow_maqaf else "charset"
    if has_medial_final_form(text):
        return None, "medial_final_form"
    if _LONG_DIGIT_RUN.search(text):
        return None, "long_digit_run"
    return segment, None

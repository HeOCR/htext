"""The word lexicon that filters OCR lines (plan decision 3).

The lexicon is built from transcription corpora only: lines that people typed,
never an OCR layer (``htext.release.lexicon_eligible``). An OCR line is kept
only when every word in it is in the lexicon, so OCR misreadings that make
non-words (``מדיבת`` for ``מדינת``) drop the line.

A line is also dropped when one of its words looks like an OCR confusion of a
far more common word (:meth:`Lexicon.suspects`): ``זבאי`` for ``זכאי``, ``באמור`` for
``כאמור``. Such misreadings are often real but rare words, so the lexicon alone
keeps them.

Words are compared in one normal form, the same for the lexicon and the
lines: niqqud removed, then punctuation stripped from both ends. A word joined
by a hyphen or maqaf is checked part by part. A part with fewer than two
Hebrew letters (a number, ``(א)``) is not checked, and neither is a Hebrew
numeral (``תשי"ט``), which :func:`is_hebrew_numeral` checks by rule.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from htext.hebrew import strip_marks

_EDGE = re.compile(r"^[^א-ת0-9]+|[^א-ת0-9]+$")
_JOINERS = re.compile(r"[-־–—/]")
_HEBREW = re.compile(r"[א-ת]")

_VALUES = {letter: value for letter, value in zip("אבגדהוזחטיכלמנסעפצקרשת", (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 200, 300, 400))}
_NUMERAL = re.compile(r'^(?P<letters>[א-ת]+)(?:["״](?P<last>[א-ת])|[\'׳])$')
_PREFIXES = "ובכלמהש"


def _numeral_value_ok(letters: str) -> bool:
    if not letters or any(letter not in _VALUES for letter in letters):
        return False
    # 15 and 16 are written ט"ו and ט"ז, never י"ה and י"ו.
    if letters.endswith(("יה", "יו")):
        return False
    body = letters[:-2] if letters.endswith(("טו", "טז")) else letters
    values = [_VALUES[letter] for letter in body]
    if any(a < b for a, b in zip(values, values[1:])):
        return False
    if body != letters and any(value < 100 for value in values):
        return False
    return values.count(400) <= 2 and sum(10 <= v < 100 for v in values) <= 1 and sum(v < 10 for v in values) <= 1


def is_hebrew_numeral(token: str) -> bool:
    """Whether a token is a Hebrew numeral (a year or a number), with up to two prefix letters.

    Without its prefix the numeral runs from high values to low, with at most one
    tens and one units letter (``תש"ט``, ``תשי"א``, ``ה'``, ``בתשל"ג``, ``תשט"ו``). A numeral is
    a rule, not a word, so it needs no lexicon entry.
    """

    match = _NUMERAL.match(strip_marks(token).strip("()[],.:;"))
    if not match:
        return False
    letters = match.group("letters") + (match.group("last") or "")
    for cut in range(0, 3):
        if cut and (len(letters) <= cut or letters[cut - 1] not in _PREFIXES):
            break
        if _numeral_value_ok(letters[cut:]):
            return True
    return False


# A word must occur this many times in the transcription corpora; a single
# occurrence may be a typo there.
DEFAULT_MIN_COUNT = 2


def word_keys(token: str) -> list[str]:
    """The normal forms of one whitespace token that the lexicon must hold."""

    keys = []
    for part in _JOINERS.split(strip_marks(token)):
        if is_hebrew_numeral(part):
            continue
        key = _EDGE.sub("", part)
        if len(_HEBREW.findall(key)) >= 2:
            keys.append(key)
    return keys


# OCR confusions seen in the Knesset laws' eye check (כ read as ב, נ as ב, ס as מ, נ as ג), ס for פ found in the
# build-3 review of rescued words (לסי for לפי), and other near-identical letters in the period's typefaces.
CONFUSIONS = (
    ("ב", "כ"), ("ב", "נ"), ("ס", "מ"), ("ג", "נ"), ("ד", "ר"), ("ה", "ח"), ("ו", "ז"), ("ו", "י"), ("ם", "ס"), ("ס", "פ"),
)
# A word is suspect when one confusion turns it into a word this many times more common.
SUSPECT_RATIO = 20
# ... and that word occurs at least this often.
SUSPECT_MIN_VARIANT = 50
# Two-corpus rule (heocr-lead, 2026-11-18): the variant must also be this many times more common in the corpus being
# built. A legal word PBY rarely uses (ברשומות beside ברשימות) is common in the laws and is not suspect; a misreading
# (זבאי beside זכאי) stays rare there. The corpus' counts only veto a suspicion: a word still needs the lexicon.
LOCAL_RATIO = 10
_SWAPS: dict[str, tuple[str, ...]] = {}
for _a, _b in CONFUSIONS:
    _SWAPS[_a] = _SWAPS.get(_a, ()) + (_b,)
    _SWAPS[_b] = _SWAPS.get(_b, ()) + (_a,)


@dataclass
class Lexicon:
    words: set[str]
    min_count: int
    sources: list[dict] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_lines(cls, lines: Iterable[str], *, min_count: int = DEFAULT_MIN_COUNT) -> "Lexicon":
        counts: Counter = Counter()
        for line in lines:
            for token in line.split():
                counts.update(word_keys(token))
        kept = {word: count for word, count in counts.items() if count >= min_count}
        return cls(set(kept), min_count, counts=kept)

    @classmethod
    def from_files(cls, paths: Iterable[Path], *, min_count: int = DEFAULT_MIN_COUNT) -> "Lexicon":
        counts: Counter = Counter()
        sources = []
        for path in paths:
            digest = hashlib.sha256()
            lines = 0
            with path.open("rb") as handle:
                for raw in handle:
                    digest.update(raw)
                    lines += 1
                    for token in raw.decode("utf-8").split():
                        counts.update(word_keys(token))
            sources.append({"file": path.name, "sha256": digest.hexdigest(), "lines": lines})
        if not sources:
            raise ValueError("the lexicon needs at least one transcription corpus")
        kept = {word: count for word, count in counts.items() if count >= min_count}
        return cls(set(kept), min_count, sources, kept)

    def unknown(self, line: str) -> list[str]:
        """Words of ``line`` that the lexicon lacks."""

        return [
            key
            for token in line.split()
            for key in word_keys(token)
            if key not in self.words
        ]

    def is_word(self, token: str) -> bool:
        """Whether every part of ``token`` is in the lexicon (and it has at least one)."""

        keys = word_keys(token)
        return bool(keys) and all(key in self.words for key in keys)

    def look_alikes(self, line: str, local: dict[str, int] | None = None) -> list[tuple[str, str, bool]]:
        """Words of ``line`` that look like an OCR confusion of a far more common word: ``(word, variant, rescued)``.

        A word is a look-alike when one confusion turns it into a word at least :data:`SUSPECT_RATIO` times more
        common in the lexicon (and seen :data:`SUSPECT_MIN_VARIANT` times). With ``local`` (word counts of the corpus
        being built), it is ``rescued`` unless the variant is also :data:`LOCAL_RATIO` times more common there.
        """

        out = []
        for token in line.split():
            for key in word_keys(token):
                count = self.counts.get(key, 0)
                for index, letter in enumerate(key):
                    for swap in _SWAPS.get(letter, ()):
                        variant = key[:index] + swap + key[index + 1 :]
                        other = self.counts.get(variant, 0)
                        if other >= SUSPECT_MIN_VARIANT and other >= SUSPECT_RATIO * count:
                            rescued = local is not None and local.get(variant, 0) < LOCAL_RATIO * local.get(key, 0)
                            out.append((key, variant, rescued))
        return out

    def suspects(self, line: str, local: dict[str, int] | None = None) -> list[tuple[str, str]]:
        """Look-alikes of ``line`` that are not rescued: ``זבאי`` beside ``זכאי`` is suspect; ``בזאת`` beside ``כזאת``
        is not, because both are common."""

        return [(word, variant) for word, variant, rescued in self.look_alikes(line, local) if not rescued]

    def card(self) -> dict:
        return {
            "sources": self.sources,
            "min_count": self.min_count,
            "words": len(self.words),
            "suspect_rule": {
                "confusions": ["/".join(pair) for pair in CONFUSIONS],
                "ratio": SUSPECT_RATIO,
                "min_variant_count": SUSPECT_MIN_VARIANT,
                "corpus_ratio": LOCAL_RATIO,
            },
        }

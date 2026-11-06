"""Hebrew character classes shared by the corpus builders.

The sets follow the packaged ``hocrsyngen`` corpora: the S10b base set
(``tests/test_training_text_corpus.py``) and the S13b typographic marks
(``scripts/typographic_text_corpus_stats.py``). Latin letters are part of the
S10b set but not of this one: PBY lines with Latin fragments are dropped.
"""

from __future__ import annotations

import re
import unicodedata

HEBREW_LETTERS = frozenset(chr(code) for code in range(0x05D0, 0x05EB))
FINAL_FORMS = frozenset("ךםןףץ")
DIGITS = frozenset("0123456789")
# S10b niqqud: vowel points U+05B0-U+05BC (dagesh included), shin and sin dots,
# and qamats qatan.
NIQQUD = frozenset(chr(code) for code in range(0x05B0, 0x05BD)) | {"ׁ", "ׂ", "ׇ"}
# Marks outside the S10b set: cantillation, meteg, rafe, upper and lower dots.
OTHER_MARKS = frozenset(chr(code) for code in range(0x0591, 0x05B0)) | {"ֽ", "ֿ", "ׄ", "ׅ"}
# Hebrew punctuation outside every packaged corpus: paseq, sof pasuq, nun hafukha.
OTHER_HEBREW_PUNCTUATION = frozenset({"׀", "׃", "׆"})
MAQAF = "־"
# S10b punctuation (Latin letters left out).
S10B_PUNCTUATION = frozenset(" .,:;!?'\"()-/%+") | {"₪"}
# S13b typographic marks: em and en dash, geresh, gershayim, typographic
# quotes and the ellipsis.
TYPOGRAPHIC_MARKS = frozenset("—–׳״“”„‘’…")
PLAIN_CHARSET = HEBREW_LETTERS | DIGITS | S10B_PUNCTUATION | TYPOGRAPHIC_MARKS
NIQQUD_CHARSET = PLAIN_CHARSET | NIQQUD

_ALL_MARKS = NIQQUD | OTHER_MARKS


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def strip_marks(text: str) -> str:
    """Remove every Hebrew point and cantillation mark (maqaf and punctuation stay)."""

    return nfc("".join(char for char in unicodedata.normalize("NFD", text) if char not in _ALL_MARKS))


def pointing_density(text: str) -> float:
    """Share of Hebrew letters that carry at least one S10b niqqud mark."""

    letters = 0
    pointed = 0
    current_pointed = False
    for char in unicodedata.normalize("NFD", text):
        if char in HEBREW_LETTERS:
            if letters:
                pointed += current_pointed
            letters += 1
            current_pointed = False
        elif char in NIQQUD and letters:
            current_pointed = True
    if letters:
        pointed += current_pointed
    return pointed / letters if letters else 0.0


def has_other_marks(text: str) -> bool:
    decomposed = unicodedata.normalize("NFD", text)
    return any(char in OTHER_MARKS or char in OTHER_HEBREW_PUNCTUATION for char in decomposed)


def hebrew_letter_count(text: str) -> int:
    return sum(char in HEBREW_LETTERS for char in text)


def word_ngrams(line: str, size: int) -> set[tuple[str, ...]]:
    words = line.split()
    return {tuple(words[index : index + size]) for index in range(len(words) - size + 1)}


_MEDIAL_FINAL = re.compile("[ךםןףץ](?=[א-ת])")


def has_medial_final_form(text: str) -> bool:
    return bool(_MEDIAL_FINAL.search(strip_marks(text)))

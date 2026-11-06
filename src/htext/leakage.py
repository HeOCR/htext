"""Hash-only leakage fixtures for protected evaluation text.

A fixture records, for one protected text file in another repository, the
sha256 of every NFC line and of every word 3-gram, plus the file's own sha256
and the commit it was read at. No protected text is stored. This is the
format of the ``hocrsyngen`` S13a fixture
(``tests/fixtures/hocrgen_bidi_synthetic_corpus.hashes.json``); ``hocrgen``
and ``hocrsyngen`` evaluation text both reach this repository that way.

``htext`` fixtures also hash the niqqud-stripped form of each line and
3-gram (``stripped: true``), so a pointed corpus line is compared with plain
evaluation text and the other way round.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from htext.hebrew import nfc, strip_marks, word_ngrams

NORMALIZATION = "NFC lines; word 3-grams are whitespace-split words joined by one space; sha256 of UTF-8"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _forms(line: str, *, stripped: bool) -> set[str]:
    line = nfc(line)
    return {line, strip_marks(line)} if stripped else {line}


def corpus_hashes(lines: Iterable[str], *, stripped: bool = True) -> dict[str, list[str]]:
    line_hashes: set[str] = set()
    gram_hashes: set[str] = set()
    for line in lines:
        for form in _forms(line, stripped=stripped):
            line_hashes.add(sha256_text(form))
            gram_hashes.update(sha256_text(" ".join(gram)) for gram in word_ngrams(form, 3))
    return {"line_sha256": sorted(line_hashes), "word3_sha256": sorted(gram_hashes)}


def fixture_for_file(path: Path, *, repository: str, source_path: str, commit: str) -> dict[str, Any]:
    raw = path.read_bytes()
    lines = [line for line in raw.decode("utf-8").splitlines() if line.strip()]
    return {
        "source": {
            "repository": repository,
            "path": source_path,
            "commit": commit,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "lines": len(lines),
        },
        "normalization": NORMALIZATION,
        "stripped": True,
        **corpus_hashes(lines),
    }


@dataclass
class Protected:
    """The union of every loaded fixture, for fast membership checks."""

    sources: list[dict[str, Any]] = field(default_factory=list)
    lines: set[str] = field(default_factory=set)
    grams: set[str] = field(default_factory=set)

    @classmethod
    def load(cls, paths: Iterable[Path]) -> "Protected":
        protected = cls()
        for path in paths:
            document = json.loads(path.read_text(encoding="utf-8"))
            fixtures = document["fixtures"] if "fixtures" in document else [document]
            for fixture in fixtures:
                if fixture.get("normalization") != NORMALIZATION:
                    raise ValueError(f"{path}: unexpected normalization {fixture.get('normalization')!r}")
                protected.sources.append({**fixture["source"], "stripped": bool(fixture.get("stripped"))})
                protected.lines.update(fixture["line_sha256"])
                protected.grams.update(fixture["word3_sha256"])
        return protected

    def leak(self, *forms: str) -> str | None:
        """``"line"`` or ``"word3"`` when any form overlaps protected text, else None."""

        for form in forms:
            if sha256_text(form) in self.lines:
                return "line"
        for form in forms:
            for gram in word_ngrams(form, 3):
                if sha256_text(" ".join(gram)) in self.grams:
                    return "word3"
        return None

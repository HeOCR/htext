"""Read ``pseudocatalogue.csv`` from the PBY dump."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

# The catalogue writes Q0 where a creator has no Wikidata item.
PLACEHOLDER_QIDS = frozenset({"Q0"})
GENRE_PREFIX = "Translation missing: he."


@dataclass(frozen=True)
class Creator:
    name: str
    qid: str | None


@dataclass(frozen=True)
class Work:
    work_id: int
    path: str
    title: str
    genre: str
    authors: tuple[Creator, ...]
    translators: tuple[Creator, ...]
    original_language: str | None
    source_edition: str | None
    # True when a creator column's names and Wikidata URIs do not pair up one
    # to one, so no creator in that column can be given a QID.
    uri_misaligned: bool = False

    @property
    def stem(self) -> str:
        return self.path.lstrip("/")


def _split(value: str | None) -> list[str]:
    return [" ".join(part.split()) for part in (value or "").split(";") if part.strip()]


def _qid(uri: str) -> str | None:
    qid = uri.rstrip("/").rsplit("/", 1)[-1]
    return None if qid in PLACEHOLDER_QIDS or not qid.startswith("Q") else qid


def _creators(names_value: str | None, uris_value: str | None) -> tuple[tuple[Creator, ...], bool]:
    names = _split(names_value)
    uris = _split(uris_value)
    if uris and len(uris) != len(names):
        return tuple(Creator(name, None) for name in names), True
    qids = [_qid(uri) for uri in uris] if uris else [None] * len(names)
    return tuple(Creator(name, qid) for name, qid in zip(names, qids)), False


def read_catalogue(path: Path) -> list[Work]:
    works: list[Work] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            authors, authors_misaligned = _creators(row["authors"], row["author_uris"])
            translators, translators_misaligned = _creators(row["translators"], row["translator_uris"])
            genre = row["genre"] or ""
            works.append(
                Work(
                    work_id=int(row["ID"]),
                    path=row["path"],
                    title=row["title"],
                    genre=genre[len(GENRE_PREFIX) :] if genre.startswith(GENRE_PREFIX) else genre,
                    authors=authors,
                    translators=translators,
                    original_language=row["original_language"] or None,
                    source_edition=(row["source_edition"] or "").strip() or None,
                    uri_misaligned=authors_misaligned or translators_misaligned,
                )
            )
    ids = [work.work_id for work in works]
    if len(set(ids)) != len(ids):
        raise ValueError("pseudocatalogue.csv has duplicate work ids")
    return sorted(works, key=lambda work: work.work_id)

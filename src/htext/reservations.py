"""Whole-unit eval reservations.

HeOCR's evaluation reserves whole source units: PBY works, Reshumot booklets,
Knesset sittings and protocols, Wikisource Indexes and others. A reserved unit
contributes no line to any htext build, in any release, whatever its rights.
Line and word 3-gram leakage checks catch the printed passages; the reservation
removes the rest of the unit too.

Two file schemas are read:

- ``heocr_eval_reservations.v1``: eval's own file
  (``reservations/eval_reservations_v1.json`` in heocr-restricted-eval). It is
  the source of truth, and htext reads it as it is.
- ``htext_reservations.v1``: a minimal form for other reservations,
  ``{"schema", "set", "registry", "works": [{"source", "work_id"}]}``.

Every reserved id is normalised to a ``(source, id)`` pair:

| Field in eval's file | Source | Id |
| --- | --- | --- |
| ``pby_work_ids`` | ``pby`` | the work id |
| ``reshumot_booklets`` ``{series: [n]}`` | ``reshumot`` | ``<series>_<n>`` |
| ``reshumot_born_digital_booklets`` | ``reshumot`` | the booklet id, ``<series>_<n>`` |
| ``hash_source_ids`` | ``hash`` | the HASH unit id (htext builds no HASH text) |
| ``unit_ids`` / ``item_ids`` ``prefix:rest`` | ``prefix`` | ``rest``, cut to its unit |
| ``wikisource_indexes`` | ``wikisource`` | the Index, ``ws_index_<n>`` |
| ``ia_identifiers`` | ``ia`` | the Internet Archive identifier |
| ``sefaria_works`` | ``sefaria`` | the Sefaria work title |
| ``books`` | ``wikisource`` for ``ws_index_<n>``, else ``ia`` | the book's unit |
| ``strata`` ``{name: [id]}`` | as ``books`` | each id |
| ``reserves`` (v4) | as ``books`` | each reserve book |
| ``conditional`` ``{id: note}`` (v4) | as ``books`` | each id; the note is metadata |
| ``withdrawn_v1_pby_work_ids_still_reserved`` (v6) | ``pby`` | the work id |
| ``maps`` ``{pby id: note}`` (v7) | ``pby`` | each key; the note names the reserved book it is an edition of |
| ``tanakh_ranges`` (v5) | ``tanakh_range`` | ``Book.c.v-Book.c.v``, OSIS refs |
| ``tanakh_parallels_reserved`` ``{range: "range (note)"}`` (v5) | ``tanakh_range`` | each value's range |
| ``documents`` ``[{canonical_document_id, document_id, ...}]`` (v8) | the id's ``prefix`` | ``rest`` of each id, whole document |

``wikisource_he_proofread:<index>`` and ``wikisource_indexes`` name the same
Hebrew Wikisource Indexes, so both are read as ``wikisource``. Schema
``heocr_eval_reservations.v3`` (P-hist eval hold-out, 2026-11-18) adds the
last five fields, and ``heocr_eval_reservations.v4`` (the standard-square
top-up) adds ``reserves`` and ``conditional``. Schemas ``v5`` to ``v7`` (the
pointed-print test set and its swaps, 2026-11-19) add verse ranges, withdrawn
works that stay reserved, and PBY editions of reserved books (``maps``).
``Reservations.verse_reserved`` tells a builder whether a verse falls in a
reserved range. Their rule holds out every other edition, scan or text of a
reserved work too. A builder matches its own ids; other editions are listed
in a reviewed ``htext_reservations.v1`` file.

A Reshumot booklet is one document whether eval uses its scan or its born-digital
PDF, so ``reshumot_scanned:<booklet>`` is read as ``reshumot``.

Item ids are cut to the unit they belong to, because units are held out whole:
a Wikisource page ``ws_index_<n>__p0003`` (or a line on it, ``...#L005``) reserves
Index ``ws_index_<n>``, and a
line ``nli_<record>__c0014#L017`` reserves the record ``nli_<record>``.

The loader fails closed: a field it does not know raises, so a new kind of eval
set is never silently ignored. Reservation files may live outside this
repository. A card records each set's name, the file's sha256 and per-source
counts, never the ids.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "htext_reservations.v1"
EVAL_SCHEMA = "heocr_eval_reservations.v1"
EVAL_SCHEMAS = frozenset({EVAL_SCHEMA, *(f"heocr_eval_reservations.v{n}" for n in (3, 4, 5, 6, 7, 8))})

# Fields of an eval set that carry no ids.
_EVAL_METADATA = {
    "set", "registration", "fixture", "splits", "labels", "note", "source_pages", "pby_work_ids_basis", "rule",
    # v5-v7: scope and binding notes, pointers into other teams' files, and the per-page htext status.
    "scope", "binds", "s16c_sampling_corpus_files", "fonts", "htext_status", "pby_all_editions",
}
# Item ids are cut to their unit: a Wikisource page to its Index, an aligned line to its record.
_UNIT_OF_ITEM = (
    re.compile(r"^(ws_index_\d+)__p\d+(?:#L\d+)?$"),
    re.compile(r"^(nli_\d+)__c\d+(?:#L\d+)?$"),
)


def _unit(rest: str) -> str:
    for pattern in _UNIT_OF_ITEM:
        match = pattern.match(rest)
        if match:
            return match.group(1)
    return rest


# Prefixes that name the same documents captured another way.
_SAME_DOCUMENTS = {"reshumot_scanned": "reshumot", "wikisource_he_proofread": "wikisource"}
_WIKISOURCE_INDEX = re.compile(r"^ws_index_\d+$")


def _book_unit(value: object, where: str) -> tuple[str, str]:
    """A P-hist book: a Wikisource Index, or else an Internet Archive identifier."""

    unit = str(value).strip()
    if not unit or ":" in unit:
        raise ValueError(f"{where}: unexpected book id {value!r}")
    return ("wikisource", unit) if _WIKISOURCE_INDEX.match(unit) else ("ia", unit)


_REF = re.compile(r"^([1-3]?[A-Z][A-Za-z]*)\.(\d+)\.(\d+)$")


def _verse(ref: str) -> tuple[str, int, int] | None:
    match = _REF.match(str(ref).strip())
    return (match.group(1), int(match.group(2)), int(match.group(3))) if match else None


def _verse_range(value: object, where: str) -> tuple[str, str]:
    """``Book.c.v-Book.c.v`` in one book; a trailing note in parentheses is dropped."""

    text = str(value).split("(")[0].strip()
    first, sep, last = text.partition("-")
    start, end = _verse(first), _verse(last)
    if not sep or start is None or end is None or start[0] != end[0] or start[1:] > end[1:]:
        raise ValueError(f"{where}: expected a verse range Book.c.v-Book.c.v in one book, found {value!r}")
    return ("tanakh_range", f"{first.strip()}-{last.strip()}")


def _prefixed(value: str, where: str) -> tuple[str, str]:
    source, sep, rest = str(value).partition(":")
    if not sep or not source or not rest:
        raise ValueError(f"{where}: expected 'source:id', found {value!r}")
    return _SAME_DOCUMENTS.get(source, source), _unit(rest)


def _eval_set_ids(row: dict[str, Any], where: str) -> list[tuple[str, str]]:
    ids: list[tuple[str, str]] = []
    for key, value in row.items():
        if key in _EVAL_METADATA:
            continue
        if key in ("pby_work_ids", "withdrawn_v1_pby_work_ids_still_reserved"):
            ids += [("pby", str(work_id)) for work_id in value]
        elif key == "maps":
            for work_id in value:
                if not str(work_id).isdigit():
                    raise ValueError(f"{where}: maps keys must be PBY work ids, found {work_id!r}")
                ids.append(("pby", str(work_id)))
        elif key == "tanakh_ranges":
            ids += [_verse_range(item, where) for item in value]
        elif key == "tanakh_parallels_reserved":
            ids += [_verse_range(item, where) for item in value.values()]
        elif key == "reshumot_booklets":
            ids += [("reshumot", f"{series}_{number}") for series, numbers in value.items() for number in numbers]
        elif key == "reshumot_born_digital_booklets":
            ids += [("reshumot", str(booklet)) for booklet in value]
        elif key == "hash_source_ids":
            # HASH handwriting units; htext builds no HASH text, but they are read so the reservation stays complete.
            ids += [("hash", str(unit)) for unit in value]
        elif key in ("unit_ids", "item_ids"):
            ids += [_prefixed(item, where) for item in value]
        elif key == "documents":
            # v8 (PH1, 2026-11-25): source documents of test units are out of every corpus, matched on either id.
            for document in value:
                found = [document.get(name) for name in ("canonical_document_id", "document_id") if document.get(name)]
                if not found:
                    raise ValueError(f"{where}: a reserved document needs canonical_document_id or document_id: {document!r}")
                for doc_id in found:
                    source, sep, rest = str(doc_id).partition(":")
                    if not sep or not source or not rest:
                        raise ValueError(f"{where}: expected 'source:id', found {doc_id!r}")
                    ids.append((_SAME_DOCUMENTS.get(source, source), rest))
        elif key == "wikisource_indexes":
            for index in value:
                if not _WIKISOURCE_INDEX.match(str(index)):
                    raise ValueError(f"{where}: expected ws_index_<n>, found {index!r}")
                ids.append(("wikisource", str(index)))
        elif key == "ia_identifiers":
            ids += [("ia", str(identifier)) for identifier in value]
        elif key == "sefaria_works":
            ids += [("sefaria", str(title)) for title in value]
        elif key in ("books", "reserves"):
            ids += [_book_unit(book, where) for book in value]
        elif key == "conditional":
            # {book id: condition}; the book is reserved whatever the condition says about scoring.
            ids += [_book_unit(book, where) for book in value]
        elif key == "strata":
            ids += [_book_unit(book, where) for books in value.values() for book in books]
        else:
            raise ValueError(f"{where}: unknown reservation field {key!r}; teach htext.reservations to read it")
    return ids


@dataclass
class Reservations:
    files: list[dict[str, Any]] = field(default_factory=list)
    units: dict[str, set[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, paths: Iterable[Path]) -> "Reservations":
        reservations = cls()
        for path in paths:
            raw = path.read_bytes()
            document = json.loads(raw.decode("utf-8"))
            schema = document.get("schema")
            if schema in EVAL_SCHEMAS:
                sets = document.get("reservations")
                if not sets:
                    raise ValueError(f"{path}: no reservations")
                parsed = []
                for number, row in enumerate(sets):
                    if not row.get("set"):
                        raise ValueError(f"{path}: reservation {number} has no set name")
                    parsed.append((row["set"], _eval_set_ids(row, f"{path}: {row['set']}")))
            elif schema == SCHEMA:
                for key in ("set", "registry", "works"):
                    if not document.get(key):
                        raise ValueError(f"{path}: missing {key!r}")
                ids = []
                for row in document["works"]:
                    source, work_id = row.get("source"), row.get("work_id")
                    if not source or work_id in (None, ""):
                        raise ValueError(f"{path}: a reservation needs a source and a work_id: {row!r}")
                    ids.append((str(source), str(work_id)))
                parsed = [(document["set"], ids)]
            else:
                raise ValueError(f"{path}: expected schema {' or '.join(sorted(EVAL_SCHEMAS | {SCHEMA}))}, found {schema!r}")
            for set_name, ids in parsed:
                if not ids:
                    raise ValueError(f"{path}: set {set_name!r} reserves nothing")
                for source, unit in ids:
                    reservations.units.setdefault(source, set()).add(unit)
                counts = Counter(source for source, _ in set(ids))
                reservations.files.append(
                    {
                        "schema": schema,
                        "set": set_name,
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "units": dict(sorted(counts.items())),
                    }
                )
        return reservations

    def reserved(self, source: str, unit: object) -> bool:
        return str(unit) in self.units.get(source, ())

    def verse_reserved(self, ref: object) -> bool:
        """Whether an OSIS verse ``Book.c.v`` falls in a reserved verse range."""
        verse = _verse(str(ref))
        if verse is None:
            raise ValueError(f"expected a verse Book.c.v, found {ref!r}")
        for item in self.units.get("tanakh_range", ()):
            first, _, last = item.partition("-")
            start, end = _verse(first), _verse(last)
            if verse[0] == start[0] and start[1:] <= verse[1:] <= end[1:]:
                return True
        return False

    def count(self, source: str) -> int:
        return len(self.units.get(source, ()))

    def card(self) -> list[dict[str, Any]]:
        """What a corpus card records: each set's name, the file sha256 and counts, not the ids."""
        return list(self.files)

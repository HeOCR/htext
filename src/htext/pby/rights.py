"""Per-work rights records (``pby_rights_index.v1``).

This is the S15a plan's reading of the law, not legal advice:

- Israel (Copyright Act 2007): life plus 70 years to the end of the calendar
  year. A work is public domain on 1 January of ``as_of`` when every author and
  every translator died in ``as_of - 71`` or earlier (decision 4 of ADR 0007).
- US: publication before ``as_of - 95``. The year of the edition PBY
  transcribed is an upper bound on first publication, so a pre-cutoff edition
  proves pre-cutoff publication. Anything else is ``"unknown"``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from htext.pby import PBY_DUMP_COMMIT
from htext.pby.catalogue import Creator, Work

RIGHTS_SCHEMA = "pby_rights_index.v1"
ANONYMOUS_NAMES = frozenset({"אלמוני/ת"})
PBY_BASIS = f"public_domain_dump LICENSE @{PBY_DUMP_COMMIT}"

_GEMATRIA = {
    **dict(zip("אבגדהוזחטי", range(1, 11))),
    **dict(zip("כלמנסעפצ", range(20, 100, 10))),
    **dict(zip("קרשת", range(100, 500, 100))),
    **dict(zip("ךםןףץ", (20, 40, 50, 80, 90))),
}
_GERSHAYIM = "\"״”“"
_GERESH = "'׳’"
# A Hebrew year in the 5500-5799 range (1740-2039) written without its
# thousands (תרנ"ג = 653 = 5653), optionally with the ה' thousands prefix.
# Values below 500 are not read as years: ת"א is the common abbreviation of
# Tel Aviv, and ת"ל and ת"ח are abbreviations too.
_HEBREW_YEAR = re.compile(
    rf"(?<![א-ת])(?:ה[{_GERESH}]\s?)?(ת[א-ת]{{0,2}}[{_GERSHAYIM}][א-ת])(?![א-ת])"
)
_GREGORIAN_YEAR = re.compile(r"(?<!\d)(1[0-9]{3}|20[0-9]{2})(?!\d)")
# No PBY source edition predates printing; an earlier four-digit number is a
# page, issue or volume number.
MIN_GREGORIAN_YEAR = 1450
# A number right after a page, volume, issue or serial marker (or after a list
# of numbers that follows one, as in "גליונות 13, 1262") is not a year.
_NUMBER_MARKER = re.compile(
    r"(?:עמ['׳’]?|עמוד(?:ים)?|כרך|כרכים|מס['׳’]|מספר|גל['׳’]|גליון|גיליון|גליונות|גילונות|גיליונות|"
    r"חוברת|חוברות|דף|דפים|סימן|סימנים|pp?\.|vol\.?|no\.?|nr\.?)"
    r"\s*(?:\d+\s*[,–—-]\s*)*$",
    re.IGNORECASE,
)


def gregorian_years(text: str) -> list[int]:
    """Four-digit years in ``text``, skipping pre-1450 numbers and marked page, volume or issue numbers."""

    years = []
    for match in _GREGORIAN_YEAR.finditer(text):
        year = int(match.group(1))
        if year < MIN_GREGORIAN_YEAR or _NUMBER_MARKER.search(text[max(0, match.start() - 40) : match.start()]):
            continue
        years.append(year)
    return years


def _gematria(letters: str) -> int | None:
    values = [_GEMATRIA[char] for char in letters]
    # Letters are written from the largest value down (ט"ו and ט"ז included).
    if any(later > earlier for earlier, later in zip(values, values[1:])) and letters[-2:] not in ("טו", "טז"):
        return None
    return sum(values)


def hebrew_years(text: str) -> list[int]:
    """Gregorian years for each Hebrew year in ``text`` (the later of the two it spans)."""

    years = []
    for match in _HEBREW_YEAR.finditer(text):
        value = _gematria("".join(char for char in match.group(1) if char not in _GERSHAYIM))
        if value is not None and 500 <= value <= 799:
            years.append(5000 + value - 3760)
    return years


def source_edition_year(note: str | None, *, max_year: int) -> int | None:
    """The latest year a ``source_edition`` note mentions, or None.

    The latest year is used because it can only make the edition look more
    recent, which keeps ``pd_us`` conservative.
    """

    if not note:
        return None
    years = gregorian_years(note) + hebrew_years(note)
    years = [year for year in years if year <= max_year]
    return max(years) if years else None


@dataclass(frozen=True)
class CreatorRecord:
    qid: str
    death_year: int | None
    precision: str | None
    revision: int | None


class Creators:
    """The pinned ``creators.json``: Wikidata rows by QID, manual rows by name."""

    def __init__(self, document: dict[str, Any]) -> None:
        if document.get("schema") != "pby_creators.v1":
            raise ValueError("creators.json must have schema pby_creators.v1")
        self.document = document
        self.by_qid = {
            row["qid"]: CreatorRecord(row["qid"], row.get("death_year"), row.get("death_year_precision"), row.get("wikidata_revision"))
            for row in document["creators"]
        }
        # Manual rows resolve creators the catalogue gives no QID. Each needs a
        # death year and a citable source.
        self.manual = {}
        for row in document.get("manual", []):
            if not row.get("source") or not isinstance(row.get("death_year"), int):
                raise ValueError(f"manual creator row needs death_year and source: {row}")
            self.manual[row["name"]] = row

    @classmethod
    def load(cls, path: Path) -> "Creators":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def resolve(self, creator: Creator) -> dict[str, Any]:
        if creator.qid and creator.qid in self.by_qid:
            record = self.by_qid[creator.qid]
            source = None
            if record.death_year is not None:
                source = f"wikidata:{record.qid}@{record.revision}"
                if record.precision not in ("year", "month", "day"):
                    source += f" (precision {record.precision}; latest year used)"
            return {"name": creator.name, "wikidata_qid": creator.qid, "death_year": record.death_year, "death_year_source": source}
        if creator.name in self.manual:
            row = self.manual[creator.name]
            return {
                "name": creator.name,
                "wikidata_qid": creator.qid,
                "death_year": row["death_year"],
                "death_year_source": f"manual:{row['source']}",
            }
        return {"name": creator.name, "wikidata_qid": creator.qid, "death_year": None, "death_year_source": None}


def israel_status(creators: list[dict[str, Any]], names: list[str], *, as_of: int) -> tuple[bool, str]:
    cutoff = as_of - 71
    if any(row["death_year"] is not None and row["death_year"] > cutoff for row in creators):
        return False, "creator_in_term"
    if any(name in ANONYMOUS_NAMES for name in names) or not names:
        return False, "anonymous_unresolved"
    if any(row["death_year"] is None for row in creators):
        return False, "creator_death_year_unknown"
    return True, f"all_creators_died_by:{cutoff}"


def us_status(
    *,
    first_publication_year: int | None,
    edition_year: int | None,
    creators: list[dict[str, Any]],
    as_of: int,
) -> tuple[bool | str, str]:
    cutoff = as_of - 95
    known = first_publication_year if first_publication_year is not None else edition_year
    if known is not None and known < cutoff:
        return True, f"published_before:{cutoff}"
    if first_publication_year is not None:
        deaths = [row["death_year"] for row in creators]
        if deaths and all(year is not None and year < 1946 for year in deaths):
            return "unknown", "uraa_candidate"
        return False, "published_in_term"
    return "unknown", "unknown"


def rights_record(work: Work, creators: Creators, *, as_of: int) -> dict[str, Any]:
    authors = [creators.resolve(creator) for creator in work.authors]
    translators = [creators.resolve(creator) for creator in work.translators]
    everyone = authors + translators
    names = [creator.name for creator in (*work.authors, *work.translators)]
    pd_israel, pd_israel_basis = israel_status(everyone, names, as_of=as_of)
    edition_year = source_edition_year(work.source_edition, max_year=as_of)
    first_publication_year = None  # no reviewed source yet (S15a §2)
    pd_us, pd_us_basis = us_status(
        first_publication_year=first_publication_year, edition_year=edition_year, creators=everyone, as_of=as_of
    )
    return {
        "pby_work_id": work.work_id,
        "pby_path": work.path,
        "pby_dump_commit": PBY_DUMP_COMMIT,
        "title": work.title,
        "genre": work.genre,
        "authors": authors,
        "translators": translators,
        "original_language": work.original_language,
        "source_edition": work.source_edition,
        "source_edition_year": edition_year,
        "first_publication_year": first_publication_year,
        "first_publication_year_source": None,
        "pd_israel": pd_israel,
        "pd_israel_basis": pd_israel_basis,
        "pd_us": pd_us,
        "pd_us_basis": pd_us_basis,
        "pby_public_domain": True,
        "pby_basis": PBY_BASIS,
        "as_of": as_of,
    }

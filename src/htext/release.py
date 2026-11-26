"""The three htext releases, the licence gate, and the per-entry release fields.

heocr-engine decision 0022 (2026-11-18): htext ships one release per licence.

- ``cc0``: public-domain text, CC0 text, and texts that section 6 of the Israeli
  Copyright Act 2007 leaves unprotected (laws, regulations, Knesset protocols).
- ``by``: text under attribution-only terms (CC BY).
- ``by-sa``: text under CC BY-SA.

NC and ND text, and text whose licence is unknown, are in no release. The gate
matches the source's licence label exactly and fails closed: a label that is not
listed here is refused until a decision names it.

No line crosses releases. Every corpus writer builds for one release and passes
each entry through :class:`ReleaseGuard`, which refuses an entry of any other
release.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

RELEASES = ("cc0", "by", "by-sa")
RELEASE_NAMES = {release: f"htext-{release}" for release in RELEASES}
RELEASE_LICENCES = {"cc0": "CC0-1.0", "by": "CC-BY-4.0", "by-sa": "CC-BY-SA-4.0"}

# The label every section 6 entry carries as its source licence.
S6_LABEL = "Israel Copyright Act 2007 s.6 (not protected)"

# Exact source labels, as each source writes them. Add a label only with the
# decision that admits it.
LICENCE_RELEASE: dict[str, str] = {
    # Public domain and public-domain dedications.
    "Public Domain": "cc0",  # PBY dump LICENSE; Sefaria's label
    "PD": "cc0",  # Sefaria's label, an alias of Public Domain; lead decision 2026-11-26
    "CC0": "cc0",  # Sefaria's label (hocrgen decision 2026-11-11, on #183)
    "CC0-1.0": "cc0",
    S6_LABEL: "cc0",
    # Attribution only.
    "CC-BY": "by",  # Sefaria's label
    "CC BY 4.0": "by",
    "CC-BY-4.0": "by",
    # Share-alike.
    "CC-BY-SA": "by-sa",  # Sefaria's label
    "CC BY-SA 3.0": "by-sa",  # older Wikimedia text; 3.0 allows adaptation under 4.0
    "CC BY-SA 4.0": "by-sa",
    "CC-BY-SA-4.0": "by-sa",
}

# Releases whose entries must carry a credit line.
CREDIT_REQUIRED = frozenset({"by", "by-sa"})

TEXT_QUALITIES = ("transcription", "ocr_layer")

_NC = re.compile(r"(?<![A-Za-z])NC(?![A-Za-z])|non[- ]?commercial", re.I)
_ND = re.compile(r"(?<![A-Za-z])ND(?![A-Za-z])|no[- ]?deriv", re.I)


class LicenceRefused(ValueError):
    """A licence label that no release takes."""

    def __init__(self, label: str, reason: str) -> None:
        super().__init__(f"licence {label!r} is refused: {reason}")
        self.label = label
        self.reason = reason


class ReleaseMismatch(ValueError):
    """An entry offered to a build of another release."""


def release_for_licence(label: str | None) -> str:
    """Return the release that takes ``label``, or raise :class:`LicenceRefused`."""
    if label is None or not label.strip():
        raise LicenceRefused(str(label), "unknown")
    if _NC.search(label):
        raise LicenceRefused(label, "non_commercial")
    if _ND.search(label):
        raise LicenceRefused(label, "no_derivatives")
    release = LICENCE_RELEASE.get(label)
    if release is None:
        raise LicenceRefused(label, "unlisted_label")
    return release


@dataclass(frozen=True)
class Credit:
    text: str
    url: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"text": self.text, "url": self.url}


def release_fields(
    *,
    source_licence: str,
    credit: Credit | None,
    text_quality: str = "transcription",
) -> dict[str, Any]:
    """The release fields every entry record carries, checked.

    ``htext_release`` is derived from ``source_licence``, never set by hand.
    """
    release = release_for_licence(source_licence)
    if text_quality not in TEXT_QUALITIES:
        raise ValueError(f"text_quality must be one of {TEXT_QUALITIES}, not {text_quality!r}")
    if release in CREDIT_REQUIRED and (credit is None or not credit.text.strip()):
        raise ValueError(f"a {RELEASE_NAMES[release]} entry needs a credit line")
    return {
        "source_licence": source_licence,
        "htext_release": release,
        "credit": credit.as_dict() if credit else None,
        "text_quality": text_quality,
    }


def lexicon_eligible(entry: Mapping[str, Any]) -> bool:
    """Whether an entry's lines may feed word lists, lexicons or dawgs.

    OCR text layers never do (heocr-lead, 2026-11-18): their errors would become
    vocabulary.
    """
    return entry.get("text_quality", "transcription") == "transcription"


@dataclass
class ReleaseGuard:
    """Admits only entries of one release; every corpus writer calls it."""

    release: str
    admitted: int = 0
    by_licence: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.release not in RELEASES:
            raise ValueError(f"unknown release {self.release!r}; expected one of {RELEASES}")

    def admit(self, entry: Mapping[str, Any]) -> Mapping[str, Any]:
        label = entry.get("source_licence")
        derived = release_for_licence(label)
        stated = entry.get("htext_release")
        if stated != derived:
            raise ReleaseMismatch(f"entry states release {stated!r} but its licence {label!r} belongs to {derived!r}")
        if derived != self.release:
            raise ReleaseMismatch(
                f"a {RELEASE_NAMES[derived]} entry ({label!r}) cannot enter a {RELEASE_NAMES[self.release]} build"
            )
        if derived in CREDIT_REQUIRED and not (entry.get("credit") or {}).get("text"):
            raise ReleaseMismatch(f"a {RELEASE_NAMES[derived]} entry needs a credit line")
        self.admitted += 1
        self.by_licence[label] = self.by_licence.get(label, 0) + 1
        return entry

    def admit_all(self, entries: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        return [self.admit(entry) for entry in entries]

    def summary(self) -> dict[str, Any]:
        """The card's record of what the guard admitted."""
        return {
            "htext_release": self.release,
            "release_name": RELEASE_NAMES[self.release],
            "release_licence": RELEASE_LICENCES[self.release],
            "entries_admitted": self.admitted,
            "source_licences": dict(sorted(self.by_licence.items())),
        }

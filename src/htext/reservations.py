"""Whole-work eval reservations.

HeOCR's evaluation reserves whole source works (for example the PBY works behind
a print-and-scan set). A reserved work contributes no line to any htext build,
in any release, whatever its rights: line and word 3-gram leakage checks catch
the printed passages, and the reservation removes the rest of the work too.

A reservation file is JSON:

    {
      "schema": "htext_reservations.v1",
      "set": "PS-v1",
      "registry": "HeOCR/heocr-restricted-eval#30",
      "reserved_by": "eval[claude/claude-code#shay-macbook-m4]@heocr/opensource",
      "works": [{"source": "pby", "work_id": "2218"}, ...]
    }

Work ids are strings, so every source can use its own ids. Reservation files may
live outside this repository (eval's restricted repository): a card then records
each file's sha256, set name and per-source counts, never the ids.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "htext_reservations.v1"


@dataclass
class Reservations:
    files: list[dict[str, Any]] = field(default_factory=list)
    works: dict[str, set[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, paths: Iterable[Path]) -> "Reservations":
        reservations = cls()
        for path in paths:
            raw = path.read_bytes()
            document = json.loads(raw.decode("utf-8"))
            if document.get("schema") != SCHEMA:
                raise ValueError(f"{path}: expected schema {SCHEMA!r}, found {document.get('schema')!r}")
            for key in ("set", "registry", "works"):
                if not document.get(key):
                    raise ValueError(f"{path}: missing {key!r}")
            counts: Counter = Counter()
            for row in document["works"]:
                source, work_id = row.get("source"), row.get("work_id")
                if not source or work_id in (None, ""):
                    raise ValueError(f"{path}: a reservation needs a source and a work_id: {row!r}")
                reservations.works.setdefault(str(source), set()).add(str(work_id))
                counts[str(source)] += 1
            reservations.files.append(
                {
                    "set": document["set"],
                    "registry": document["registry"],
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "works": dict(sorted(counts.items())),
                }
            )
        return reservations

    def reserved(self, source: str, work_id: object) -> bool:
        return str(work_id) in self.works.get(source, ())

    def card(self) -> list[dict[str, Any]]:
        """What a corpus card records: set, registry, file sha256 and counts, not the ids."""
        return list(self.files)

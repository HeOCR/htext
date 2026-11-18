"""The committed K1-8 fetch manifest pins every file it lists."""

from __future__ import annotations

import json
import re
from pathlib import Path

from htext.knesset.fetch import MANIFEST_SCHEMA, USER_AGENT, local_file
from htext.knesset.laws import booklet_unit

MANIFEST = Path(__file__).resolve().parents[1] / "data" / "knesset_laws" / "sources.v1.json"


def test_manifest_pins_every_file():
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert document["schema"] == MANIFEST_SCHEMA
    assert document["knessets"] == list(range(1, 9))
    assert document["source"]["user_agent"] == USER_AGENT
    documents = [doc for bill in document["bills"] for doc in bill["documents"]]
    assert document["counts"]["bills"] == len(document["bills"]) == 2146
    assert document["counts"]["files_pinned"] == document["counts"]["files"] == len(documents)
    for doc in documents:
        assert re.fullmatch(r"[0-9a-f]{64}", doc["sha256"]) and doc["bytes"] > 0 and not doc.get("error")
        assert local_file(doc["url"]) == (doc["file"], doc["format"])
    assert len({bill["bill_id"] for bill in document["bills"]}) == len(document["bills"])


def test_every_law_maps_to_a_booklet():
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    units = [booklet_unit(bill) for bill in document["bills"]]
    # One K1-8 law has no MagazineNumber in OData; the builder holds it out as no_booklet_number.
    assert sum(unit is None for unit in units) == 1
    assert sum(bool(unit) and unit.startswith("chukei_taktziv_") for unit in units) == 76

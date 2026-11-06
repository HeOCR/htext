"""Fetch creator birth and death years from Wikidata for the PBY catalogue.

Usage (from the repository root, with network access; run once per pin):

    python scripts/fetch_pby_creators.py PATH/TO/public_domain_dump/pseudocatalogue.csv \
        --dump-commit <full sha> --output data/pby/creators.json

This is the only step of the PBY intake that uses the network. It reads every
distinct author and translator QID in the catalogue, fetches each item's P570
(date of death) and P569 (date of birth) claims and its current revision id,
and writes them as a pinned, reviewable ``creators.json``. The intake builder
reads that file and never calls Wikidata itself.

Year rules (conservative for public-domain status):

- deprecated claims are ignored; preferred claims win over normal ones;
- a value less precise than a year (decade, century) is recorded as the
  latest year it allows, with its precision, so it can only make a creator
  look more recent;
- several remaining death claims give the latest year.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "htext-pby-creators/0.1 (https://github.com/HeOCR/htext)"
BATCH = 50
# The catalogue writes Q0 where a creator has no Wikidata item.
PLACEHOLDER_QIDS = frozenset({"Q0"})
PRECISION_NAMES = {6: "millennium", 7: "century", 8: "decade", 9: "year", 10: "month", 11: "day"}


def catalogue_qids(catalogue: Path) -> list[str]:
    qids: set[str] = set()
    with catalogue.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            for column in ("author_uris", "translator_uris"):
                for uri in (row.get(column) or "").split(";"):
                    uri = uri.strip()
                    qid = uri.rsplit("/", 1)[-1]
                    if uri and qid not in PLACEHOLDER_QIDS:
                        qids.add(qid)
    return sorted(qids, key=lambda qid: int(qid[1:]))


def _latest_year(value: dict) -> tuple[int, int] | None:
    """Return (latest possible year, precision) for a Wikidata time value."""

    text = value["time"]
    sign = -1 if text.startswith("-") else 1
    year = sign * int(text[1:].split("-", 1)[0])
    precision = int(value["precision"])
    if precision >= 9:
        return year, precision
    span = {8: 10, 7: 100, 6: 1000}.get(precision)
    if span is None:
        return None
    # Wikidata stores a decade as its first year (1890 for the 1890s) and a
    # century as a year inside it (1900 for the 19th century is common).
    if precision == 8:
        return year - year % 10 + 9, precision
    if precision == 7:
        start = year - year % 100
        return (start if year % 100 == 0 else start + 100), precision
    return year - year % 1000 + 999, precision


def _claim_year(claims: list[dict], *, latest: bool) -> dict | None:
    usable = [claim for claim in claims if claim.get("rank") != "deprecated"]
    preferred = [claim for claim in usable if claim.get("rank") == "preferred"]
    years = []
    for claim in preferred or usable:
        snak = claim.get("mainsnak", {})
        if snak.get("snaktype") != "value":
            continue
        parsed = _latest_year(snak["datavalue"]["value"])
        if parsed:
            years.append(parsed)
    if not years:
        return None
    year, precision = (max if latest else min)(years)
    return {"year": year, "precision": PRECISION_NAMES.get(precision, str(precision))}


def fetch(qids: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for start in range(0, len(qids), BATCH):
        batch = qids[start : start + BATCH]
        query = urllib.parse.urlencode(
            {
                "action": "wbgetentities",
                "ids": "|".join(batch),
                "props": "claims|info|labels",
                "languages": "he|en",
                "format": "json",
            }
        )
        request = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.load(response)
        if "entities" not in payload:
            raise SystemExit(f"Wikidata error for {batch[0]}..{batch[-1]}: {payload.get('error')}")
        entities = payload["entities"]
        for qid in batch:
            entity = entities.get(qid, {})
            if "missing" in entity or not entity:
                out[qid] = {"qid": qid, "missing": True}
                continue
            claims = entity.get("claims", {})
            labels = entity.get("labels", {})
            death = _claim_year(claims.get("P570", []), latest=True)
            birth = _claim_year(claims.get("P569", []), latest=False)
            out[qid] = {
                "qid": qid,
                "label_he": labels.get("he", {}).get("value"),
                "label_en": labels.get("en", {}).get("value"),
                "death_year": death["year"] if death else None,
                "death_year_precision": death["precision"] if death else None,
                "birth_year": birth["year"] if birth else None,
                "wikidata_revision": entity.get("lastrevid"),
            }
            if entity.get("id", qid) != qid:
                out[qid]["resolved_qid"] = entity["id"]
        print(f"fetched {min(start + BATCH, len(qids))}/{len(qids)}", file=sys.stderr)
        time.sleep(1)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("catalogue", type=Path)
    parser.add_argument("--dump-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    qids = catalogue_qids(args.catalogue)
    creators = fetch(qids)
    document = {
        "schema": "pby_creators.v1",
        "source": {
            "wikidata_api": API,
            "properties": {"death": "P570", "birth": "P569"},
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "catalogue": "projectbenyehuda/public_domain_dump pseudocatalogue.csv",
            "dump_commit": args.dump_commit,
        },
        "year_rules": (
            "deprecated claims ignored; preferred claims win; imprecise dates give the latest year they "
            "allow; several death claims give the latest year"
        ),
        "creators": [creators[qid] for qid in qids],
        "manual": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

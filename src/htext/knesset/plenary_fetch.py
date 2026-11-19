"""Fetch the Knesset plenary protocols ("דברי הכנסת") and pin every file.

This is the only step of the ``knesset-plenary`` intake that uses the network.
It runs once per pin, outside the build, as the laws fetcher does, and reuses
its polite client (one request at a time, at least a second apart, a generic
client name, every request logged).

1. **Scope** (sources plan, decision 1, heocr-lead 2026-11-18). Sittings of
   K1-8 that started before 1976-01-01, and every sitting of K13-25. K8 from
   1976 and K9-12 carry no hocrgen publishability flag and are not listed.
2. **Catalogue.** ``KNS_PlenumSession`` lists the sittings. ``KNS_DocumentPlenumSession``
   group 28 ("דברי הכנסת") gives each sitting's protocol files, named
   ``<k>_ptm_<n>``. Scans (PIC), video and URL rows are never fetched.
3. **Reserved sittings.** A sitting whose unit id ``K<k>_<number>`` eval
   reserves (source ``plenary``) is dropped from the catalogue before any file
   is fetched, so its text never reaches disk. When two sittings share a unit
   id, a reservation drops both. The manifest records how many sittings were
   reserved, never which.
4. **Files.** The DOC (or DOCX) of every sitting left. K1-8 DOCs hold the same
   OCR text as the PDF's text layer. The PDF is fetched only for a seeded
   sample of K1-8 sittings, for the eye check against the scan.
5. **Pins.** The manifest records each sitting's OData fields and each file's
   URL, local path, size and sha256. Downloads stay outside git; a file already
   on disk is hashed and reused, so a rerun resumes.
"""

from __future__ import annotations

import random
import re
import urllib.parse
from typing import Any, Iterable

from htext.knesset.fetch import ODATA, USER_AGENT, FetchError, PoliteClient, _sha256_file, odata_rows
from htext.reservations import Reservations

MANIFEST_SCHEMA = "htext_knesset_plenary_sources.v1"
PROTOCOL_GROUP_TYPE = 28
# Knesset -> sittings must start before this date (None: every sitting).
SCOPE: dict[int, str | None] = {**{k: "1976-01-01" for k in range(1, 9)}, **{k: None for k in range(13, 26)}}
EYE_CHECK_PDFS = 100
SESSION_FIELDS = ("PlenumSessionID", "KnessetNum", "Number", "Name", "StartDate", "FinishDate", "IsSpecialMeeting", "LastUpdatedDate")
DOCUMENT_FIELDS = ("DocumentPlenumSessionID", "PlenumSessionID", "GroupTypeID", "ApplicationDesc", "FilePath", "LastUpdatedDate")
# Sessions per KNS_DocumentPlenumSession query; an OR filter keeps the URL short.
SESSIONS_PER_QUERY = 15

_FILE_URL = re.compile(r"^https://fs\.knesset\.gov\.il//?(\d+)/Plenum/(\d+_ptm_\d+)\.(doc|docx|pdf)$", re.I)


def unit_id(session: dict[str, Any]) -> str:
    """Eval's plenary unit id: ``K<knesset>_<sitting number>``."""
    return f"K{int(session['knesset'])}_{int(session['number'])}"


def in_scope(knesset: int, start_date: str | None) -> bool:
    if knesset not in SCOPE:
        return False
    before = SCOPE[knesset]
    return before is None or (bool(start_date) and str(start_date)[:10] < before)


def local_file(url: str) -> tuple[str, str] | None:
    """``(relative path, format)`` for a protocol file URL, or None if the URL is not one."""
    match = _FILE_URL.match(url.strip())
    if not match:
        return None
    knesset, stem, extension = match.groups()
    fmt = "PDF" if extension.lower() == "pdf" else "DOC"
    return f"{int(knesset)}/{stem}.{extension.lower()}", fmt


def session_filter() -> str:
    return "(" + " or ".join(f"KnessetNum eq {k}" for k in sorted(SCOPE)) + ")"


def document_filter(session_ids: Iterable[int]) -> str:
    ids = " or ".join(f"PlenumSessionID eq {int(i)}" for i in session_ids)
    return f"({ids}) and GroupTypeID eq {PROTOCOL_GROUP_TYPE}"


def odata_url(entity: str, *, filter: str, select: Iterable[str]) -> str:
    query = urllib.parse.urlencode({"$filter": filter, "$select": ",".join(select), "$format": "json"}, quote_via=urllib.parse.quote)
    return f"{ODATA}/{entity}()?{query}"


def session_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "plenum_session_id": int(row["PlenumSessionID"]),
        "knesset": int(row["KnessetNum"]),
        "number": None if row.get("Number") is None else int(row["Number"]),
        "name": row.get("Name"),
        "start_date": row.get("StartDate"),
        "finish_date": row.get("FinishDate"),
        "is_special_meeting": row.get("IsSpecialMeeting"),
        "odata_last_updated": row.get("LastUpdatedDate"),
    }


def select_sessions(rows: Iterable[dict[str, Any]], reservations: Reservations) -> tuple[list[dict], dict[str, int]]:
    """Sittings in scope and not reserved, and the counts of what was left out (no ids)."""
    sessions = [session_record(row) for row in rows]
    counts = {"listed": len(sessions), "out_of_scope": 0, "no_unit_id": 0, "reserved_sittings": 0, "reserved_unit_ids": 0}
    scoped = []
    for session in sessions:
        if not in_scope(session["knesset"], session["start_date"]):
            counts["out_of_scope"] += 1
        elif session["number"] is None:
            # No sitting number means no unit id, so the reservation cannot be checked: held out.
            counts["no_unit_id"] += 1
        else:
            scoped.append(session)
    reserved_units = {unit_id(s) for s in scoped if reservations.reserved("plenary", unit_id(s))}
    counts["reserved_unit_ids"] = len(reserved_units)
    kept = []
    for session in scoped:
        if unit_id(session) in reserved_units:
            counts["reserved_sittings"] += 1
        else:
            kept.append(session)
    kept.sort(key=lambda s: (s["knesset"], s["number"], s["plenum_session_id"]))
    counts["in_scope"] = len(scoped) + counts["no_unit_id"]
    counts["kept"] = len(kept)
    return kept, counts


def eye_check_sample(sessions: Iterable[dict[str, Any]], n: int, seed: int) -> set[int]:
    """Seeded sample of K1-8 sittings whose PDF is fetched for the eye check."""
    early = sorted(s["plenum_session_id"] for s in sessions if s["knesset"] <= 8)
    return set(random.Random(seed).sample(early, min(n, len(early))))


def protocol_documents(rows: Iterable[dict[str, Any]], sessions: list[dict[str, Any]], eye_check: set[int]) -> list[dict]:
    """Attach each kept sitting's protocol files: its DOCs, and its PDF if sampled. Returns the rows left out."""
    by_id = {s["plenum_session_id"]: s for s in sessions}
    for session in sessions:
        session["documents"] = []
    skipped: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        url = str(row.get("FilePath") or "")
        session = by_id.get(int(row.get("PlenumSessionID") or -1))
        if session is None:
            continue  # not a kept sitting (reserved sittings never get this far)
        if row.get("GroupTypeID") != PROTOCOL_GROUP_TYPE:
            skipped.append({"url": url, "reason": "not_group_28"})
            continue
        parsed = local_file(url)
        if parsed is None:
            skipped.append({"url": url, "reason": f"not_fetched:{row.get('ApplicationDesc')}"})
            continue
        path, fmt = parsed
        if fmt == "PDF" and session["plenum_session_id"] not in eye_check:
            continue  # counted in the manifest as pdfs_not_sampled
        if path in seen:
            continue
        seen.add(path)
        session["documents"].append(
            {
                "document_id": str(row.get("DocumentPlenumSessionID")),
                "format": fmt,
                "url": url,
                "file": path,
                "odata_last_updated": row.get("LastUpdatedDate"),
            }
        )
    for session in sessions:
        session["documents"].sort(key=lambda d: (d["format"], d["file"]))
    return sorted(skipped, key=lambda r: r["url"])


def fetch_catalogue(client: PoliteClient, reservations: Reservations, *, eye_check_pdfs: int = EYE_CHECK_PDFS, seed: int = 15) -> dict[str, Any]:
    rows = odata_rows(client, odata_url("KNS_PlenumSession", filter=session_filter(), select=SESSION_FIELDS))
    sessions, counts = select_sessions(rows, reservations)
    eye = eye_check_sample(sessions, eye_check_pdfs, seed)
    documents: list[dict] = []
    ids = [s["plenum_session_id"] for s in sessions]
    for start in range(0, len(ids), SESSIONS_PER_QUERY):
        batch = ids[start : start + SESSIONS_PER_QUERY]
        documents += odata_rows(client, odata_url("KNS_DocumentPlenumSession", filter=document_filter(batch), select=DOCUMENT_FIELDS))
    skipped = protocol_documents(documents, sessions, eye)
    counts["eye_check_sittings"] = len(eye)
    return {"sessions": sessions, "selection": counts, "skipped_documents": skipped, "seed": seed}


def download(client: PoliteClient, catalogue: dict[str, Any], inputs) -> dict[str, int]:
    """Download every listed file into ``inputs``, reusing files already there; fill in size and sha256."""
    counts = {"downloaded": 0, "reused": 0, "failed": 0}
    for session in catalogue["sessions"]:
        for doc in session["documents"]:
            target = inputs / doc["file"]
            if target.exists() and target.stat().st_size > 0:
                counts["reused"] += 1
            else:
                try:
                    body = client.get(doc["url"])
                except FetchError as error:
                    doc.update({"sha256": None, "bytes": None, "error": str(error)})
                    counts["failed"] += 1
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                partial = target.with_name(target.name + ".part")
                partial.write_bytes(body)
                partial.replace(target)
                counts["downloaded"] += 1
            doc["sha256"] = _sha256_file(target)
            doc["bytes"] = target.stat().st_size
            doc.pop("error", None)
    return counts


def manifest(catalogue: dict[str, Any], *, reservations: Reservations, counts: dict[str, int], fetched_at: str) -> dict[str, Any]:
    sessions = catalogue["sessions"]
    docs = [doc for s in sessions for doc in s["documents"]]
    per_knesset: dict[str, dict[str, int]] = {}
    for session in sessions:
        row = per_knesset.setdefault(str(session["knesset"]), {"sittings": 0, "with_doc": 0, "without_doc": 0, "pdfs": 0})
        formats = {doc["format"] for doc in session["documents"]}
        row["sittings"] += 1
        row["with_doc"] += "DOC" in formats
        row["without_doc"] += "DOC" not in formats
        row["pdfs"] += "PDF" in formats
    return {
        "schema": MANIFEST_SCHEMA,
        "source": {
            "odata": ODATA,
            "entities": ["KNS_PlenumSession", "KNS_DocumentPlenumSession"],
            "session_filter": session_filter(),
            "scope": {str(k): (f"before {v}" if v else "all sittings") for k, v in SCOPE.items()},
            "document_group_type_id": PROTOCOL_GROUP_TYPE,
            "files_host": "https://fs.knesset.gov.il",
            "user_agent": USER_AGENT,
            "fetched_at": fetched_at,
        },
        "eval_reservations": reservations.card(),
        "eye_check": {"pdf_sittings": catalogue["selection"]["eye_check_sittings"], "seed": catalogue["seed"]},
        "counts": {
            "selection": catalogue["selection"],
            "files": len(docs),
            "files_pinned": sum(1 for doc in docs if doc.get("sha256")),
            "files_failed": sum(1 for doc in docs if doc.get("error")),
            "skipped_documents": len(catalogue["skipped_documents"]),
            "per_knesset": dict(sorted(per_knesset.items(), key=lambda item: int(item[0]))),
            "this_run": counts,
        },
        "sessions": sessions,
        "skipped_documents": catalogue["skipped_documents"],
    }

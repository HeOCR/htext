"""Fetch the Knesset's enacted laws, as published in Reshumot, and pin every file.

This is the only step of the ``knesset-laws`` intake that uses the network. It
runs once per pin, outside the build, as ``scripts/fetch_pby_creators.py`` does
for PBY (sources plan, sections 2-3).

1. **Catalogue.** The Knesset OData service (no key) lists every bill of the
   chosen Knessets that has a publication series (``KNS_Bill``,
   ``PublicationSeriesID`` not null). For those bills it lists the documents of
   group 9, "חוק - פרסום ברשומות", the law as published (``KNS_DocumentBill``,
   files named ``<k>_lsr_<n>``). First-reading bills (group 2, ``_ls1_``) are out
   by decision 2 of the plan, and are never listed.
2. **Files.** Each group-9 DOC and PDF is downloaded from ``fs.knesset.gov.il``.
   The DOC holds the same OCR text as the PDF's text layer, in logical order;
   the builder prefers it and keeps the PDF for the eye check against the scan.
   TIF scans are not fetched.
3. **Pins.** The manifest records each bill's OData fields, each file's URL,
   local path, size and sha256, and the time of the fetch. Every request goes
   to a JSON-lines log.

Fetching is polite: one request at a time, at least ``min_interval`` seconds
apart (1 by default), a generic client name, and a few retries with backoff on
server errors. A file already on disk is hashed and reused, so a rerun resumes.
Downloads stay outside git.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

ODATA = "https://knesset.gov.il/Odata/ParliamentInfo.svc"
USER_AGENT = "htext-fetch/0.1 (https://github.com/HeOCR/htext)"
MANIFEST_SCHEMA = "htext_knesset_laws_sources.v1"

# Group 9 is the law as published in Reshumot. Group 2 (first-reading bills) is out.
LAW_GROUP_TYPE = 9
FORMATS = ("DOC", "PDF")
# Bills per KNS_DocumentBill query; an OR filter keeps the URL short.
BILLS_PER_QUERY = 15

BILL_FIELDS = (
    "BillID",
    "KnessetNum",
    "Name",
    "PublicationDate",
    "MagazineNumber",
    "PageNumber",
    "PublicationSeriesID",
    "PublicationSeriesDesc",
    "LastUpdatedDate",
)
DOCUMENT_FIELDS = ("DocumentBillID", "BillID", "GroupTypeID", "ApplicationDesc", "FilePath", "LastUpdatedDate")

# fs.knesset.gov.il writes a doubled slash after the host; both forms are read.
_FILE_URL = re.compile(r"^https://fs\.knesset\.gov\.il//?(\d+)/law/(\d+_lsr_\d+)\.(DOC|PDF)$", re.I)


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes


Transport = Callable[[str], Response]


def urllib_transport(url: str, *, timeout: float = 60) -> Response:
    """GET ``url`` with the generic client name; HTTP errors come back as a status."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, */*"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return Response(response.status, response.read())
    except urllib.error.HTTPError as error:
        return Response(error.code, error.read() or b"")


class FetchError(RuntimeError):
    pass


@dataclass
class PoliteClient:
    """One request at a time, ``min_interval`` seconds apart, every request logged."""

    transport: Transport = urllib_transport
    min_interval: float = 1.0
    retries: int = 3
    backoff: float = 5.0
    log_path: Path | None = None
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    requests: int = 0
    _last: float | None = field(default=None, repr=False)

    def _wait(self) -> None:
        if self._last is not None:
            delay = self.min_interval - (self.clock() - self._last)
            if delay > 0:
                self.sleep(delay)
        self._last = self.clock()

    def _log(self, row: dict[str, Any]) -> None:
        if self.log_path is None:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    def get(self, url: str) -> bytes:
        for attempt in range(1, self.retries + 1):
            self._wait()
            self.requests += 1
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                response = self.transport(url)
            except (OSError, urllib.error.URLError) as error:
                self._log({"at": stamp, "url": url, "attempt": attempt, "error": type(error).__name__})
                response = None
            if response is not None:
                row = {"at": stamp, "url": url, "attempt": attempt, "status": response.status, "bytes": len(response.body)}
                if response.status == 200:
                    row["sha256"] = hashlib.sha256(response.body).hexdigest()
                self._log(row)
                if response.status == 200:
                    return response.body
                if response.status < 500 and response.status != 429:
                    raise FetchError(f"HTTP {response.status} for {url}")
            if attempt < self.retries:
                self.sleep(self.backoff * attempt)
        raise FetchError(f"gave up on {url} after {self.retries} attempts")

    def get_json(self, url: str) -> dict[str, Any]:
        return json.loads(self.get(url).decode("utf-8"))


def odata_url(entity: str, *, filter: str, select: Iterable[str]) -> str:
    query = urllib.parse.urlencode(
        {"$filter": filter, "$select": ",".join(select), "$format": "json"}, quote_via=urllib.parse.quote
    )
    return f"{ODATA}/{entity}()?{query}"


def odata_rows(client: PoliteClient, url: str) -> Iterator[dict[str, Any]]:
    """Every row of an OData query, following ``odata.nextLink`` (relative to the service root)."""
    while url:
        page = client.get_json(url)
        if "value" not in page:
            raise FetchError(f"no 'value' in OData response for {url}: {str(page)[:200]}")
        yield from page["value"]
        link = page.get("odata.nextLink")
        if not link:
            break
        url = link if link.startswith("http") else f"{ODATA}/{link}"
        if "$format=json" not in url:
            url += "&$format=json"


def bill_filter(knessets: Iterable[int]) -> str:
    numbers = sorted(set(knessets))
    if not numbers:
        raise ValueError("no Knessets given")
    if numbers == list(range(numbers[0], numbers[-1] + 1)):
        span = f"KnessetNum ge {numbers[0]} and KnessetNum le {numbers[-1]}"
    else:
        span = "(" + " or ".join(f"KnessetNum eq {k}" for k in numbers) + ")"
    return f"{span} and PublicationSeriesID ne null"


def document_filter(bill_ids: Iterable[int]) -> str:
    ids = " or ".join(f"BillID eq {int(bill_id)}" for bill_id in bill_ids)
    return f"({ids}) and GroupTypeID eq {LAW_GROUP_TYPE}"


def local_file(url: str) -> tuple[str, str] | None:
    """``(relative path, format)`` for a law file URL, or None if the URL is not a group-9 law file."""
    match = _FILE_URL.match(url.strip())
    if not match:
        return None
    knesset, stem, extension = match.groups()
    extension = extension.upper()
    return f"{int(knesset)}/{stem}.{extension}", extension


def law_documents(rows: Iterable[dict[str, Any]], formats: Iterable[str] = FORMATS) -> tuple[list[dict], list[dict]]:
    """Split document rows into the law files to fetch and the rows left out, with a reason each."""
    wanted = {fmt.upper() for fmt in formats}
    kept, skipped = [], []
    seen: set[tuple[Any, str]] = set()
    for row in rows:
        url = str(row.get("FilePath") or "")
        if row.get("GroupTypeID") != LAW_GROUP_TYPE:
            skipped.append({"url": url, "bill_id": row.get("BillID"), "reason": "not_group_9"})
            continue
        parsed = local_file(url)
        if parsed is None:
            reason = "scan_only" if url.upper().endswith((".TIF", ".TIFF")) else "unexpected_path"
            skipped.append({"url": url, "bill_id": row.get("BillID"), "reason": reason})
            continue
        path, fmt = parsed
        if fmt not in wanted:
            skipped.append({"url": url, "bill_id": row.get("BillID"), "reason": "format_not_fetched"})
            continue
        key = (row.get("BillID"), path)
        if key in seen:
            continue
        seen.add(key)
        kept.append(
            {
                "bill_id": int(row["BillID"]),
                "document_bill_id": str(row.get("DocumentBillID")),
                "format": fmt,
                "url": url,
                "file": path,
                "odata_last_updated": row.get("LastUpdatedDate"),
            }
        )
    kept.sort(key=lambda doc: (doc["bill_id"], doc["format"], doc["file"]))
    return kept, skipped


def bill_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "bill_id": int(row["BillID"]),
        "knesset": int(row["KnessetNum"]),
        "name": row.get("Name"),
        "publication_date": (row.get("PublicationDate") or "")[:10] or None,
        "publication_series_id": row.get("PublicationSeriesID"),
        "publication_series": row.get("PublicationSeriesDesc"),
        "magazine_number": row.get("MagazineNumber"),
        "page_number": row.get("PageNumber"),
        "odata_last_updated": row.get("LastUpdatedDate"),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_catalogue(client: PoliteClient, knessets: Iterable[int], formats: Iterable[str] = FORMATS) -> dict[str, Any]:
    bills = [bill_record(row) for row in odata_rows(client, odata_url("KNS_Bill", filter=bill_filter(knessets), select=BILL_FIELDS))]
    bills.sort(key=lambda bill: bill["bill_id"])
    ids = [bill["bill_id"] for bill in bills]
    rows: list[dict[str, Any]] = []
    for start in range(0, len(ids), BILLS_PER_QUERY):
        batch = ids[start : start + BILLS_PER_QUERY]
        rows += odata_rows(client, odata_url("KNS_DocumentBill", filter=document_filter(batch), select=DOCUMENT_FIELDS))
    documents, skipped = law_documents(rows, formats)
    by_bill: dict[int, list[dict]] = {}
    for doc in documents:
        by_bill.setdefault(doc["bill_id"], []).append(doc)
    for bill in bills:
        bill["documents"] = by_bill.get(bill["bill_id"], [])
    return {"bills": bills, "skipped_documents": sorted(skipped, key=lambda row: (row["bill_id"] or 0, row["url"]))}


def download(client: PoliteClient, catalogue: dict[str, Any], inputs: Path) -> dict[str, int]:
    """Download every listed file into ``inputs``, reusing files already there; fill in size and sha256."""
    counts = {"downloaded": 0, "reused": 0, "failed": 0}
    for bill in catalogue["bills"]:
        for doc in bill["documents"]:
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


def manifest(catalogue: dict[str, Any], *, knessets: Iterable[int], formats: Iterable[str], counts: dict[str, int], fetched_at: str) -> dict[str, Any]:
    bills = catalogue["bills"]
    docs = [doc for bill in bills for doc in bill["documents"]]
    per_knesset: dict[str, dict[str, int]] = {}
    for bill in bills:
        row = per_knesset.setdefault(str(bill["knesset"]), {"bills": 0, "with_doc": 0, "with_pdf": 0, "without_file": 0})
        row["bills"] += 1
        formats_here = {doc["format"] for doc in bill["documents"] if doc.get("sha256")}
        row["with_doc"] += "DOC" in formats_here
        row["with_pdf"] += "PDF" in formats_here
        row["without_file"] += not formats_here
    return {
        "schema": MANIFEST_SCHEMA,
        "source": {
            "odata": ODATA,
            "entities": ["KNS_Bill", "KNS_DocumentBill"],
            "bill_filter": bill_filter(knessets),
            "document_group_type_id": LAW_GROUP_TYPE,
            "formats": sorted({fmt.upper() for fmt in formats}),
            "files_host": "https://fs.knesset.gov.il",
            "user_agent": USER_AGENT,
            "fetched_at": fetched_at,
        },
        "knessets": sorted(set(knessets)),
        "counts": {
            "bills": len(bills),
            "files": len(docs),
            "files_pinned": sum(1 for doc in docs if doc.get("sha256")),
            "files_failed": sum(1 for doc in docs if doc.get("error")),
            "skipped_documents": len(catalogue["skipped_documents"]),
            "per_knesset": dict(sorted(per_knesset.items(), key=lambda item: int(item[0]))),
            "this_run": counts,
        },
        "bills": bills,
        "skipped_documents": catalogue["skipped_documents"],
    }


def parse_knessets(text: str) -> list[int]:
    """``"1-8"`` or ``"1,3,5"`` to a list of Knesset numbers."""
    numbers: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            low, high = (int(value) for value in part.split("-", 1))
            if low > high:
                raise ValueError(f"bad range {part!r}")
            numbers.update(range(low, high + 1))
        elif part:
            numbers.add(int(part))
    if not numbers or min(numbers) < 1:
        raise ValueError(f"bad Knesset list {text!r}")
    return sorted(numbers)

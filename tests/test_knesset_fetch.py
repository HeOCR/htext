"""Offline tests for the Knesset laws fetcher: a fake transport stands in for the network."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from htext.knesset import fetch
from htext.knesset.fetch import FetchError, PoliteClient, Response


def _bill(bill_id: int, knesset: int, magazine: int, series: int = 6071) -> dict:
    return {
        "BillID": bill_id,
        "KnessetNum": knesset,
        "Name": f"חוק הבדיקה {bill_id}, התשי\"ט-1958",
        "PublicationDate": "1958-11-26T00:00:00",
        "MagazineNumber": magazine,
        "PageNumber": 2,
        "PublicationSeriesID": series,
        "PublicationSeriesDesc": "ספר החוקים",
        "LastUpdatedDate": "2025-12-07T15:53:37.49",
    }


def _doc(bill_id: int, group: int, fmt: str, path: str) -> dict:
    return {
        "DocumentBillID": str(bill_id * 10 + group),
        "BillID": bill_id,
        "GroupTypeID": group,
        "ApplicationDesc": fmt,
        "FilePath": f"https://fs.knesset.gov.il//{path}",
        "LastUpdatedDate": "2012-07-02T16:53:10.767",
    }


class FakeKnesset:
    """Serves two pages of bills, their documents, and file bytes; records every URL."""

    def __init__(self) -> None:
        self.urls: list[str] = []
        self.bills = [_bill(101, 3, 263), _bill(102, 3, 264), _bill(103, 4, 300)]
        self.documents = [
            _doc(101, 9, "DOC", "3/law/3_lsr_1.DOC"),
            _doc(101, 9, "PDF", "3/law/3_lsr_2.PDF"),
            _doc(101, 9, "PIC", "3/law/3_lsr_3.TIF"),
            _doc(101, 2, "DOC", "3/law/3_ls1_4.DOC"),
            _doc(102, 9, "PDF", "3/law/3_lsr_5.PDF"),
        ]
        self.files = {"3_lsr_1.DOC": b"doc one", "3_lsr_2.PDF": b"%PDF two", "3_lsr_5.PDF": b"%PDF five"}
        self.fail_once: set[str] = set()

    def __call__(self, url: str) -> Response:
        self.urls.append(url)
        if url.startswith(fetch.ODATA + "/KNS_Bill"):
            if "skiptoken" in url:
                return Response(200, json.dumps({"value": self.bills[2:]}).encode())
            page = {"value": self.bills[:2], "odata.nextLink": "KNS_Bill?$filter=x&$skiptoken=102"}
            return Response(200, json.dumps(page).encode())
        if url.startswith(fetch.ODATA + "/KNS_DocumentBill"):
            # Group 9 only, as the filter asks; the fake also leaks one group-2 row to prove the client re-checks.
            return Response(200, json.dumps({"value": self.documents}).encode())
        name = url.rsplit("/", 1)[-1]
        if name in self.fail_once:
            self.fail_once.discard(name)
            return Response(503, b"")
        if name in self.files:
            return Response(200, self.files[name])
        return Response(404, b"")


def _client(transport, tmp_path: Path | None = None, **kwargs) -> PoliteClient:
    sleeps: list[float] = []
    now = [0.0]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    client = PoliteClient(
        transport=transport,
        clock=lambda: now[0],
        sleep=sleep,
        log_path=tmp_path / "log.jsonl" if tmp_path else None,
        **kwargs,
    )
    client.sleeps = sleeps  # type: ignore[attr-defined]
    return client


def test_bill_filter_ranges_and_lists():
    assert fetch.bill_filter(range(1, 9)) == "KnessetNum ge 1 and KnessetNum le 8 and PublicationSeriesID ne null"
    assert fetch.bill_filter([5, 1]) == "(KnessetNum eq 1 or KnessetNum eq 5) and PublicationSeriesID ne null"
    with pytest.raises(ValueError):
        fetch.bill_filter([])


def test_document_filter_asks_for_group_9_only():
    assert fetch.document_filter([1, 2]) == "(BillID eq 1 or BillID eq 2) and GroupTypeID eq 9"


def test_parse_knessets():
    assert fetch.parse_knessets("1-8") == list(range(1, 9))
    assert fetch.parse_knessets("3, 1,3") == [1, 3]
    for bad in ("", "0", "5-2"):
        with pytest.raises(ValueError):
            fetch.parse_knessets(bad)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://fs.knesset.gov.il//3/law/3_lsr_211874.DOC", ("3/3_lsr_211874.DOC", "DOC")),
        ("https://fs.knesset.gov.il/8/law/8_lsr_1.pdf", ("8/8_lsr_1.PDF", "PDF")),
        ("https://fs.knesset.gov.il//3/law/3_ls1_284800.DOC", None),
        ("https://fs.knesset.gov.il//3/law/3_lsr_203911.TIF", None),
        ("https://example.org//3/law/3_lsr_1.DOC", None),
        ("https://fs.knesset.gov.il//3/law/../3_lsr_1.DOC", None),
    ],
)
def test_local_file_accepts_only_law_files(url, expected):
    assert fetch.local_file(url) == expected


def test_law_documents_keeps_doc_and_pdf_of_group_9():
    fake = FakeKnesset()
    kept, skipped = fetch.law_documents(fake.documents)
    assert [(doc["bill_id"], doc["file"]) for doc in kept] == [
        (101, "3/3_lsr_1.DOC"),
        (101, "3/3_lsr_2.PDF"),
        (102, "3/3_lsr_5.PDF"),
    ]
    assert sorted(row["reason"] for row in skipped) == ["not_group_9", "scan_only"]
    kept_doc_only, skipped_doc_only = fetch.law_documents(fake.documents, formats=["DOC"])
    assert [doc["file"] for doc in kept_doc_only] == ["3/3_lsr_1.DOC"]
    assert sum(row["reason"] == "format_not_fetched" for row in skipped_doc_only) == 2


def test_client_waits_between_requests_and_logs(tmp_path):
    fake = FakeKnesset()
    client = _client(fake, tmp_path)
    client.get("https://fs.knesset.gov.il//3/law/3_lsr_1.DOC")
    client.get("https://fs.knesset.gov.il//3/law/3_lsr_2.PDF")
    assert client.sleeps == [1.0]
    rows = [json.loads(line) for line in (tmp_path / "log.jsonl").read_text().splitlines()]
    assert [row["status"] for row in rows] == [200, 200]
    assert rows[0]["sha256"] == hashlib.sha256(b"doc one").hexdigest()


def test_client_retries_server_errors_but_not_404():
    fake = FakeKnesset()
    fake.fail_once.add("3_lsr_1.DOC")
    client = _client(fake, retries=3, backoff=5.0)
    assert client.get("https://fs.knesset.gov.il//3/law/3_lsr_1.DOC") == b"doc one"
    assert client.requests == 2
    with pytest.raises(FetchError, match="HTTP 404"):
        client.get("https://fs.knesset.gov.il//3/law/3_lsr_404.DOC")


def test_catalogue_follows_next_link_and_attaches_documents():
    fake = FakeKnesset()
    catalogue = fetch.fetch_catalogue(_client(fake), range(1, 9))
    assert [bill["bill_id"] for bill in catalogue["bills"]] == [101, 102, 103]
    bill = catalogue["bills"][0]
    assert bill["magazine_number"] == 263 and bill["publication_series_id"] == 6071
    assert bill["publication_date"] == "1958-11-26"
    assert [doc["format"] for doc in bill["documents"]] == ["DOC", "PDF"]
    assert catalogue["bills"][2]["documents"] == []
    assert any("skiptoken" in url and "%24format=json" not in url and "$format=json" in url for url in fake.urls)
    assert all(url.startswith(fetch.ODATA) for url in fake.urls)


def test_download_pins_files_and_resumes(tmp_path):
    fake = FakeKnesset()
    client = _client(fake)
    catalogue = fetch.fetch_catalogue(client, range(1, 9))
    counts = fetch.download(client, catalogue, tmp_path / "inputs")
    assert counts == {"downloaded": 3, "reused": 0, "failed": 0}
    doc = catalogue["bills"][0]["documents"][0]
    assert (tmp_path / "inputs" / "3/3_lsr_1.DOC").read_bytes() == b"doc one"
    assert doc["sha256"] == hashlib.sha256(b"doc one").hexdigest() and doc["bytes"] == 7
    assert not list((tmp_path / "inputs").rglob("*.part"))

    before = len(fake.urls)
    again = fetch.fetch_catalogue(client, range(1, 9))
    calls_for_catalogue = len(fake.urls) - before
    assert fetch.download(client, again, tmp_path / "inputs") == {"downloaded": 0, "reused": 3, "failed": 0}
    assert len(fake.urls) - before == calls_for_catalogue


def test_failed_file_is_recorded_not_fatal(tmp_path):
    fake = FakeKnesset()
    del fake.files["3_lsr_5.PDF"]
    client = _client(fake)
    catalogue = fetch.fetch_catalogue(client, range(1, 9))
    counts = fetch.download(client, catalogue, tmp_path)
    assert counts["failed"] == 1
    failed = catalogue["bills"][1]["documents"][0]
    assert failed["sha256"] is None and "404" in failed["error"]


def test_manifest_counts(tmp_path):
    fake = FakeKnesset()
    client = _client(fake)
    catalogue = fetch.fetch_catalogue(client, range(1, 9))
    counts = fetch.download(client, catalogue, tmp_path)
    document = fetch.manifest(catalogue, knessets=range(1, 9), formats=["DOC", "PDF"], counts=counts, fetched_at="T")
    assert document["schema"] == fetch.MANIFEST_SCHEMA
    assert document["source"]["user_agent"] == fetch.USER_AGENT
    assert document["counts"]["bills"] == 3 and document["counts"]["files_pinned"] == 3
    assert document["counts"]["per_knesset"] == {
        "3": {"bills": 2, "with_doc": 1, "with_pdf": 2, "without_file": 0, "files_pinned": 3},
        "4": {"bills": 1, "with_doc": 0, "with_pdf": 0, "without_file": 1, "files_pinned": 0},
    }
    listed_only = fetch.manifest(
        fetch.fetch_catalogue(client, range(1, 9)), knessets=range(1, 9), formats=["DOC"], counts={}, fetched_at="T"
    )
    assert listed_only["counts"]["per_knesset"]["3"]["with_pdf"] == 2
    assert listed_only["counts"]["per_knesset"]["3"]["files_pinned"] == 0
    assert document["counts"]["skipped_documents"] == 2
    json.dumps(document, ensure_ascii=False)


def test_user_agent_is_generic():
    assert "htext" in fetch.USER_AGENT and "@" not in fetch.USER_AGENT

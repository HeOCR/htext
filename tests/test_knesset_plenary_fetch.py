"""Offline tests for the Knesset plenary fetcher: a fake transport stands in for the network."""

from __future__ import annotations

import json
from pathlib import Path

from htext.knesset import plenary_fetch as pf
from htext.knesset.fetch import ODATA, PoliteClient, Response
from htext.reservations import Reservations


def _session(sid: int, knesset: int, number: int, start: str) -> dict:
    return {"PlenumSessionID": sid, "KnessetNum": knesset, "Number": number, "Name": f"ישיבה {number}",
            "StartDate": start, "FinishDate": start, "IsSpecialMeeting": False, "LastUpdatedDate": "2020-01-01T00:00:00"}


def _doc(did: int, sid: int, knesset: int, fmt: str, ext: str, group: int = 28) -> dict:
    return {"DocumentPlenumSessionID": str(did), "PlenumSessionID": sid, "GroupTypeID": group, "ApplicationDesc": fmt,
            "FilePath": f"https://fs.knesset.gov.il//{knesset}/Plenum/{knesset}_ptm_{did}.{ext}", "LastUpdatedDate": "2020"}


class FakeKnesset:
    def __init__(self) -> None:
        self.urls: list[str] = []
        self.sessions = [
            _session(1, 3, 10, "1955-01-04T16:00:00"),   # kept
            _session(2, 3, 11, "1955-01-05T16:00:00"),   # reserved
            _session(3, 8, 40, "1976-02-01T16:00:00"),   # K8 from 1976: out of scope
            _session(4, 16, 7, "2003-03-01T16:00:00"),   # kept, DOCX
            _session(5, 16, 8, "2003-03-02T16:00:00"),   # shares unit id K16_8 with 6
            _session(6, 16, 8, "2003-03-02T18:00:00"),   # reserved through the shared id
            _session(7, 10, 1, "1981-07-20T16:00:00"),   # K10: out of scope
            {**_session(8, 18, 0, "2010-01-01T16:00:00"), "Number": None},  # no unit id: held out
        ]
        self.documents = [
            _doc(11, 1, 3, "DOC", "doc"), _doc(12, 1, 3, "PDF", "pdf"), _doc(13, 1, 3, "PIC", "tif"),
            _doc(21, 2, 3, "DOC", "doc"), _doc(22, 2, 3, "PDF", "pdf"),
            _doc(41, 4, 16, "DOC", "docx"), _doc(42, 4, 16, "VDO", "mp4"), _doc(43, 4, 16, "DOC", "doc", group=30),
            _doc(51, 5, 16, "DOC", "doc"), _doc(61, 6, 16, "DOC", "doc"), _doc(81, 8, 18, "DOC", "doc"),
        ]

    def __call__(self, url: str) -> Response:
        self.urls.append(url)
        if url.startswith(ODATA + "/KNS_PlenumSession"):
            return Response(200, json.dumps({"value": self.sessions}).encode())
        if url.startswith(ODATA + "/KNS_DocumentPlenumSession"):
            return Response(200, json.dumps({"value": self.documents}).encode())
        name = url.rsplit("/", 1)[-1]
        return Response(200, f"bytes of {name}".encode())


def _client(fake) -> PoliteClient:
    now = [0.0]
    return PoliteClient(transport=fake, clock=lambda: now[0], sleep=lambda s: now.__setitem__(0, now[0] + s))


RESERVED = Reservations(units={"plenary": {"K3_11", "K16_8", "K10_1"}})


def test_scope_follows_decision_1():
    assert pf.in_scope(1, "1949-02-15T16:00:00") and pf.in_scope(8, "1975-12-31T10:00:00")
    assert not pf.in_scope(8, "1976-01-01T10:00:00")
    assert not any(pf.in_scope(k, "1980-01-01") for k in range(9, 13))
    assert pf.in_scope(13, "1992-07-13") and pf.in_scope(25, "2023-01-01")
    assert not pf.in_scope(26, "2027-01-01") and not pf.in_scope(3, None)


def test_local_file_reads_doc_docx_and_pdf_only():
    assert pf.local_file("https://fs.knesset.gov.il//16/Plenum/16_ptm_128870.doc") == ("16/16_ptm_128870.doc", "DOC")
    assert pf.local_file("https://fs.knesset.gov.il/20/Plenum/20_ptm_1.DOCX") == ("20/20_ptm_1.docx", "DOC")
    assert pf.local_file("https://fs.knesset.gov.il//3/Plenum/3_ptm_2.pdf") == ("3/3_ptm_2.pdf", "PDF")
    assert pf.local_file("https://fs.knesset.gov.il//3/Plenum/3_ptm_3.tif") is None
    assert pf.local_file("https://fs.knesset.gov.il//16/Plenum/16_toc_1.doc") is None


def test_reserved_sittings_are_never_requested(tmp_path):
    fake = FakeKnesset()
    client = _client(fake)
    catalogue = pf.fetch_catalogue(client, RESERVED, eye_check_pdfs=1)
    pf.download(client, catalogue, tmp_path)
    kept = {s["plenum_session_id"] for s in catalogue["sessions"]}
    assert kept == {1, 4}
    # No document query names a reserved sitting, and no reserved file is fetched.
    doc_queries = [u for u in fake.urls if u.startswith(ODATA + "/KNS_DocumentPlenumSession")]
    assert doc_queries and not any(f"PlenumSessionID%20eq%20{i}%" in u or u.endswith(f"PlenumSessionID%20eq%20{i}") for u in doc_queries for i in (2, 5, 6, 8))
    files = [u for u in fake.urls if "fs.knesset.gov.il" in u]
    assert not any(f"_ptm_{d}." in u for u in files for d in (21, 22, 51, 61, 81))
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == ["16_ptm_41.docx", "3_ptm_11.doc", "3_ptm_12.pdf"]


def test_selection_counts_and_no_reserved_ids_in_manifest(tmp_path):
    client = _client(FakeKnesset())
    catalogue = pf.fetch_catalogue(client, RESERVED, eye_check_pdfs=1)
    counts = pf.download(client, catalogue, tmp_path)
    document = pf.manifest(catalogue, reservations=RESERVED, counts=counts, fetched_at="2026-11-19T00:00:00Z")
    selection = document["counts"]["selection"]
    assert selection == {"listed": 8, "out_of_scope": 2, "no_unit_id": 1, "in_scope": 6, "reserved_unit_ids": 2,
                         "reserved_sittings": 3, "kept": 2, "eye_check_sittings": 1}
    assert document["counts"]["files_pinned"] == document["counts"]["files"] == 3
    text = json.dumps(document, ensure_ascii=False)
    for unit in ("K3_11", "K16_8"):
        assert unit not in text
    numbers = {(s["knesset"], s["number"]) for s in document["sessions"]}
    assert (3, 11) not in numbers and (16, 8) not in numbers


def test_pdf_only_for_the_eye_check_sample():
    client = _client(FakeKnesset())
    catalogue = pf.fetch_catalogue(client, RESERVED, eye_check_pdfs=0)
    formats = {d["format"] for s in catalogue["sessions"] for d in s["documents"]}
    assert formats == {"DOC"}
    sample = pf.eye_check_sample([{"plenum_session_id": i, "knesset": 3} for i in range(500)] + [{"plenum_session_id": 999, "knesset": 16}], 100, 15)
    assert len(sample) == 100 and 999 not in sample
    assert sample == pf.eye_check_sample([{"plenum_session_id": i, "knesset": 3} for i in range(500)], 100, 15)


def test_scans_video_and_other_groups_are_not_fetched():
    client = _client(FakeKnesset())
    catalogue = pf.fetch_catalogue(client, RESERVED, eye_check_pdfs=1)
    reasons = sorted(r["reason"] for r in catalogue["skipped_documents"])
    assert reasons == ["not_fetched:PIC", "not_fetched:VDO", "not_group_28"]

"""The Wikisource line-pair driver resumes from per-page receipts: an interrupted run, resumed, gives the same output."""

import json
import sys

import pytest

from htext.linepairs import wikisource as w


def _fake_compute(job, out, book, n):
    lines = [{"line": i, "label": f"שורה {n} {i}", "ocr": "x", "cer_nomarks": 0.1, "bbox": [0, 0, 1, 1]} for i in range(3)]
    return {"book": book, "n": n, "page_id": job["page_id"], "rev": job["rev"], "quality": job["quality"], "tags": job["tags"],
            "kept": lines, "dropped": {"unanchored": 1}, "ocr_lines": 4}


def _setup(tmp_path):
    pages = tmp_path / "pages.jsonl"
    pages.write_text("".join(json.dumps({"index": "Invented.pdf", "n": n, "page_id": 100 + n, "rev": 200 + n, "quality": 3,
                                         "eval_reserved_book": False, "wikitext": f"טקסט {n}"}, ensure_ascii=False) + "\n" for n in range(1, 7)), encoding="utf-8")
    (tmp_path / "scans.json").write_text(json.dumps([{"index": "Invented.pdf", "url": "u", "bytes": 1}]), encoding="utf-8")
    (tmp_path / "ledger.jsonl").write_text(json.dumps({"index": "Invented.pdf", "ok": True, "sha1": "0" * 40}) + "\n", encoding="utf-8")
    td = tmp_path / "tessdata"
    td.mkdir()
    (td / "heb_rivok.traineddata").write_bytes(b"model")
    return ["--pages", str(pages), "--scans", str(tmp_path / "scans.json"), "--scan-dir", str(tmp_path), "--tessdata", str(td),
            "--scan-ledger", str(tmp_path / "ledger.jsonl"), "--jobs", "1"]


def _run(monkeypatch, args, out):
    monkeypatch.setattr(sys, "argv", ["x", *args, "--out", str(out)])
    return w.main()


def test_interrupted_run_resumes_to_identical_output(tmp_path, monkeypatch):
    monkeypatch.setattr(w, "ProcessPoolExecutor", _Serial)
    args = _setup(tmp_path)
    monkeypatch.setattr(w, "_compute_page", _fake_compute)
    _run(monkeypatch, args, tmp_path / "clean")
    calls = {"n": 0}

    def crashing(job, out, book, n):
        calls["n"] += 1
        if calls["n"] == 4:
            raise KeyboardInterrupt  # the power cut, mid-run
        return _fake_compute(job, out, book, n)

    monkeypatch.setattr(w, "_compute_page", crashing)
    with pytest.raises(KeyboardInterrupt):
        _run(monkeypatch, args, tmp_path / "resumed")
    assert not (tmp_path / "resumed" / "pool.tsv").exists()  # no half-written final file
    recomputed = []
    monkeypatch.setattr(w, "_compute_page", lambda job, out, book, n: recomputed.append(n) or _fake_compute(job, out, book, n))
    _run(monkeypatch, args, tmp_path / "resumed")
    assert recomputed == [4, 5, 6]  # pages 1-3 came from their receipts
    for name in ("pool.tsv", "pages.jsonl"):
        assert (tmp_path / "resumed" / name).read_bytes() == (tmp_path / "clean" / name).read_bytes()


class _Serial:
    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def map(self, f, it, chunksize=1):
        return map(f, it)

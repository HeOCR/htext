"""Extract the text of each pinned Knesset Word file (laws or plenary records), once, into one gzipped JSON-lines file.

The Word files are Word 97-2003 documents (cp1255). ``textutil`` (macOS) reads
them and writes UTF-8; LibreOffice (``soffice --headless --convert-to``) is the
fallback elsewhere. Only DOC files are extracted: a PDF's text layer comes out
of ``pdftotext`` in visual order, with mirrored brackets and margin notes mixed
into the columns, so ``v1`` leaves the PDF-only laws out.

Each row is ``{"file", "sha256", "extractor", "text"}``; ``sha256`` is the source
file's, checked against the fetch manifest before extraction, so the build
can prove every text came from a pinned file.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable

TEXTS_SCHEMA = "htext_knesset_laws_texts.v1"
# The same rows for the plenary records (htext_knesset_plenary_sources.v1 manifests).
PLENARY_TEXTS_SCHEMA = "htext_knesset_plenary_texts.v1"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def textutil(path: Path) -> str:
    result = subprocess.run(
        ["textutil", "-convert", "txt", "-encoding", "UTF-8", "-stdout", str(path)], capture_output=True, check=True
    )
    return result.stdout.decode("utf-8")


def soffice(path: Path) -> str:
    with tempfile.TemporaryDirectory() as out:
        subprocess.run(
            ["soffice", "--headless", "--convert-to", "txt:Text (encoded):UTF8", "--outdir", out, str(path)],
            capture_output=True,
            check=True,
        )
        return (Path(out) / (path.stem + ".txt")).read_text(encoding="utf-8-sig")


def default_extractor() -> tuple[str, Callable[[Path], str]]:
    if shutil.which("textutil"):
        return f"textutil (macOS {platform.mac_ver()[0]})", textutil
    if shutil.which("soffice"):
        version = subprocess.run(["soffice", "--version"], capture_output=True, text=True, check=False).stdout.strip()
        return f"soffice ({version})", soffice
    raise SystemExit("no DOC extractor: install LibreOffice (soffice), or run on macOS (textutil)")


def doc_files(manifest: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """Every pinned DOC (or DOCX) of a laws manifest (``bills``) or a plenary manifest (``sessions``)."""
    for entry in manifest.get("bills", manifest.get("sessions", [])):
        for document in entry["documents"]:
            if document["format"] == "DOC" and document.get("sha256"):
                yield document


def texts_schema(manifest: dict[str, Any]) -> str:
    return PLENARY_TEXTS_SCHEMA if "sessions" in manifest else TEXTS_SCHEMA


def extract_all(
    manifest: dict[str, Any],
    inputs: Path,
    output: Path,
    *,
    extractor: tuple[str, Callable[[Path], str]] | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, int]:
    name, extract = extractor or default_extractor()
    counts = {"extracted": 0, "failed": 0}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as handle:
        header = {"schema": texts_schema(manifest), "extractor": name}
        handle.write((json.dumps(header, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
        for number, document in enumerate(doc_files(manifest), 1):
            path = inputs / document["file"]
            digest = _sha256_file(path)
            if digest != document["sha256"]:
                raise SystemExit(f"{path}: sha256 {digest} does not match the manifest's {document['sha256']}")
            try:
                text = extract(path)
            except (subprocess.CalledProcessError, UnicodeDecodeError, OSError) as error:
                row = {"file": document["file"], "sha256": digest, "extractor": name, "text": None, "error": type(error).__name__}
                counts["failed"] += 1
            else:
                row = {"file": document["file"], "sha256": digest, "extractor": name, "text": text}
                counts["extracted"] += 1
            handle.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
            if progress and number % 200 == 0:
                progress(f"{number} files extracted")
    return counts


def read_texts(path: Path, schema: str = TEXTS_SCHEMA) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """The header and ``{file: row}`` of a texts file."""

    with gzip.open(path, "rt", encoding="utf-8") as handle:
        header = json.loads(next(handle))
        if header.get("schema") != schema:
            raise ValueError(f"{path}: expected schema {schema!r}, found {header.get('schema')!r}")
        rows = {}
        for line in handle:
            row = json.loads(line)
            rows[row["file"]] = row
    return header, rows

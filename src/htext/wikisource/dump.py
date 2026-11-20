"""Stream MediaWiki XML, selecting revision payloads from page metadata."""

from __future__ import annotations

import bz2
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from xml.parsers import expat

PAGE = 104
INDEX = 112
ARTICLE = 0


@dataclass(frozen=True)
class Page:
    id: int
    title: str
    namespace: int
    redirected: bool


def scan(
    path: Path,
    *,
    select: Callable[[Page], Callable[[str], None] | None],
    finish: Callable[[Page, int, str, str], None],
    accept_revision: Callable[[Page, int], bool] | None = None,
) -> None:
    """Call select before the first revision text byte is delivered to a consumer.

    Skipped payloads are discarded by the XML reader. The build never creates
    a text node, string buffer or wikitext object for them. Only official,
    checksum-pinned XML is passed here by the builder.
    """
    parser = expat.ParserCreate(namespace_separator=" ")
    parser.buffer_text = True
    stack: list[str] = []
    fields: dict[str, str] = {}
    field_parts: list[str] = []
    page: Page | None = None
    consume: Callable[[str], None] | None = None
    redirected = False

    page_fields = {("page", field) for field in ("id", "title", "ns")}
    revision_fields = {("revision", field) for field in ("id", "model", "format")}
    metadata = page_fields | revision_fields | {("siteinfo", "dbname")}
    # XML export 0.11 keeps the main slot directly in <revision>.
    text_element = ("revision", "text")

    def start(name: str, attrs: dict[str, str]) -> None:
        nonlocal fields, page, consume, redirected
        tag = name.rsplit(" ", 1)[-1]
        stack.append(tag)
        if stack == ["mediawiki", "page"]:
            fields = {}
            page = None
            consume = None
            redirected = False
        elif stack == ["mediawiki", "page", "redirect"]:
            redirected = True
        elif stack == ["mediawiki", "page", "revision"]:
            if page is not None:
                raise ValueError("expected a current-revision-only pages-articles dump")
            page = Page(int(fields["page:id"]), fields["page:title"], int(fields["page:ns"]), redirected)
            consume = select(page)
        pair = tuple(stack[-2:])
        if pair in metadata and (pair not in revision_fields or consume is not None):
            field_parts.clear()
            parser.CharacterDataHandler = field_parts.append
        elif pair == text_element and "deleted" not in attrs:
            if consume is not None and accept_revision is not None:
                assert page is not None
                if not accept_revision(page, int(fields["revision:id"])):
                    consume = None
            parser.CharacterDataHandler = consume

    def end(_: str) -> None:
        pair = tuple(stack[-2:])
        if pair in metadata and (pair not in revision_fields or consume is not None):
            value = "".join(field_parts)
            if pair == ("siteinfo", "dbname") and value != "hewikisource":
                raise ValueError("expected the hewikisource XML export")
            fields[":".join(pair)] = value
            parser.CharacterDataHandler = None
        elif pair == text_element:
            parser.CharacterDataHandler = None
        elif pair == ("page", "revision") and consume is not None:
            assert page is not None
            finish(page, int(fields["revision:id"]), fields.get("revision:model", ""), fields.get("revision:format", ""))
        stack.pop()

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    # No XML dictionaries or entity expansion outside the XML's built-ins.
    def reject_doctype(*_: object) -> None:
        raise ValueError("unexpected XML doctype")

    parser.StartDoctypeDeclHandler = reject_doctype
    with bz2.open(path, "rb") as handle:
        while block := handle.read(1024 * 1024):
            parser.Parse(block, False)
        parser.Parse(b"", True)


# Extract only ProofreadPage references in main-namespace markup. Retain a
# short open tag across XML callbacks but never collect an article's prose.
_REFERENCE = re.compile(r"<pages(?=[\s/>])[^<>]*>|\{\{\s*:?\s*(?:Page|עמוד)\s*:[^{}|\n]+", re.I)
_REFERENCE_START = re.compile(r"<pages\b[^<>]*$|\{\{[^{}\n]*$", re.I)
_INDEX_ATTR = re.compile(r'''\sindex\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s>]+?)(?=\s|/?>))''', re.I)


class References:
    def __init__(self) -> None:
        self.indexes: set[str] = set()
        self.tail = ""

    def feed(self, chunk: str) -> None:
        chunk = self.tail + chunk
        stop = 0
        for match in _REFERENCE.finditer(chunk):
            token = match[0]
            if token.startswith("{{"):
                # Do not treat a reference split at the callback boundary as
                # complete until its first pipe or closing brace arrives.
                if match.end() == len(chunk):
                    break
                title = token.split(":", 1)[1].lstrip(": ")
                if ":" in title and title.split(":", 1)[0].casefold() in {"page", "עמוד"}:
                    title = title.split(":", 1)[1]
                self.indexes.add(page_scan(title))
            elif attr := _INDEX_ATTR.search(token):
                self.indexes.add(index_scan(unescape(next(value for value in attr.groups() if value is not None))))
            stop = match.end()
        suffix = chunk[max(stop, len(chunk) - 8192):]
        partial = _REFERENCE_START.search(suffix)
        self.tail = partial[0] if partial else suffix[-6:]


def title_key(title: str) -> str:
    return unicodedata.normalize("NFC", " ".join(title.replace("_", " ").split()))


def index_scan(title: str) -> str:
    title = title_key(title)
    prefix, sep, body = title.partition(":")
    scan = title_key(body) if sep and prefix.casefold() in {"index", "מפתח", "file", "קובץ"} else title
    return scan[:1].upper() + scan[1:]


def page_scan(title: str) -> str:
    title = title_key(title)
    prefix, sep, body = title.partition(":")
    if sep and prefix.casefold() in {"page", "עמוד"}:
        title = title_key(body)
    scan, sep, number = title.rpartition("/")
    return index_scan(scan if sep and number.isascii() and number.isdecimal() else title)

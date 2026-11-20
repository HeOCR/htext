"""Reviewed booklet provenance and text selection for Open Law Book."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from htext.hebrew import nfc, strip_marks
from htext.wikisource.dump import title_key

SCHEMA = "htext_wikisource_law_sources.v1"
REFERENCE_SHA256 = "790099a2e64c2e391957a2c9f306c6a8c0addd087cfd8431666165f5b4f65de1"
_BOOKLET = re.compile(r"(?:sefer_hachukim|kovetz_hatakanot|yalkut_hapirsumim|chukei_taktziv)_[1-9][0-9]*")


def load_sources(path: Path) -> dict[int, tuple[int, frozenset[str]]]:
    """Article IDs map to a reviewed revision and all its source booklets."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise ValueError(f"expected {SCHEMA} for Open Law Book provenance")
    articles = document.get("articles")
    if not isinstance(articles, list) or not articles:
        raise ValueError("Open Law Book provenance requires a nonempty articles list")
    result = {}
    for row in articles:
        if not isinstance(row, dict):
            raise ValueError("invalid Open Law Book provenance entry")
        article_id, revision_id, booklets = (row.get(key) for key in ("page_id", "revision_id", "booklets"))
        if any(type(value) is not int or value < 1 for value in (article_id, revision_id)) or article_id in result:
            raise ValueError("Open Law Book provenance requires unique page IDs and positive revision IDs")
        if not isinstance(booklets, list) or not booklets or any(
            not isinstance(unit, str) or not _BOOKLET.fullmatch(unit) for unit in booklets
        ):
            raise ValueError("Open Law Book provenance requires canonical Reshumot booklet IDs")
        result[article_id] = (revision_id, frozenset(booklets))
    return result


def line_key(line: str) -> str:
    return strip_marks(nfc(line))


def reference_lines(path: Path) -> set[str]:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != REFERENCE_SHA256:
        raise ValueError("--knesset-laws-v2 must match the published v2 text SHA-256")
    return {line_key(line) for line in raw.decode("utf-8").splitlines()}


def clause_bodies(code):
    """Yield clause wikitext while omitting publication notes and signatures."""
    import mwparserfromhell
    from mwparserfromhell import nodes

    categories = {
        title_key(str(link.title)).casefold().removeprefix("category:").removeprefix("קטגוריה:")
        for link in code.filter_wikilinks(recursive=False)
        if title_key(str(link.title)).casefold().startswith(("category:", "קטגוריה:"))
    }
    if "בוט חוקים" not in categories:
        return
    active = False
    body = []
    for node in code.nodes:
        if isinstance(node, nodes.Template):
            name = title_key(str(node.name)).removeprefix("תבנית:")
            if name in {"ח:חתימות", "ח:סוף"}:
                break
            if name in {"ח:סעיף", "ח:קטע2", "ח:קטע3", "ח:מאגר", "ח:פתיח-התחלה"}:
                if body:
                    yield mwparserfromhell.wikicode.Wikicode(body)
                    body = []
                active = name == "ח:סעיף"
                continue
        if active:
            body.append(node)
    if body:
        yield mwparserfromhell.wikicode.Wikicode(body)

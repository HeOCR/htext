"""Extract text and explicit rights evidence from ProofreadPage revisions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import unescape
from typing import Iterator

import mwparserfromhell
from mwparserfromhell import nodes
from mwparserfromhell.wikicode import Wikicode

from htext.hebrew import OTHER_MARKS
from htext.pby.text import normalise
from htext.wikisource.dump import title_key

_HEADER = re.compile(r"\A\s*<noinclude>(.*?)</noinclude>", re.I | re.S)
_FOOTER = re.compile(r"<noinclude>((?:(?!<noinclude>).)*?)</noinclude>\s*\Z", re.I | re.S)
_QUALITY = re.compile(r'''\A\s*<pagequality\s+level\s*=\s*["']([0-4])["'][^>]*>''', re.I)

# Exact positive labels. A scan licence, PD-US-only label, or generic copyright
# category does not establish rights to the underlying Hebrew work.
_PD = {"נחלת הכלל", "רשות הציבור", "pd-israel", "pd-old", "pd-old-70", "pd-old-100"}
_FREE = {"cc0", "cc-zero", "cc-by-sa-4.0", "cc by-sa 4.0"}
_RESTRICTED = re.compile(r"\bcc[- ]by[- ](?:nc|nd)\b|all rights reserved|כל הזכויות שמורות|שימוש הוגן", re.I)
_DEATH_FIELDS = {"שנת פטירה", "שנת פטירת המחבר", "death year", "deathyear"}
_RIGHTS_TEMPLATES = _PD | _FREE | {"זכויות יוצרים", "רישיון", "רשיון"}


@dataclass(frozen=True)
class ProofreadPage:
    quality: int
    header: str
    body: str
    footer: str


def proofread_page(raw: str, model: str, content_format: str) -> ProofreadPage | None:
    if model != "proofread-page":
        return None
    if content_format == "application/json":
        try:
            data = json.loads(raw)
            quality = data["level"]["level"]
            sections = (data["header"], data["body"], data["footer"])
        except (KeyError, TypeError, ValueError):
            return None
        if type(quality) is int and quality in (3, 4) and all(isinstance(value, str) for value in sections):
            return ProofreadPage(quality, *sections)
        return None
    if content_format != "text/x-wiki" or not (header := _HEADER.match(raw)):
        return None
    if not (quality_match := _QUALITY.match(header[1])) or quality_match[1] not in {"3", "4"}:
        return None
    body = raw[header.end():]
    footer = _FOOTER.search(body)
    return ProofreadPage(int(quality_match[1]), header[1][quality_match.end():], body[:footer.start()] if footer else body, footer[1] if footer else "")


def _markings(code: Wikicode, *, as_of: int) -> tuple[set[tuple[str, str]], bool]:
    found: set[tuple[str, str]] = set()
    restrictive = False
    for node in code.nodes:
        if isinstance(node, nodes.Template):
            name = title_key(str(node.name))
            key = name.removeprefix("תבנית:").casefold()
            restrictive |= bool(_RESTRICTED.search(key))
            if key in _PD | _FREE:
                found.add(("template", name))
            if key in _RIGHTS_TEMPLATES:
                for param in node.params:
                    name_key = title_key(str(param.name)).casefold()
                    value = str(param.value).strip()
                    restrictive |= bool(_RESTRICTED.search(value))
                    if name_key in _DEATH_FIELDS and re.fullmatch(r"[0-9]{4}", value):
                        if int(value) <= as_of - 71:
                            found.add(("template", f"{name}: {name_key}={value}"))
                        else:
                            restrictive = True
        elif isinstance(node, nodes.Wikilink):
            title = title_key(str(node.title))
            prefix, separator, name = title.partition(":")
            if separator and prefix.casefold() in {"קטגוריה", "category"}:
                restrictive |= bool(_RESTRICTED.search(name))
                if name.casefold() in _PD | _FREE:
                    found.add(("category", name))
    return found, restrictive


def rights_basis(page: ProofreadPage, body: Wikicode, *, as_of: int) -> list[dict[str, str]]:
    found: set[tuple[str, str]] = set()
    for part in (mwparserfromhell.parse(page.header), body, mwparserfromhell.parse(page.footer)):
        markers, restrictive = _markings(part, as_of=as_of)
        if restrictive:
            return []
        found.update(markers)
    return [{"kind": kind, "marking": name} for kind, name in sorted(found)]


_INLINE = {"b", "big", "em", "i", "small", "span", "strong", "u"}
_BLOCK = {"blockquote", "center", "div", "p", "poem"}
_BLOCKED_CLASS = re.compile(r"\b(?:navbox|navigation|noprint|metadata|toc|mw-editsection|hatnote)\b", re.I)
_MAGIC_WORD = re.compile(r"__[A-Z]+__")
_NAV_HEADINGS = {"ניווט", "ראו גם", "קישורים חיצוניים", "תוכן עניינים", "הערות שוליים"}
_UNPARSED_EXCLUSION = re.compile(r"<\s*(?:ref(?:erences)?|noinclude|includeonly)(?=[\s/>]|$)|\{\{", re.I)


def _visible(code: Wikicode) -> Iterator[str]:
    navigation_level = None
    for node in code.nodes:
        if isinstance(node, nodes.Heading):
            if navigation_level is None or node.level <= navigation_level:
                navigation_level = node.level if str(node.title).strip() in _NAV_HEADINGS else None
            yield "\n"
        elif navigation_level is not None:
            continue
        elif isinstance(node, nodes.Text):
            literal = str(node)
            if unparsed := _UNPARSED_EXCLUSION.search(literal):
                # Unclosed editor markup cannot safely be distinguished from
                # the remaining body. Retain only text before the opener.
                yield literal[:unparsed.start()]
                return
            yield literal
        elif isinstance(node, nodes.HTMLEntity):
            yield node.normalize()
        elif isinstance(node, nodes.Wikilink):
            target = str(node.title).strip()
            if ":" not in target and not target.startswith("#"):
                yield from _visible(node.text if node.text is not None else node.title)
        elif isinstance(node, nodes.Tag):
            tag = str(node.tag).casefold()
            hidden = bool(node.has("class") and _BLOCKED_CLASS.search(str(node.get("class").value)))
            hidden |= bool(node.has("style") and re.search(r"display\s*:\s*none", str(node.get("style").value), re.I))
            if hidden:
                yield " "
            elif tag in _INLINE and node.contents is not None:
                yield from _visible(node.contents)
            elif tag in _BLOCK and node.contents is not None:
                yield "\n"
                yield from _visible(node.contents)
                yield "\n"
            elif tag in {"br", "hr", "table", "ul", "li", "ol"}:
                yield "\n"
            else:
                yield " "
        elif not isinstance(node, nodes.Comment):
            # Templates (including transclusions), parameters and external links.
            yield " "


def text_lines(body: Wikicode) -> Iterator[str]:
    text = "".join(_visible(body)).translate(str.maketrans("", "", "".join(OTHER_MARKS)))
    for line in _MAGIC_WORD.sub("", text).splitlines():
        if cleaned := normalise(unescape(line), strip_references=False):
            yield cleaned


def converted_article(body: Wikicode) -> bool:
    """Identify the conversion templates excluded from main-namespace text."""
    return any(
        title_key(str(template.name)).removeprefix("תבנית:") in {"המרת או.סי.אר", "הוסב אוטומטית מהקלדה"}
        for template in body.filter_templates()
    )

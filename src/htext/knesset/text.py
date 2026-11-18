"""Turn the text of one enacted law (its Word file, extracted to plain text) into paragraphs.

The Word files hold the OCR text of the printed page, one printed line per line,
in reading order. A page has:

- a running header, ``<page> ספר החוקים <booklet> <Hebrew date> <dd.mm.yyyy>``;
- body text in long lines, each section opening with its number (``3.``);
- margin notes (section headings) as short lines between sections;
- footnotes, which open with ``*`` (the law's own note) or with a citation
  (``1 ס"ח ...``), and the printer's line.

Paragraphs are cut at blank lines, page headers and section openings. Inside a
paragraph, the body runs to its last long line or its last line that ends a
sentence; short lines after that are a margin note and become a paragraph of
their own, so a heading is never glued into running text. Footnotes, headers
and the printer's line are dropped.

OCR fixes (each counted on the card):

- an apostrophe after a word of three or more letters, before a space or the
  end of the line, is the OCR reading of a comma (``ישראל' סכום``);
- a doubled apostrophe between letters is gershayim (``בה''ח``);
- a lone one- or two-digit token after a law's year (``תשי"א-1951 1 (להלן``) is a
  footnote reference and is removed;
- a section number at the start of a paragraph is removed, because the OCR
  often misreads its punctuation (``3,``, ``.4 .``).

Everything else stays as the OCR read it; the lexicon filter and the eye check
deal with the rest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator, Sequence

from htext.pby.text import normalise

# A line shorter than this is a margin-note candidate.
SHORT_LINE_CHARS = 30

_PAGE_HEADER = re.compile(r"ספר החוקים\s*\d+.*\d{1,2}\.\d{1,2}\.\d{2,4}")
_WIDE_GAP = re.compile(r"\S\s{8,}\S")
_PRINTER = re.compile(r"נדפס\s+בדפוס\s+הממשלה|הודפס\s+בדפוס")
_FOOTNOTE_START = re.compile(
    r'^(\*|\d{1,2}\s+(ס"ח|ק"ת|ע"ר|ה"ח|ס״ח|ק״ת|ע״ר|ה״ח|דיני מדינת ישראל|ספר החוקים|קובץ התקנות|עיתון רשמי|תוספת))'
)
# A section opening: "3.", "3,", ".4 .", "12א.", "14. " at the start of a line.
_SECTION_START = re.compile(r"^[.,]?\s*\d{1,3}[א-ת]?\s*[.,](?=\s|\S)")
_SECTION_LABEL = re.compile(r"^[.,]?\s*\d{1,3}[א-ת]?\s*[.,]\s*")
_SENTENCE_END = re.compile(r"[.:;][\"'”’״׳)]*$")
_COMMA_APOSTROPHE = re.compile(r"(?<=[א-ת]{3})'(?=\s|$)")
_DOUBLE_APOSTROPHE = re.compile(r"(?<=[א-ת])''(?=[א-ת])")
_FOOTNOTE_REFERENCE = re.compile(r"(?<=-\d{4}) \d{1,2}(?=\s|$|[,.;:)])")
# The law's own footnote mark, after its title.
_STAR = re.compile(r"\s*\*+(?=\s|$)")
_LEADING_DASH = re.compile(r"^[-–—]+\s*")


@dataclass(frozen=True)
class Paragraph:
    text: str
    kind: str  # "body" or "note"


def _is_header(line: str) -> bool:
    return bool(_PAGE_HEADER.search(line) and (_WIDE_GAP.search(line) or line.lstrip()[:1].isdigit() or "\t" in line))


def _blocks(lines: Sequence[str], stats: dict[str, int]) -> Iterator[list[str]]:
    """Runs of kept lines, cut at blank lines, headers, footnotes and section openings."""

    block: list[str] = []
    in_footnote = False
    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            in_footnote = False
            if block:
                yield block
                block = []
            continue
        if _is_header(line):
            stats["lines_dropped:page_header"] = stats.get("lines_dropped:page_header", 0) + 1
            in_footnote = False
            if block:
                yield block
                block = []
            continue
        if _PRINTER.search(stripped):
            stats["lines_dropped:printer"] = stats.get("lines_dropped:printer", 0) + 1
            continue
        if _FOOTNOTE_START.match(stripped):
            in_footnote = True
            if block:
                yield block
                block = []
        if in_footnote:
            stats["lines_dropped:footnote"] = stats.get("lines_dropped:footnote", 0) + 1
            continue
        if _SECTION_START.match(stripped) and block:
            yield block
            block = []
        line_text = _STAR.sub("", stripped).strip()
        if line_text:
            block.append(line_text)
    if block:
        yield block


def _split_block(block: list[str]) -> list[Paragraph]:
    """Body lines first, then any trailing short lines as a margin note."""

    last_body = -1
    for index, line in enumerate(block):
        if len(line) >= SHORT_LINE_CHARS or _SENTENCE_END.search(line):
            last_body = index
    out = []
    if last_body >= 0:
        out.append(Paragraph(" ".join(block[: last_body + 1]), "body"))
    if last_body < len(block) - 1:
        out.append(Paragraph(" ".join(block[last_body + 1 :]), "note"))
    return out


def fix_ocr(text: str, stats: dict[str, int]) -> str:
    for name, pattern, replacement in (
        ("double_apostrophe", _DOUBLE_APOSTROPHE, '"'),
        ("apostrophe_comma", _COMMA_APOSTROPHE, ","),
        ("footnote_reference", _FOOTNOTE_REFERENCE, ""),
    ):
        text, count = pattern.subn(replacement, text)
        if count:
            stats[f"ocr_fix:{name}"] = stats.get(f"ocr_fix:{name}", 0) + count
    return text


def paragraphs(text: str, stats: dict[str, int] | None = None) -> list[Paragraph]:
    """The kept paragraphs of one law, normalised and with the OCR fixes applied."""

    stats = {} if stats is None else stats
    lines = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", "\n").split("\n")
    out = []
    for block in _blocks(lines, stats):
        for paragraph in _split_block(block):
            body = paragraph.text
            if paragraph.kind == "note":
                body = _LEADING_DASH.sub("", body)
            if paragraph.kind == "body":
                body, count = _SECTION_LABEL.subn("", body, count=1)
                if count:
                    stats["section_labels_removed"] = stats.get("section_labels_removed", 0) + 1
            body = normalise(fix_ocr(body, stats), strip_references=False)
            if body:
                out.append(Paragraph(body, paragraph.kind))
                stats[f"paragraphs:{paragraph.kind}"] = stats.get(f"paragraphs:{paragraph.kind}", 0) + 1
    return out

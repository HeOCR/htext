"""Build the ``gutenberg`` corpus: Project Gutenberg's public-domain Hebrew texts (htext-cc0).

The works are pinned in ``data/gutenberg/sources.v1.json``: each with its PG number, the pglaf mirror URL, the sha256 of
the fetched plain-text file, and every contributor with a death year. A work enters only when every contributor
(author, translator, compiler, editor) died in or before ``as_of - 71`` (the PBY rule for Israel); a work with an
unknown death year is out, and the manifest lists why. PG's US public-domain status is recorded per work.

Text rules:

- only the text between PG's ``*** START OF`` and ``*** END OF`` markers is read, so PG's licence boilerplate is never
  in the corpus (PG is credited on the card instead);
- paragraphs are the blank-line-separated blocks; a block whose first line is indented by at least 8 spaces and short
  is a heading of its own;
- footnote blocks (``[1] ...``), emphasis markup (``*...*``, ``_..._``) and footnote marks (``[1]``) are removed;
- each paragraph is cut by the S10b length profile and the PBY character and niqqud rules, into a plain and a pointed
  file, as PBY is; exact duplicates are dropped, and so are lines listed in ``--dedup-against`` files (other htext
  corpora in the same release tranche).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from htext import __version__
from htext.hebrew import strip_marks
from htext.leakage import Protected, sha256_text
from htext.pby.build import PROFILE_TARGETS, length_profile, profile_passes
from htext.pby.text import DEFAULT_NIQQUD_THRESHOLD, MAX_LINE_CHARS, LengthSampler, choose_segment, normalise, word_spans
from htext.release import Credit, ReleaseGuard, release_fields
from htext.reservations import Reservations

SOURCE = "gutenberg"
SOURCE_LICENCE = "Public Domain"
CREDIT = Credit("Project Gutenberg", "https://www.gutenberg.org")
SOURCES_SCHEMA = "htext_gutenberg_sources.v1"
CARD_SCHEMA = "gutenberg_corpus_card.v1"
RIGHTS_SCHEMA = "gutenberg_rights_index.v1"
RIGHTS_INDEX_FILE = "gutenberg_rights_index.v1.jsonl.gz"
LINE_INDEX_FILE = "gutenberg_line_index.v1.jsonl.gz"
DEFAULT_CORPUS_VERSION = "v1"
SUBSETS = ("plain", "niqqud")

_START = re.compile(r"^\*\*\* ?START OF (THE|THIS) PROJECT GUTENBERG.*$", re.M)
_END = re.compile(r"^\*\*\* ?END OF (THE|THIS) PROJECT GUTENBERG.*$", re.M)
_FOOTNOTE_BLOCK = re.compile(r"^\s*\[\d+\]")
_FOOTNOTE_MARK = re.compile(r"\[\d+\]")
_EMPHASIS = re.compile(r"[*_]")
_HEBREW = re.compile(r"[א-ת]")
HEADING_INDENT = 8
HEADING_MAX_CHARS = 60


def corpus_file_name(subset: str, version: str = DEFAULT_CORPUS_VERSION) -> str:
    return f"gutenberg_lines_{subset}_{version}.txt"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def body(text: str) -> str:
    """The text between PG's START and END markers; refuses a file without both."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    start, end = _START.search(text), _END.search(text)
    if not start or not end or end.start() <= start.end():
        raise ValueError("no Project Gutenberg START/END markers")
    return text[start.end():end.start()]


@dataclass(frozen=True)
class Paragraph:
    text: str
    kind: str  # "body" or "heading"


def paragraphs(text: str, stats: Counter | None = None) -> list[Paragraph]:
    stats = Counter() if stats is None else stats
    out: list[Paragraph] = []
    for block in re.split(r"\n\s*\n", body(text)):
        raw = [line for line in block.split("\n") if line.strip()]
        if not raw:
            continue
        if _FOOTNOTE_BLOCK.match(raw[0]):
            stats["blocks_dropped:footnote"] += 1
            continue
        if not any(_HEBREW.search(line) for line in raw):
            stats["blocks_dropped:no_hebrew"] += 1
            continue
        heading = len(raw[0]) - len(raw[0].lstrip(" ")) >= HEADING_INDENT and len(raw[0].strip()) <= HEADING_MAX_CHARS
        if heading:
            # Centred title-page and section lines: each its own heading.
            for line in raw:
                cleaned = normalise(_EMPHASIS.sub("", _FOOTNOTE_MARK.sub("", line)).strip(), strip_references=False)
                if cleaned and _HEBREW.search(cleaned):
                    out.append(Paragraph(cleaned, "heading"))
                    stats["paragraphs:heading"] += 1
            continue
        joined = " ".join(line.strip() for line in raw)
        cleaned = normalise(_EMPHASIS.sub("", _FOOTNOTE_MARK.sub("", joined)), strip_references=False)
        if cleaned:
            out.append(Paragraph(cleaned, "body"))
            stats["paragraphs:body"] += 1
    return out


@dataclass
class GutenbergConfig:
    sources: Path  # data/gutenberg/sources.v1.json
    inputs: Path  # dir holding pg<N>.txt as fetched
    output: Path
    length_profile: Sequence[int]
    length_profile_source: str
    reservations: Sequence[Path]
    leakage_fixtures: Sequence[Path] = ()
    dedup_against: Sequence[Path] = ()
    as_of: int = 2026
    seed: int = 15
    corpus_version: str = DEFAULT_CORPUS_VERSION
    niqqud_threshold: float = DEFAULT_NIQQUD_THRESHOLD
    allow_maqaf: bool = False
    fit: Callable[[str], str | None] | None = None
    fit_provenance: dict[str, Any] = field(default_factory=dict)


def eligible(work: dict[str, Any], as_of: int) -> tuple[bool, str]:
    years = [c.get("death_year") for c in work["contributors"]]
    if not years or any(y is None for y in years):
        return False, "contributor_death_unknown"
    if max(years) > as_of - 71:
        return False, f"contributor_died_after:{as_of - 71}"
    return True, f"all_contributors_died_by:{as_of - 71}"


def _dedup_set(paths: Iterable[Path]) -> set[str]:
    seen: set[str] = set()
    for p in paths:
        with (gzip.open(p, "rt", encoding="utf-8") if p.suffix == ".gz" else p.open(encoding="utf-8")) as f:
            for line in f:
                if line.strip():
                    seen.add(strip_marks(line.rstrip("\n")))
    return seen


def build(config: GutenbergConfig) -> dict[str, Any]:
    sources = json.loads(config.sources.read_text(encoding="utf-8"))
    if sources.get("schema") != SOURCES_SCHEMA:
        raise ValueError(f"{config.sources}: expected schema {SOURCES_SCHEMA!r}")
    reservations = Reservations.load(config.reservations)
    protected = Protected.load(config.leakage_fixtures)
    against = _dedup_set(config.dedup_against)
    stats: Counter = Counter()
    seen = {s: set() for s in SUBSETS}
    lines: dict[str, list[dict[str, Any]]] = {s: [] for s in SUBSETS}
    records, out_list = [], []
    for work in sorted(sources["works"], key=lambda w: w["pg"]):
        if work.get("exclude"):
            # A reviewed reason in the sources file: audio only, already released in another htext corpus, ...
            out_list.append({"pg": work["pg"], "title": work["title"], "reason": work["exclude"]})
            continue
        ok, basis = eligible(work, config.as_of)
        if not ok:
            out_list.append({"pg": work["pg"], "title": work["title"], "reason": basis})
            continue
        if reservations.reserved("gutenberg", str(work["pg"])):
            out_list.append({"pg": work["pg"], "title": work["title"], "reason": "eval_reserved"})
            continue
        path = config.inputs / f"pg{work['pg']}.txt"
        if _sha256(path) != work["sha256"]:
            raise ValueError(f"{path}: sha256 does not match the pinned sources")
        sampler = LengthSampler(config.length_profile, f"{config.seed}:gutenberg:{work['pg']}")
        n_before = {s: len(lines[s]) for s in SUBSETS}
        for para in paragraphs(path.read_text(encoding="utf-8"), stats):
            words = para.text.split()
            plain_words = [strip_marks(w) for w in words]
            spans = [(0, len(words))] if para.kind == "heading" else word_spans(plain_words, verse=False, targets=sampler)
            for start, end in spans:
                stats["segments"] += 1
                pointed = " ".join(words[start:end])
                plain = " ".join(plain_words[start:end])
                if para.kind == "heading" and len(plain) > MAX_LINE_CHARS:
                    stats["segments_dropped:too_long"] += 1
                    continue
                segment, why = choose_segment(pointed, plain, threshold=config.niqqud_threshold, allow_maqaf=config.allow_maqaf)
                if segment is None:
                    stats[f"segments_dropped:{why}"] += 1
                    continue
                if leak := protected.leak(segment.text, segment.plain_form):
                    stats[f"segments_dropped:leak_{leak}"] += 1
                    continue
                if segment.plain_form in against:
                    stats["segments_dropped:in_other_corpus"] += 1
                    continue
                if config.fit is not None and (failure := config.fit(segment.text)):
                    stats[f"segments_dropped:fit:{failure}"] += 1
                    continue
                if segment.text in seen[segment.subset]:
                    stats["segments_dropped:duplicate"] += 1
                    continue
                seen[segment.subset].add(segment.text)
                lines[segment.subset].append({"text": segment.text, "pg": work["pg"], "kind": para.kind})
        counts = {s: len(lines[s]) - n_before[s] for s in SUBSETS}
        records.append({
            "entry_id": f"gutenberg:{work['pg']}", "pg": work["pg"], "title": work["title"],
            "contributors": work["contributors"], "mirror_url": work["mirror_url"], "sha256": work["sha256"],
            "catalogue_sha256": sources["catalogue"]["sha256"], "lines": counts,
            "pd_israel": True, "pd_israel_basis": basis, "pd_us": True, "pd_us_basis": "project_gutenberg_us_public_domain",
            "as_of": config.as_of, "source": SOURCE,
            **release_fields(source_licence=SOURCE_LICENCE, credit=CREDIT),
        })
    guard = ReleaseGuard("cc0")
    guard.admit_all(records)
    config.output.mkdir(parents=True, exist_ok=True)
    files = {}
    for s in SUBSETS:
        name = corpus_file_name(s, config.corpus_version)
        (config.output / name).write_text("".join(l["text"] + "\n" for l in lines[s]), encoding="utf-8")
        prof = length_profile([len(l["text"]) for l in lines[s]]) if lines[s] else {}
        files[name] = {"subset": s, "lines": len(lines[s]), "sha256": _sha256(config.output / name),
                       "bytes": (config.output / name).stat().st_size, "length_profile": prof,
                       "length_profile_passes": profile_passes(prof) if lines[s] else {}}
    with gzip.open(config.output / LINE_INDEX_FILE, "wt", encoding="utf-8") as f:
        for s in SUBSETS:
            for l in lines[s]:
                f.write(json.dumps({"subset": s, "pg": l["pg"], "kind": l["kind"], "sha256": sha256_text(l["text"])}, sort_keys=True) + "\n")
    with gzip.open(config.output / RIGHTS_INDEX_FILE, "wt", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    card = {
        "schema": CARD_SCHEMA, "name": "Project Gutenberg public-domain Hebrew texts",
        "builder": {"package": "htext", "version": __version__}, "credit": CREDIT.as_dict(),
        "licence": {"outputs": "CC0-1.0", "source": SOURCE_LICENCE}, "htext_release": guard.release, "release": guard.summary(),
        "text_quality": "transcription", "source_tag": SOURCE,
        "source": {"catalogue": sources["catalogue"], "sources_sha256": _sha256(config.sources)},
        "works": [{"pg": r["pg"], "title": r["title"], "lines": r["lines"]} for r in records],
        "out": out_list,
        "inputs": {"eval_reservations": reservations.card(), "leakage_fixtures": protected.sources,
                   "dedup_against": [{"file": p.name, "sha256": _sha256(p)} for p in config.dedup_against],
                   "length_profile_source": config.length_profile_source,
                   "fit_check": config.fit_provenance if config.fit is not None else {"ran": False}},
        "corpus_version": config.corpus_version,
        "parameters": {"as_of": config.as_of, "seed": config.seed, "niqqud_threshold": config.niqqud_threshold, "max_line_chars": MAX_LINE_CHARS},
        "files": files, "pipeline": dict(sorted(stats.items())),
        "length_profile_targets": {k: list(v) if isinstance(v, tuple) else v for k, v in PROFILE_TARGETS.items()},
    }
    (config.output / "corpus_card.json").write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (config.output / "CORPUS_CARD.md").write_text(render_card(card), encoding="utf-8")
    names = sorted(p.name for p in config.output.iterdir() if p.is_file() and p.name != "SHA256SUMS")
    (config.output / "SHA256SUMS").write_text("".join(f"{_sha256(config.output / n)}  {n}\n" for n in names), encoding="utf-8")
    return card


def render_card(card: dict[str, Any]) -> str:
    out = [f"# {card['name']}", "",
           f"- **Release:** `htext-cc0` (CC0-1.0); source licence `{card['licence']['source']}`. Source tag `{card['source_tag']}`.",
           f"- **Credit:** {card['credit']['text']} ({card['credit']['url']}). The PG licence text is not part of the corpus.",
           f"- **Catalogue:** `{card['source']['catalogue']['file']}`, sha256 `{card['source']['catalogue']['sha256']}`.",
           "", "## Works", "", "| PG | Title | Plain lines | Pointed lines |", "| ---: | --- | ---: | ---: |"]
    out += [f"| {w['pg']} | {w['title']} | {w['lines']['plain']:,} | {w['lines']['niqqud']:,} |" for w in card["works"]]
    out += ["", "## Left out", "", "| PG | Title | Reason |", "| ---: | --- | --- |"]
    out += [f"| {o['pg']} | {o['title']} | `{o['reason']}` |" for o in card["out"]]
    out += ["", "## Files", "", "| File | Lines | sha256 |", "| --- | ---: | --- |"]
    out += [f"| `{n}` | {i['lines']:,} | `{i['sha256']}` |" for n, i in card["files"].items()]
    out.append("")
    return "\n".join(out)

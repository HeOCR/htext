"""Build the ``tanakh`` corpus: the Westminster Leningrad Codex (WLC), as the Open Scriptures Hebrew Bible keeps it.

Source: ``openscriptures/morphhb`` at a pinned commit (``WLC_COMMIT``), the
OSIS files in ``wlc/``. They carry WLC 4.20. tanach.us's UXLC was the first
choice, but its robots file disallows automated fetching (heocr-lead,
2026-11-18), so htext takes the WLC from GitHub.

Rights. The Leningrad Codex is about a thousand years old, and the WLC text
is in the public domain: the files' ``<work osisWork="WLC">`` record says
``Public Domain``, and OSHB's README says the WLC text "remains in the Public
Domain". OSHB's own lemma and morphology layers are CC BY 4.0. This builder
reads only the words, never the ``lemma``, ``morph`` or ``n`` attributes, and
removes OSHB's ``/`` morpheme dividers, so no CC BY data reaches the corpus.

Text, per verse:

- the written text (ketiv) as printed; marginal readings (qere), alternative
  accents and editorial notes are in ``<note>`` elements, which are skipped;
- maqaf joins two words into one token; sof pasuq, paseq, the reversed nun and
  the open and closed section markers (pe, samekh) are removed;
- two forms of every verse: **niqqud**, with the S10b vowel points (cantillation,
  meteg, rafe and the upper and lower dots removed), and **plain**, with every
  mark removed;
- each verse is packed into lines at word boundaries, to the S10b length
  profile, as PBY prose is; a line never crosses a verse, and both forms are cut
  at the same words. (The sources plan said "like PBY poetry"; balanced verse
  halves left the median line at 38 characters, outside the S10b targets.)

Each line passes the PBY character rules, the leakage check (line and word
3-grams, in either form), deduplication within its file, and the hocrsyngen
wrap check. A line dropped in one form is dropped in the other too, so the two
files hold the same verses.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from htext import __version__
from htext.hebrew import MAQAF, NIQQUD_CHARSET, OTHER_MARKS, PLAIN_CHARSET, has_medial_final_form, hebrew_letter_count, nfc, strip_marks
from htext.leakage import Protected, sha256_text
from htext.pby.build import PROFILE_TARGETS, length_profile, profile_passes
from htext.pby.text import MAX_LINE_CHARS, LengthSampler, word_spans
from htext.release import Credit, ReleaseGuard, release_fields
from htext.reservations import Reservations

SOURCE = "tanakh"
SOURCE_LICENCE = "Public Domain"
WLC_REPOSITORY = "openscriptures/morphhb"
WLC_COMMIT = "db6c5c9b46b8f39346f10915ddb1a70dcd429901"
CREDIT = Credit(
    "Westminster Leningrad Codex (public domain), via the Open Scriptures Hebrew Bible", "https://github.com/openscriptures/morphhb"
)
PD_STATEMENTS = (
    {"where": "README.md", "text": "The text of the WLC remains in the Public Domain."},
    {"where": "LICENSE.md", "text": "This work is based on The Westminster Leningrad Codex, which is in the public domain."},
    {"where": 'wlc/*.xml <work osisWork="WLC">', "text": "<rights>Public Domain</rights>"},
)
CARD_SCHEMA = "tanakh_corpus_card.v1"
RIGHTS_SCHEMA = "tanakh_rights_index.v1"
LINE_INDEX_SCHEMA = "tanakh_line_index.v1"
RIGHTS_INDEX_FILE = "tanakh_rights_index.v1.jsonl.gz"
LINE_INDEX_FILE = "tanakh_line_index.v1.jsonl.gz"
DEFAULT_CORPUS_VERSION = "v1"
SUBSETS = ("niqqud", "plain")

OSIS = "{http://www.bibletechnologies.net/2003/OSIS/namespace}"
# Books in the order of the Leningrad Codex (Chronicles opens the Writings), with their Hebrew names.
BOOKS: tuple[tuple[str, str], ...] = (
    ("Gen", "בראשית"), ("Exod", "שמות"), ("Lev", "ויקרא"), ("Num", "במדבר"), ("Deut", "דברים"),
    ("Josh", "יהושע"), ("Judg", "שופטים"), ("1Sam", "שמואל א"), ("2Sam", "שמואל ב"), ("1Kgs", "מלכים א"), ("2Kgs", "מלכים ב"),
    ("Isa", "ישעיהו"), ("Jer", "ירמיהו"), ("Ezek", "יחזקאל"), ("Hos", "הושע"), ("Joel", "יואל"), ("Amos", "עמוס"),
    ("Obad", "עובדיה"), ("Jonah", "יונה"), ("Mic", "מיכה"), ("Nah", "נחום"), ("Hab", "חבקוק"), ("Zeph", "צפניה"),
    ("Hag", "חגי"), ("Zech", "זכריה"), ("Mal", "מלאכי"),
    ("1Chr", "דברי הימים א"), ("2Chr", "דברי הימים ב"), ("Ps", "תהלים"), ("Job", "איוב"), ("Prov", "משלי"), ("Ruth", "רות"),
    ("Song", "שיר השירים"), ("Eccl", "קהלת"), ("Lam", "איכה"), ("Esth", "אסתר"), ("Dan", "דניאל"), ("Ezra", "עזרא"), ("Neh", "נחמיה"),
)
SECTION_OF = {name: ("torah" if index < 5 else "prophets" if index < 26 else "writings") for index, (name, _) in enumerate(BOOKS)}

# Segments that are dropped: verse end, paseq, the reversed nun, and the open and closed section markers.
_DROPPED_SEGMENTS = frozenset({"x-sof-pasuq", "x-paseq", "x-reversednun", "x-pe", "x-samekh"})
_WLC_VERSION = re.compile(r"WLC version (\d+(?:\.\d+)+)")
_SPACE = re.compile(r"\s+")


@dataclass
class Verse:
    book: str
    chapter: int
    verse: int
    words: list[str]  # pointed tokens, maqaf-joined, cantillation kept

    @property
    def ref(self) -> str:
        return f"{self.book}.{self.chapter}.{self.verse}"


@dataclass
class TanakhConfig:
    wlc: Path
    leakage_fixtures: Sequence[Path]
    output: Path
    length_profile: Sequence[int]
    length_profile_source: str
    source_commit: str = WLC_COMMIT
    reservations: Sequence[Path] = ()
    seed: int = 15
    corpus_version: str = DEFAULT_CORPUS_VERSION
    fit: Callable[[str], str | None] | None = None
    allow_maqaf: bool = False
    fit_provenance: dict[str, Any] = field(default_factory=dict)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_jsonl_gz(path: Path, rows: Iterable[dict[str, Any]], *, compact: bool = False) -> None:
    separators = (",", ":") if compact else (", ", ": ")
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as handle:
        for row in rows:
            handle.write((json.dumps(row, ensure_ascii=False, sort_keys=True, separators=separators) + "\n").encode("utf-8"))


def corpus_file_name(subset: str, version: str = DEFAULT_CORPUS_VERSION) -> str:
    return f"tanakh_lines_{subset}_{version}.txt"


def _word_text(element: ET.Element) -> str:
    """A ``<w>``'s letters and marks: OSHB's ``/`` morpheme dividers removed, attributes never read."""

    return "".join(element.itertext()).replace("/", "")


def read_book(path: Path, stats: Counter | None = None) -> tuple[list[Verse], str | None]:
    """The verses of one OSIS book file, and the WLC version its header names."""

    stats = stats if stats is not None else Counter()
    root = ET.parse(path).getroot()
    versions = [match.group(1) for desc in root.iter(f"{OSIS}revisionDesc") for match in _WLC_VERSION.finditer("".join(desc.itertext()))]
    verses: list[Verse] = []
    for element in root.iter(f"{OSIS}verse"):
        book, chapter, number = element.get("osisID").split(".")
        words: list[str] = []
        join_next = False
        for child in element:
            tag = child.tag.replace(OSIS, "")
            if tag == "w":
                text = _word_text(child)
                if join_next and words:
                    words[-1] += MAQAF + text
                else:
                    words.append(text)
                join_next = False
                if child.get("type") == "x-ketiv":
                    stats["words:ketiv"] += 1
            elif tag == "seg":
                kind = child.get("type")
                if kind == "x-maqqef":
                    join_next = True
                elif kind in _DROPPED_SEGMENTS:
                    stats[f"marks_removed:{kind[2:]}"] += 1
                else:
                    # Large, small and suspended letters outside a word are still letters of the text.
                    text = "".join(child.itertext())
                    if words and not join_next:
                        words[-1] += text
                    else:
                        words.append(text)
                    stats[f"letters:{kind[2:]}"] += 1
            elif tag == "note":
                stats[f"notes_skipped:{child.get('type') or 'editorial'}"] += 1
            else:
                raise ValueError(f"{path.name} {element.get('osisID')}: unexpected element <{tag}>")
        verses.append(Verse(book, int(chapter), int(number), [_SPACE.sub("", word) for word in words if word.strip()]))
    return verses, (versions[0] if versions else None)


def pointed_form(text: str) -> str:
    """The S10b niqqud form: cantillation, meteg, rafe and the upper and lower dots removed."""

    return nfc("".join(char for char in unicodedata.normalize("NFD", text) if char not in OTHER_MARKS))


def line_rejection(niqqud: str, plain: str, *, allow_maqaf: bool) -> str | None:
    if len(plain) > MAX_LINE_CHARS:
        return "too_long"
    if hebrew_letter_count(plain) < 2:
        return "too_few_letters"
    extra = {MAQAF} if allow_maqaf else set()
    for text, charset in ((niqqud, NIQQUD_CHARSET | extra), (plain, PLAIN_CHARSET | extra)):
        if any(char not in charset for char in text):
            return "maqaf" if MAQAF in text and not allow_maqaf else "charset"
    if has_medial_final_form(plain):
        return "medial_final_form"
    return None


@dataclass
class TanakhLine:
    niqqud: str
    plain: str
    ref: str
    part: int
    parts: int
    # Whether the line is new in each file (niqqud, plain); a repeated verse is kept once per file.
    new: tuple[bool, bool] = (True, True)


def _rights_record(book: str, hebrew: str, verses: int, file: dict[str, Any]) -> dict[str, Any]:
    return {
        "entry_id": f"tanakh:{book}",
        "source": SOURCE,
        "book": book,
        "name": hebrew,
        "section": SECTION_OF[book],
        "verses": verses,
        "file": file,
        "pd_israel": True,
        "pd_israel_basis": "ancient_text_public_domain_edition",
        "pd_us": True,
        "pd_us_basis": "ancient_text_public_domain_edition",
        **release_fields(source_licence=SOURCE_LICENCE, credit=CREDIT),
        "skipped": None,
    }


def build(config: TanakhConfig, *, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    output = config.output
    output.mkdir(parents=True, exist_ok=True)
    protected = Protected.load(config.leakage_fixtures)
    reservations = Reservations.load(config.reservations)
    stats: Counter = Counter()
    seen = {subset: set() for subset in SUBSETS}
    corpus: list[TanakhLine] = []
    records: dict[str, dict[str, Any]] = {}
    versions: set[str] = set()
    for book, hebrew in BOOKS:
        path = config.wlc / f"{book}.xml"
        if not path.is_file():
            raise FileNotFoundError(f"{path}: every book of the WLC must be present")
        verses, version = read_book(path, stats)
        if version:
            versions.add(version)
        record = records[book] = _rights_record(book, hebrew, len(verses), {"file": f"wlc/{path.name}", "sha256": _sha256_file(path)})
        if reservations.reserved(SOURCE, book):
            record["skipped"] = "eval_reserved"
            continue
        sampler = LengthSampler(config.length_profile, f"{config.seed}:tanakh:{book}")
        kept = 0
        for verse in verses:
            stats["verses"] += 1
            niqqud_words = [pointed_form(word) for word in verse.words]
            plain_words = [strip_marks(word) for word in verse.words]
            spans = word_spans(plain_words, verse=False, targets=sampler)
            for part, (start, end) in enumerate(spans, 1):
                stats["segments"] += 1
                niqqud = " ".join(niqqud_words[start:end])
                plain = " ".join(plain_words[start:end])
                why = line_rejection(niqqud, plain, allow_maqaf=config.allow_maqaf)
                if why:
                    stats[f"segments_dropped:{why}"] += 1
                    continue
                leak = protected.leak(niqqud, plain)
                if leak:
                    stats[f"segments_dropped:leak_{leak}"] += 1
                    continue
                if config.fit is not None:
                    failure = config.fit(niqqud) or config.fit(plain)
                    if failure:
                        stats[f"segments_dropped:fit:{failure}"] += 1
                        continue
                line = TanakhLine(niqqud, plain, verse.ref, part, len(spans))
                # Deduplication is per file: a repeated verse may differ in its points but not its letters.
                new = {subset: getattr(line, subset) not in seen[subset] for subset in SUBSETS}
                if not any(new.values()):
                    stats["segments_dropped:duplicate"] += 1
                    continue
                for subset in SUBSETS:
                    if new[subset]:
                        seen[subset].add(getattr(line, subset))
                    else:
                        stats[f"lines_deduplicated:{subset}"] += 1
                line.new = (new["niqqud"], new["plain"])
                corpus.append(line)
                kept += 1
        if not kept:
            record["skipped"] = "no_line_kept"
        if progress:
            progress(f"{book}: {len(verses)} verses, {kept} lines")
    for record in records.values():
        stats[f"books:{record['skipped'] or 'with_lines'}"] += 1

    files: dict[str, dict[str, Any]] = {}
    index_rows = []
    for position, subset in enumerate(SUBSETS):
        name = corpus_file_name(subset, config.corpus_version)
        lines = [line for line in corpus if line.new[position]]
        with (output / name).open("w", encoding="utf-8", newline="\n") as handle:
            for line in lines:
                handle.write(getattr(line, subset) + "\n")
        profile = length_profile([len(line.plain) for line in lines])
        files[name] = {
            "subset": subset,
            "lines": len(lines),
            "books": len({line.ref.split(".")[0] for line in lines}),
            "sha256": _sha256_file(output / name),
            "bytes": (output / name).stat().st_size,
            "length_profile": profile,
            "length_profile_passes": profile_passes(profile),
            "per_section": {key: value for key, value in sorted(Counter(SECTION_OF[line.ref.split(".")[0]] for line in lines).items())},
        }
        index_rows.extend(
            {"subset": subset, "sha256": sha256_text(getattr(line, subset)), "ref": line.ref, "part": line.part, "parts": line.parts} for line in lines
        )
    _write_jsonl_gz(output / LINE_INDEX_FILE, index_rows, compact=True)
    in_corpus = [book for book, _ in BOOKS if records[book]["skipped"] is None]
    guard = ReleaseGuard("cc0")
    guard.admit_all(records[book] for book in in_corpus)
    for book, record in records.items():
        if record["skipped"] is not None:
            record["htext_release"] = None
    _write_jsonl_gz(output / RIGHTS_INDEX_FILE, (records[book] for book, _ in BOOKS))
    card = _card(config, protected, reservations, records, files, stats, guard, sorted(versions))
    (output / "corpus_card.json").write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "CORPUS_CARD.md").write_text(render_card(card), encoding="utf-8")
    names = sorted(path.name for path in output.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (output / "SHA256SUMS").write_text("".join(f"{_sha256_file(output / n)}  {n}\n" for n in names), encoding="utf-8")
    return card


def _card(config, protected, reservations, records, files, stats, guard, versions) -> dict[str, Any]:
    rows = list(records.values())
    return {
        "schema": CARD_SCHEMA,
        "name": "Tanakh: the Westminster Leningrad Codex, pointed and plain",
        "builder": {"package": "htext", "version": __version__},
        "credit": CREDIT.as_dict(),
        "licence": {"outputs": "CC0-1.0", "source": SOURCE_LICENCE},
        "text_rights": "ancient_text_public_domain_edition",
        "htext_release": guard.release,
        "release": guard.summary(),
        "text_quality": "transcription",
        "schemas": {"rights_index": RIGHTS_SCHEMA, "line_index": LINE_INDEX_SCHEMA},
        "source": {
            "repository": WLC_REPOSITORY,
            "commit": config.source_commit,
            "path": "wlc/",
            "edition": "Westminster Leningrad Codex (WLC), not UXLC",
            "wlc_versions": versions,
            "public_domain_statements": list(PD_STATEMENTS),
            "not_used": "OSHB's lemma, morphology and n attributes (CC BY 4.0) and its / morpheme dividers; marginal readings (qere) and notes",
            "books": len(rows),
        },
        "inputs": {
            "leakage_fixtures": protected.sources,
            "leakage_mode": "line and word 3-grams, in either form",
            "eval_reservations": reservations.card(),
            "length_profile_source": config.length_profile_source,
            "fit_check": config.fit_provenance if config.fit is not None else {"ran": False},
        },
        "corpus_version": config.corpus_version,
        "parameters": {"seed": config.seed, "max_line_chars": MAX_LINE_CHARS, "maqaf_allowed": config.allow_maqaf},
        "books": {
            "total": len(rows),
            "with_lines": sum(1 for row in rows if row["skipped"] is None),
            "skipped": dict(sorted(Counter(row["skipped"] for row in rows if row["skipped"]).items())),
            "verses": stats.get("verses", 0),
        },
        "notes": [
            "Biblical verses are quoted in many printed Hebrew pages, including pages in HeOCR's evaluation sets. The leakage "
            "check drops lines that match evaluation text, but a quotation can still match a line here; run the training-time "
            "overlap check (CLEAN) against your evaluation set before training on this corpus.",
            "Every line exists in both files. A repeated verse is kept once per file, so the two files can differ slightly in length.",
        ],
        "files": files,
        "pipeline": dict(sorted(stats.items())),
        "length_profile_targets": {key: list(value) if isinstance(value, tuple) else value for key, value in PROFILE_TARGETS.items()},
    }


def render_card(card: dict[str, Any]) -> str:
    source = card["source"]
    books = card["books"]
    lines = [
        f"# {card['name']}",
        "",
        f"- **Release:** `htext-{card['htext_release']}` (decision 0022). Source licence: `{card['licence']['source']}`. Outputs: {card['licence']['outputs']}.",
        f"- **Credit:** [{card['credit']['text']}]({card['credit']['url']}).",
        f"- **Source:** [`{source['repository']}`](https://github.com/{source['repository']}) @ `{source['commit']}`, `{source['path']}`. "
        f"Edition: {source['edition']}; the files name WLC version {', '.join(source['wlc_versions']) or 'unknown'}.",
        "- **Public domain.** The Leningrad Codex is about a thousand years old, and the WLC text is in the public domain:",
    ]
    lines += [f"  - {row['where']}: \"{row['text']}\"" for row in source["public_domain_statements"]]
    lines += [
        f"- **Not used:** {source['not_used']}.",
        f"- **Books:** {books['with_lines']} of {books['total']} with lines; {books['verses']:,} verses read."
        + (f" Skipped: {', '.join(f'{k} {v}' for k, v in books['skipped'].items())}." if books["skipped"] else ""),
        f"- **Eval reservations:** {len(card['inputs']['eval_reservations'])} sets loaded.",
        f"- **Leakage check:** {card['inputs']['leakage_mode']}, against {len(card['inputs']['leakage_fixtures'])} fixtures.",
        f"- **Fit check:** {'ran' if card['inputs']['fit_check'].get('ran') else 'not run'}.",
        "",
        "## Notes",
        "",
    ]
    lines += [f"- {note}" for note in card["notes"]]
    lines += ["", "## Files", "", "| File | Form | Lines | Median chars | 31-55 share | 36-47 share | Profile |", "| --- | --- | ---: | ---: | ---: | ---: | --- |"]
    for name, info in card["files"].items():
        profile = info["length_profile"]
        passes = "pass" if all(info["length_profile_passes"].values()) else "miss: " + ", ".join(k for k, v in info["length_profile_passes"].items() if not v)
        lines.append(
            f"| `{name}` | {info['subset']} | {info['lines']:,} | {profile['median']} | {profile['share_31_55']:.1%} | {profile['share_36_47']:.1%} | {passes} |"
        )
    lines += ["", "## Pipeline", "", "| Counter | Value |", "| --- | ---: |"]
    lines += [f"| `{key}` | {value:,} |" for key, value in card["pipeline"].items()]
    return "\n".join(lines) + "\n"

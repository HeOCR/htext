"""Build the Hebrew Wikisource proofread corpus from a pinned Wikimedia dump."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from collections import Counter, defaultdict, deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import urlencode

from htext import __version__
from htext.hebrew import strip_marks
from htext.leakage import Protected, sha256_text
from htext.pby.text import DEFAULT_NIQQUD_THRESHOLD, MAX_LINE_CHARS, LengthSampler, choose_segment, word_spans
from htext.release import Credit, ReleaseGuard, release_fields
from htext.reservations import Reservations
from htext.wikisource import dump
from htext.wikisource.dump import ARTICLE, INDEX, PAGE, Page, index_scan, page_scan, title_key

CORPUS = "wikisource"
SOURCE_LICENCE = "CC BY-SA 4.0"
LICENCE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
WIKI = "https://he.wikisource.org"
CREDIT = Credit("Hebrew Wikisource contributors", WIKI)
DUMP_DATE = "20261101"
DUMP_SHA256 = "15a731d70154941afec2a616d538434573a4e068f94c8ea91b659ac64b833fe1"
DUMP_BYTES = 469_082_606
RIGHTS_INDEX = "wikisource_rights_index.v1.jsonl.gz"
RIGHTS_SCHEMA = "wikisource_rights_index.v1"
LINE_INDEX = "wikisource_line_index.v1.jsonl.gz"
LINE_INDEX_SCHEMA = "wikisource_line_index.v1"
DROP_SCHEMA = "htext_eval_overlap_drop.v1"
LIMITATION = "The exclusion map covers the same ProofreadPage work and its article subpages. Other editions require the official eval overlap check."


@dataclass(frozen=True)
class DumpPin:
    date: str = DUMP_DATE
    sha256: str = DUMP_SHA256
    bytes: int = DUMP_BYTES

    @property
    def url(self) -> str:
        return f"https://dumps.wikimedia.org/hewikisource/{self.date}/hewikisource-{self.date}-pages-articles.xml.bz2"

    def verify(self, path: Path) -> None:
        if path.stat().st_size != self.bytes or _sha256(path) != self.sha256:
            raise ValueError(f"dump does not match the size and SHA-256 pin for {self.date}")


@dataclass(frozen=True)
class BuildConfig:
    dump: Path
    output: Path
    reservations: Sequence[Path]
    eval_overlap_drop: Path | None
    length_profile: Sequence[int]
    length_profile_source: str
    leakage_fixtures: Sequence[Path] = ()
    seed: int = 15
    corpus_version: str = "v1"
    niqqud_threshold: float = DEFAULT_NIQQUD_THRESHOLD
    allow_maqaf: bool = False
    fit: Callable[[str], str | None] | None = None
    fit_provenance: dict[str, Any] = field(default_factory=dict)


def _sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _drop_list(path: Path | None) -> tuple[set[str], set[str]]:
    if path is None:
        raise ValueError("--eval-overlap-drop is required for every Wikisource build")
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema") != DROP_SCHEMA or document.get("corpus") != CORPUS:
        raise ValueError(f"expected a {DROP_SCHEMA} file for corpus {CORPUS!r}")
    lines, units = document.get("line_sha256"), document.get("units")
    if not isinstance(lines, list) or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in lines):
        raise ValueError("eval overlap line_sha256 must be a list of lowercase SHA-256 hashes")
    if not isinstance(units, list) or any(type(value) not in (int, str) or not str(value).strip() for value in units):
        raise ValueError("eval overlap units must be a list of page IDs, Index IDs or titles")
    return set(lines), {str(value) for value in units}


@dataclass
class Units:
    ids: set[int] = field(default_factory=set)
    indexes: set[int] = field(default_factory=set)
    titles: set[str] = field(default_factory=set)

    @classmethod
    def from_values(cls, values: set[str]) -> Units:
        units = cls()
        for value in values:
            value = title_key(value.removeprefix("wikisource:").removeprefix("wikisource_he_proofread:"))
            if match := re.fullmatch(r"ws index ([1-9][0-9]*)(?: p[0-9]+(?:#L[0-9]+)?)?", value):
                units.indexes.add(int(match[1]))
            elif match := re.fullmatch(r"(?:ws page )?([1-9][0-9]*)", value):
                units.ids.add(int(match[1]))
            elif not value or value.startswith(("ws index ", "ws page ")):
                raise ValueError("malformed Wikisource reservation or overlap unit ID")
            else:
                units.titles.add(value)
        return units

    def directly_excludes(self, page: Page) -> bool:
        return page.id in self.ids or (page.namespace == INDEX and page.id in self.indexes) or title_key(page.title) in self.titles


def _work(title: str) -> str:
    return title_key(title).split("/", 1)[0]


@dataclass
class Exclusions:
    reservations: Units
    overlap: Units
    scans: set[str] = field(default_factory=set)
    works: set[str] = field(default_factory=set)

    def discover(self, path: Path) -> dict[str, int]:
        """Build the work/scan graph from titles and transclusion targets.

        ProofreadPage expands an Index's pagelist into Page:<scan>/<number>
        titles. The title gives that membership without opening the Index or
        the Page revisions. The graph also blocks other scans of the same
        main-namespace work when it spans several indexes.
        """
        indexes_found: set[int] = set()
        work_scans: dict[str, set[str]] = defaultdict(set)
        references = dump.References()

        def select(page: Page) -> Callable[[str], None] | None:
            nonlocal references
            reserved = self.reservations.directly_excludes(page)
            direct = reserved or self.overlap.directly_excludes(page)
            if page.namespace == INDEX and direct:
                scan = index_scan(page.title)
                if not scan.casefold().endswith((".pdf", ".djvu")):
                    raise ValueError("a reserved Index lacks a PDF/DjVu title; provide its Page IDs as reservations")
                if reserved:
                    indexes_found.add(page.id)
                self.scans.add(scan)
            if page.namespace == PAGE and reserved:
                self.scans.add(page_scan(page.title))
            if page.namespace == ARTICLE:
                if direct:
                    self.works.add(_work(page.title))
                elif not page.redirected:
                    references = dump.References()
                    return references.feed
            return None

        def finish(page: Page, _revision: int, model: str, fmt: str) -> None:
            if (model, fmt) == ("wikitext", "text/x-wiki") and references.indexes:
                work_scans[_work(page.title)].update(references.indexes)

        dump.scan(path, select=select, finish=finish)
        if missing := self.reservations.indexes - indexes_found:
            raise ValueError(f"{len(missing)} reserved Index IDs are absent from the pinned dump")
        scan_works: dict[str, set[str]] = defaultdict(set)
        for work, scans in work_scans.items():
            for scan in scans:
                scan_works[scan].add(work)
        queue = deque((False, scan) for scan in self.scans)
        queue.extend((True, work) for work in self.works)
        while queue:
            is_work, key = queue.popleft()
            neighbours, excluded = (work_scans, self.scans) if is_work else (scan_works, self.works)
            for neighbour in neighbours.get(key, ()):
                if neighbour not in excluded:
                    excluded.add(neighbour)
                    queue.append((not is_work, neighbour))
        return {"reserved_indexes": len(indexes_found), "works_excluded": len(self.works), "scan_families_excluded": len(self.scans)}

    def excludes(self, page: Page) -> bool:
        return page_scan(page.title) in self.scans or self.reservations.directly_excludes(page) or self.overlap.directly_excludes(page)


def _page_record(page: Page, revision: int, quality: int, basis: list[dict[str, str]], ranges: dict[str, Any], as_of: int) -> dict[str, Any]:
    revision_url = f"{WIKI}/w/index.php?{urlencode({'oldid': revision})}"
    history = f"{WIKI}/w/index.php?{urlencode({'title': page.title, 'action': 'history'})}"
    return {
        "schema": RIGHTS_SCHEMA, "unit_id": f"ws_page_{page.id}", "page_id": page.id, "title": page.title,
        "revision_id": revision, "revision_url": revision_url, "history_url": history,
        "proofread_quality": quality, "underlying_work_rights_basis": basis, "line_ranges": ranges,
        # The underlying work's status, as htext records it for every corpus. The Page's own explicit marking is the
        # basis (``underlying_work_rights_basis``); the US is not assessed for Wikisource.
        "pd_israel": True, "pd_israel_basis": "explicit_marking_on_page", "pd_us": None, "pd_us_basis": "not_assessed", "as_of": as_of,
        **release_fields(source_licence=SOURCE_LICENCE, credit=Credit(CREDIT.text, history), text_quality="transcription"),
    }


def build(config: BuildConfig, *, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Write a local build. Both eval inputs are mandatory and no network is used."""
    from htext.wikisource.text import proofread_page, rights_basis, text_lines

    drop_lines, drop_units = _drop_list(config.eval_overlap_drop)
    reservations = Reservations.load(config.reservations)
    reserved_units = reservations.units.get(CORPUS, set())
    if not reserved_units:
        raise ValueError("--reserved must include Hebrew Wikisource units from eval")
    if not re.fullmatch(r"v[1-9][0-9]*", config.corpus_version):
        raise ValueError("corpus version must have the form v1, v2, ...")
    if not config.length_profile or min(config.length_profile) < 1:
        raise ValueError("length profile must contain positive lengths")
    if not 0 < config.niqqud_threshold <= 1:
        raise ValueError("niqqud threshold must be greater than 0 and at most 1")
    if config.output.exists() or config.output.is_symlink():
        raise ValueError("Wikisource output must be a new directory")
    pin = DumpPin()
    pin.verify(config.dump)
    as_of = date.fromisoformat(pin.date).year
    protected = Protected.load(config.leakage_fixtures)
    exclusions = Exclusions(Units.from_values(reserved_units), Units.from_values(drop_units))
    if progress:
        progress("Wikisource: mapping eval reservations from titles and transclusion references")
    exclusion_counts = exclusions.discover(config.dump)
    if progress:
        progress("Wikisource: filtering proofread Page revisions and writing corpus lines")
    guard = ReleaseGuard("by-sa")
    sampler = LengthSampler(config.length_profile, config.seed)
    stats: Counter[str] = Counter()
    files = {subset: {"name": f"wikisource_{subset}_{config.corpus_version}.txt", "pages": 0, "lines": 0, "characters": 0}
             for subset in ("plain", "niqqud")}
    config.output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".wikisource-", dir=config.output.parent) as temp:
        output = Path(temp) / "corpus"
        output.mkdir()
        with (output / files["plain"]["name"]).open("w", encoding="utf-8", newline="\n") as plain, (
            output / files["niqqud"]["name"]
        ).open("w", encoding="utf-8", newline="\n") as niqqud, (output / RIGHTS_INDEX).open("wb") as index, gzip.GzipFile(
            fileobj=index, mode="wb", filename="", mtime=0
        ) as rights, (output / LINE_INDEX).open("wb") as line_raw, gzip.GzipFile(
            fileobj=line_raw, mode="wb", filename="", mtime=0
        ) as line_index:
            writers = {"plain": plain, "niqqud": niqqud}
            parts: list[str] = []
            seen: set[str] = set()  # exact duplicates are dropped across the corpus, as in every htext builder

            def select(page: Page) -> Callable[[str], None] | None:
                if page.namespace == ARTICLE and _work(page.title) in exclusions.works:
                    stats["article_pages_excluded_by_eval"] += 1
                if page.namespace != PAGE:
                    return None
                stats["pages_seen"] += 1
                if exclusions.excludes(page):
                    stats["pages_excluded_by_eval"] += 1
                    return None
                if page.redirected:
                    stats["pages_redirect"] += 1
                    return None
                parts.clear()
                return parts.append

            def finish(page: Page, revision: int, model: str, fmt: str) -> None:
                proof = proofread_page("".join(parts), model, fmt)
                parts.clear()
                if proof is None:
                    stats["pages_not_proofread"] += 1
                    return
                import mwparserfromhell

                body = mwparserfromhell.parse(proof.body)
                basis = rights_basis(proof, body, as_of=as_of)
                if not basis:
                    stats["pages_without_rights_basis"] += 1
                    return
                sampler.rng.seed(f"{config.seed}:wikisource:{page.id}")
                ranges: dict[str, Any] = {}
                for line in text_lines(body):
                    words = line.split()
                    plain_words = [strip_marks(word) for word in words]
                    for start, end in word_spans(plain_words, verse=False, targets=sampler):
                        pointed = " ".join(words[start:end])
                        segment, why = choose_segment(
                            pointed, " ".join(plain_words[start:end]),
                            threshold=config.niqqud_threshold, allow_maqaf=config.allow_maqaf,
                        )
                        if not segment:
                            stats[f"lines_dropped:{why}"] += 1
                            continue
                        forms = (pointed, segment.plain_form) if pointed != segment.plain_form else (pointed,)
                        if any(sha256_text(form) in drop_lines for form in forms):
                            stats["lines_dropped:eval_overlap"] += 1
                            continue
                        if leak := protected.leak(*forms):
                            stats[f"lines_dropped:leak_{leak}"] += 1
                            continue
                        if config.fit and (failure := config.fit(segment.text)):
                            stats[f"lines_dropped:fit:{failure}"] += 1
                            continue
                        if segment.text in seen:
                            stats["lines_dropped:duplicate"] += 1
                            continue
                        seen.add(segment.text)
                        info = files[segment.subset]
                        span = ranges.get(segment.subset)
                        if span is None:
                            span = ranges[segment.subset] = {"first_line": info["lines"] + 1, "lines": 0}
                            info["pages"] += 1
                        span["lines"] += 1
                        info["lines"] += 1
                        info["characters"] += len(segment.text)
                        writers[segment.subset].write(segment.text + "\n")
                        line_index.write((json.dumps({"file": info["name"], "unit_id": f"ws_page_{page.id}", "scan": page_scan(page.title),
                                                      "sha256": sha256_text(segment.text)}, ensure_ascii=False, sort_keys=True,
                                                     separators=(",", ":")) + "\n").encode("utf-8"))
                if ranges:
                    record = guard.admit(_page_record(page, revision, proof.quality, basis, ranges, as_of))
                    rights.write((json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
                else:
                    stats["pages_without_lines"] += 1

            dump.scan(config.dump, select=select, finish=finish)
        card = _write_card(config, output, pin, guard, files, stats, protected, reservations, exclusion_counts, len(drop_units), len(drop_lines))
        output.rename(config.output)
    return card


def _write_card(config, output, pin, guard, files, stats, protected, reservations, exclusions, drop_units, drop_lines) -> dict[str, Any]:
    for info in files.values():
        path = output / info["name"]
        info.update(bytes=path.stat().st_size, sha256=_sha256(path))
    totals = {"pages": guard.admitted, **{key: sum(info[key] for info in files.values()) for key in ("lines", "characters")}}
    card = {
        "schema": "htext_wikisource_corpus_card.v1",
        "name": "Hebrew Wikisource proofread text",
        "builder": {"package": "htext", "version": __version__},
        "corpus_version": config.corpus_version,
        "source": {"url": pin.url, "date": pin.date, "sha256": pin.sha256, "bytes": pin.bytes},
        "source_licence": SOURCE_LICENCE,
        "licence": {"outputs": "CC-BY-SA-4.0", "source": SOURCE_LICENCE, "url": LICENCE_URL},
        "credit": CREDIT.as_dict(), "htext_release": guard.release, "release": guard.summary(),
        "text_quality": "transcription", "proofread_quality_levels": [3, 4],
        "parameters": {"seed": config.seed, "niqqud_threshold": config.niqqud_threshold, "max_line_chars": MAX_LINE_CHARS,
                       "maqaf_allowed": config.allow_maqaf, "length_profile_source": config.length_profile_source,
                       "length_profile_sha256": sha256_text(json.dumps(sorted(config.length_profile))),
                       "fit_check": config.fit_provenance if config.fit else {"ran": False}},
        "eval_reservations": {"sets": reservations.card(), "units": reservations.count(CORPUS), **exclusions,
                              "pages_excluded": stats["pages_excluded_by_eval"],
                              "article_pages_excluded": stats["article_pages_excluded_by_eval"]},
        "eval_overlap_drop": {"units": drop_units, "line_sha256s": drop_lines, "lines_dropped": stats["lines_dropped:eval_overlap"]},
        "leakage_fixtures": protected.sources,
        "release_gate": "The official HeOCR evaluation overlap check must find 0 before release.",
        "known_limitations": [LIMITATION],
        "totals": totals, "counts": dict(sorted(stats.items())),
        "files": {info["name"]: {key: value for key, value in info.items() if key != "name"} for info in files.values()},
        "rights_index": {"name": RIGHTS_INDEX, "schema": RIGHTS_SCHEMA, "pages": guard.admitted, "sha256": _sha256(output / RIGHTS_INDEX)},
        "line_index": {"name": LINE_INDEX, "schema": LINE_INDEX_SCHEMA, "lines": totals["lines"], "sha256": _sha256(output / LINE_INDEX)},
        "notice": "NOTICE.md",
    }
    (output / "corpus_card.json").write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "CORPUS_CARD.md").write_text(render_card(card), encoding="utf-8")
    (output / "NOTICE.md").write_text(
        f"# Attribution\n\nText from [{CREDIT.text}]({CREDIT.url}), under [CC BY-SA 4.0]({LICENCE_URL}).\n\n"
        f"The per-page title, permanent revision URL and contributor history are in `{RIGHTS_INDEX}`. "
        "The index also gives the source of the underlying work's rights evidence and the output line ranges.\n\n"
        "HeOCR adapted the text by removing wikitext markup and notes, normalizing whitespace and marks, "
        "segmenting it into OCR training lines and filtering the results. The processed text is CC BY-SA 4.0. "
        "Keep this notice and the per-page attribution when redistributing the text.\n",
        encoding="utf-8",
    )
    (output / "SHA256SUMS").write_text(
        "".join(f"{_sha256(path)}  {path.name}\n" for path in sorted(output.iterdir())), encoding="utf-8"
    )
    return card


def render_card(card: dict[str, Any]) -> str:
    pin, totals, reserved, drop = (card[key] for key in ("source", "totals", "eval_reservations", "eval_overlap_drop"))
    rows = "".join(f"| `{name}` | {info['pages']:,} | {info['lines']:,} | {info['characters']:,} |\n" for name, info in card["files"].items())
    return (
        "# Hebrew Wikisource proofread text\n\n"
        f"The {card['corpus_version']} build, in `htext-by-sa`, under [CC BY-SA 4.0]({LICENCE_URL}). "
        f"Credit [{CREDIT.text}]({CREDIT.url}). See [NOTICE](NOTICE.md) and `{RIGHTS_INDEX}` for attribution by revision.\n\n"
        f"Source is the [Wikimedia dump dated {pin['date']}]({pin['url']}) with SHA-256 `{pin['sha256']}`. "
        "Only quality 3 or 4 Page revisions with explicit underlying-work rights markings contribute.\n\n"
        f"{totals['pages']:,} distinct pages contributed {totals['lines']:,} lines and {totals['characters']:,} Unicode characters "
        "(excluding newlines). Pages may appear in both files.\n\n"
        "| File | Pages | Lines | Characters |\n| --- | ---: | ---: | ---: |\n" + rows + "\n"
        f"Eval exclusions cover {reserved['reserved_indexes']:,} reserved Indexes, {reserved['works_excluded']:,} works "
        f"({reserved['article_pages_excluded']:,} articles and subpages) and {reserved['pages_excluded']:,} Page revisions. "
        f"The overlap list supplied {drop['units']:,} units and "
        f"{drop['line_sha256s']:,} line hashes. {drop['lines_dropped']:,} candidate lines matched those hashes.\n\n"
        f"{LIMITATION} {card['release_gate']}\n"
    )

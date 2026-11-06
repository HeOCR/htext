"""Build the PBY corpus variants, indexes, exclusion list and corpus card."""

from __future__ import annotations

import gzip
import hashlib
import json
import random
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from htext import __version__
from htext.hebrew import nfc, strip_marks
from htext.leakage import Protected, sha256_text
from htext.pby import PBY_ATTRIBUTION, PBY_CREDIT, PBY_DUMP_COMMIT, PBY_DUMP_VERSION, PBY_REPOSITORY, PBY_URL
from htext.pby.catalogue import Work, read_catalogue
from htext.pby.rights import RIGHTS_SCHEMA, Creators, rights_record
from htext.pby.text import (
    DEFAULT_NIQQUD_THRESHOLD,
    MAX_LINE_CHARS,
    VERSE_GENRES,
    AlignmentError,
    LengthSampler,
    choose_segment,
    line_rejection,
    source_lines,
    word_spans,
)

# S15a §7.5: start with these genres; reference and lexicon entries are left
# out, and drama is not on the list.
DEFAULT_GENRES = ("prose", "article", "memoir", "letters", "fables", "poetry")
# Long works (the largest has tens of thousands of lines) would otherwise
# dominate; a cap keeps the corpus spread across works.
DEFAULT_MAX_LINES_PER_WORK = 200
VARIANTS = ("il", "il_us")
SUBSETS = ("plain", "niqqud")
LINE_INDEX_SCHEMA = "pby_line_index.v1"
EXCLUSION_SCHEMA = "pby_excluded_works.v1"
CARD_SCHEMA = "pby_corpus_card.v1"
LINE_INDEX_FILE = "pby_line_index.v1.jsonl.gz"
RIGHTS_INDEX_FILE = "pby_rights_index.v1.jsonl.gz"
# S10b length profile targets (S15a §7.3).
PROFILE_TARGETS = {
    "max_chars": MAX_LINE_CHARS,
    "share_31_55": (0.18, 0.35),
    "min_share_36_47": 0.10,
    "median": (18, 30),
}


@dataclass
class BuildConfig:
    dump: Path
    creators: Path
    leakage_fixtures: Sequence[Path]
    output: Path
    length_profile: Sequence[int]
    length_profile_source: str
    as_of: int = 2026
    seed: int = 15
    niqqud_threshold: float = DEFAULT_NIQQUD_THRESHOLD
    genres: Sequence[str] = DEFAULT_GENRES
    max_lines_per_work: int | None = None
    screen_terms: Sequence[str] = ()
    screen_terms_source: str | None = None
    # A fit function returns a failure reason or None; None skips the check.
    fit: Callable[[str], str | None] | None = None
    allow_maqaf: bool = False
    fit_provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class CorpusLine:
    text: str
    subset: str
    work_id: int
    genre: str
    period: int | None
    pd_us: bool
    density: float


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _period(record: dict[str, Any]) -> int | None:
    years = [row["death_year"] for row in (*record["authors"], *record["translators"]) if row["death_year"] is not None]
    return max(years) // 10 * 10 if years else None


def length_profile(lengths: Sequence[int]) -> dict[str, Any]:
    if not lengths:
        return {"lines": 0}
    count = len(lengths)
    return {
        "lines": count,
        "max_chars": max(lengths),
        "median": statistics.median(lengths),
        "share_31_55": round(sum(31 <= n <= 55 for n in lengths) / count, 4),
        "share_36_47": round(sum(36 <= n <= 47 for n in lengths) / count, 4),
    }


def profile_passes(profile: dict[str, Any]) -> dict[str, bool]:
    if not profile.get("lines"):
        return {}
    low, high = PROFILE_TARGETS["share_31_55"]
    median_low, median_high = PROFILE_TARGETS["median"]
    return {
        "max_chars": profile["max_chars"] <= PROFILE_TARGETS["max_chars"],
        "share_31_55": low <= profile["share_31_55"] <= high,
        "share_36_47": profile["share_36_47"] >= PROFILE_TARGETS["min_share_36_47"],
        "median": median_low <= profile["median"] <= median_high,
    }


def _work_lines(
    work: Work,
    record: dict[str, Any],
    config: BuildConfig,
    protected: Protected,
    seen: set[str],
    stats: Counter,
) -> list[CorpusLine]:
    stem = work.stem
    try:
        pointed_text = (config.dump / "txt" / f"{stem}.txt").read_text(encoding="utf-8")
        plain_text = (config.dump / "txt_stripped" / f"{stem}.txt").read_text(encoding="utf-8")
    except FileNotFoundError:
        stats["works_dropped:missing_file"] += 1
        return []
    try:
        lines = source_lines(pointed_text, plain_text)
    except AlignmentError as error:
        stats["works_dropped:" + ("misaligned" if "lines vs" in str(error) else "footnote_gap")] += 1
        return []
    sampler = LengthSampler(config.length_profile, seed=f"{config.seed}:{work.work_id}")
    verse = work.genre in VERSE_GENRES
    period = _period(record)
    out: list[CorpusLine] = []
    for line in lines:
        stats["source_lines"] += 1
        reason = line_rejection(line)
        if reason:
            stats[f"source_lines_dropped:{reason}"] += 1
            continue
        plain_words = line.plain.split()
        pointed_words = line.pointed.split()
        if len(pointed_words) != len(plain_words):
            stats["source_lines_plain_only:word_mismatch"] += 1
            pointed_words = []
        for start, end in word_spans(plain_words, verse=verse, targets=sampler):
            stats["segments"] += 1
            pointed = " ".join(pointed_words[start:end]) if pointed_words else None
            segment, why = choose_segment(
                pointed, " ".join(plain_words[start:end]), threshold=config.niqqud_threshold, allow_maqaf=config.allow_maqaf
            )
            if segment is None:
                stats[f"segments_dropped:{why}"] += 1
                continue
            if pointed is not None:
                stats[f"density_bin:{min(int(segment.density * 10), 9)}"] += 1
            leak = protected.leak(segment.text, segment.plain_form)
            if leak:
                stats[f"segments_dropped:leak_{leak}"] += 1
                continue
            if config.screen_terms and any(term in segment.plain_form for term in config.screen_terms):
                stats["segments_dropped:content_screen"] += 1
                continue
            key = nfc(segment.plain_form)
            if key in seen:
                stats["segments_dropped:duplicate"] += 1
                continue
            seen.add(key)
            out.append(
                CorpusLine(
                    text=segment.text,
                    subset=segment.subset,
                    work_id=work.work_id,
                    genre=work.genre,
                    period=period,
                    pd_us=record["pd_us"] is True,
                    density=segment.density,
                )
            )
    if config.max_lines_per_work is not None and len(out) > config.max_lines_per_work:
        stats["segments_dropped:per_work_cap"] += len(out) - config.max_lines_per_work
        keep = sorted(random.Random(f"{config.seed}:cap:{work.work_id}").sample(range(len(out)), config.max_lines_per_work))
        out = [out[index] for index in keep]
    if config.fit is not None:
        fitted = []
        for corpus_line in out:
            failure = config.fit(corpus_line.text)
            if failure:
                stats[f"segments_dropped:fit:{failure}"] += 1
            else:
                fitted.append(corpus_line)
        out = fitted
    return out


def _write_lines(path: Path, lines: Iterable[str]) -> int:
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for line in lines:
            handle.write(line + "\n")
            count += 1
    return count


def _write_jsonl_gz(path: Path, rows: Iterable[dict[str, Any]], *, compact: bool = False) -> None:
    """Write gzipped JSONL with a fixed header (no name, mtime 0), so equal rows give equal bytes."""

    separators = (",", ":") if compact else (", ", ": ")
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as handle:
        for row in rows:
            handle.write((json.dumps(row, ensure_ascii=False, sort_keys=True, separators=separators) + "\n").encode("utf-8"))


def corpus_file_name(variant: str, subset: str) -> str:
    return f"pby_lines_{variant}_{subset}_v1.txt"


def build(config: BuildConfig, *, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    config.output.mkdir(parents=True, exist_ok=True)
    works = read_catalogue(config.dump / "pseudocatalogue.csv")
    creators = Creators.load(config.creators)
    protected = Protected.load(config.leakage_fixtures)
    records = {work.work_id: rights_record(work, creators, as_of=config.as_of) for work in works}
    stats: Counter = Counter()
    seen: set[str] = set()
    corpus: list[CorpusLine] = []
    genres = set(config.genres)
    for number, work in enumerate(works, 1):
        record = records[work.work_id]
        if work.genre not in genres:
            stats["works_skipped:genre"] += 1
            continue
        if not record["pd_israel"]:
            stats["works_skipped:not_pd_israel"] += 1
            continue
        stats["works_read"] += 1
        lines = _work_lines(work, record, config, protected, seen, stats)
        if lines:
            stats["works_with_lines"] += 1
        corpus.extend(lines)
        if progress and number % 2000 == 0:
            progress(f"{number}/{len(works)} works, {len(corpus)} lines")

    output = config.output
    files: dict[str, dict[str, Any]] = {}
    for variant in VARIANTS:
        for subset in SUBSETS:
            selected = [line for line in corpus if line.subset == subset and (variant == "il" or line.pd_us)]
            name = corpus_file_name(variant, subset)
            _write_lines(output / name, (line.text for line in selected))
            lengths = [len(line.text) if subset == "plain" else len(strip_marks(line.text)) for line in selected]
            profile = length_profile(lengths)
            files[name] = {
                "variant": variant,
                "subset": subset,
                "lines": len(selected),
                "works": len({line.work_id for line in selected}),
                "sha256": _sha256_file(output / name),
                "bytes": (output / name).stat().st_size,
                "length_profile": profile,
                "length_profile_passes": profile_passes(profile),
                "genres": dict(sorted(Counter(line.genre for line in selected).items())),
            }

    _write_jsonl_gz(
        output / LINE_INDEX_FILE,
        (
            {
                "sha256": sha256_text(line.text),
                "pby_work_id": line.work_id,
                "subset": line.subset,
                "genre": line.genre,
                "period": line.period,
                "il_us": line.pd_us,
            }
            for line in corpus
        ),
        compact=True,
    )
    _write_jsonl_gz(output / RIGHTS_INDEX_FILE, (records[work.work_id] for work in works))

    corpus_work_ids = sorted({line.work_id for line in corpus})
    exclusion = {
        "schema": EXCLUSION_SCHEMA,
        "note": "Every PBY work with at least one line in any variant of this build. Exclude these works from real-scan evaluation sets.",
        "as_of": config.as_of,
        "pby_dump_commit": PBY_DUMP_COMMIT,
        "corpus_sha256": {name: info["sha256"] for name, info in files.items()},
        "works": [
            {
                "pby_work_id": work_id,
                "title": records[work_id]["title"],
                "author_qids": [row["wikidata_qid"] for row in records[work_id]["authors"]],
                "translator_qids": [row["wikidata_qid"] for row in records[work_id]["translators"]],
            }
            for work_id in corpus_work_ids
        ],
    }
    (output / "pby_excluded_works.v1.json").write_text(json.dumps(exclusion, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    card = _card(config, records, files, stats, corpus_work_ids)
    (output / "corpus_card.json").write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "CORPUS_CARD.md").write_text(render_card(card), encoding="utf-8")

    names = sorted(path.name for path in output.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (output / "SHA256SUMS").write_text("".join(f"{_sha256_file(output / name)}  {name}\n" for name in names), encoding="utf-8")
    return card


def _card(
    config: BuildConfig,
    records: dict[int, dict[str, Any]],
    files: dict[str, dict[str, Any]],
    stats: Counter,
    corpus_work_ids: list[int],
) -> dict[str, Any]:
    rights = list(records.values())
    density_bins = {f"{bin_ / 10:.1f}-{(bin_ + 1) / 10:.1f}": stats.get(f"density_bin:{bin_}", 0) for bin_ in range(10)}
    return {
        "schema": CARD_SCHEMA,
        "name": "PBY public-domain Hebrew lines",
        "builder": {"package": "htext", "version": __version__},
        "attribution": PBY_ATTRIBUTION,
        "credit": {"text": PBY_CREDIT, "url": PBY_URL},
        "licence": {
            "outputs": "CC0-1.0",
            "source": "Public domain (public_domain_dump LICENSE); PBY requests credit, which this card gives",
        },
        "text_rights": "third_party_public_domain",
        "schemas": {
            "rights_index": RIGHTS_SCHEMA,
            "line_index": LINE_INDEX_SCHEMA,
            "excluded_works": EXCLUSION_SCHEMA,
        },
        "source": {
            "repository": PBY_REPOSITORY,
            "commit": PBY_DUMP_COMMIT,
            "version": PBY_DUMP_VERSION,
            "catalogue_rows": len(rights),
        },
        "inputs": {
            "creators_json_sha256": _sha256_file(config.creators),
            "leakage_fixtures": Protected.load(config.leakage_fixtures).sources,
            "length_profile_source": config.length_profile_source,
            "fit_check": config.fit_provenance if config.fit is not None else {"ran": False},
        },
        "parameters": {
            "as_of": config.as_of,
            "seed": config.seed,
            "niqqud_threshold": config.niqqud_threshold,
            "genres": list(config.genres),
            "max_lines_per_work": config.max_lines_per_work,
            "max_line_chars": MAX_LINE_CHARS,
            "maqaf_allowed": config.allow_maqaf,
            "content_screen": {
                "terms": len(config.screen_terms),
                "source": config.screen_terms_source,
            },
        },
        "rights": {
            "pd_israel": dict(sorted(Counter(row["pd_israel_basis"] for row in rights).items())),
            "pd_us": dict(sorted(Counter(row["pd_us_basis"] for row in rights).items())),
            "source_edition_year_parsed": sum(row["source_edition_year"] is not None for row in rights),
            "works_in_corpus": len(corpus_work_ids),
            "works_in_il_us": len({work_id for work_id in corpus_work_ids if records[work_id]["pd_us"] is True}),
        },
        "files": files,
        "pipeline": dict(sorted(stats.items())),
        "niqqud_density_histogram": density_bins,
        "length_profile_targets": {key: list(value) if isinstance(value, tuple) else value for key, value in PROFILE_TARGETS.items()},
    }


def render_card(card: dict[str, Any]) -> str:
    source = card["source"]
    parameters = card["parameters"]
    rights = card["rights"]
    lines = [
        f"# {card['name']}",
        "",
        f"{card['attribution']}.",
        "",
        f"Credit: [{card['credit']['text']}]({card['credit']['url']}).",
        "",
        f"- Source: `{source['repository']}` at `{source['commit']}` (VERSION `{source['version']}`), "
        f"{source['catalogue_rows']} catalogue rows.",
        f"- Rights computed for `as_of` {parameters['as_of']}. `pd_israel` and `pd_us` are this build's reading "
        "of the law, not legal advice; see `pby_rights_index.v1.jsonl.gz`.",
        f"- Outputs are {card['licence']['outputs']}. Source text: {card['licence']['source']}.",
        f"- Builder: `htext` {card['builder']['version']}.",
        "",
        "## Files",
        "",
        "| File | Variant | Subset | Lines | Works | Bytes | sha256 |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for name, info in card["files"].items():
        lines.append(
            f"| `{name}` | {info['variant']} | {info['subset']} | {info['lines']} | {info['works']} | {info['bytes']} | `{info['sha256']}` |"
        )
    lines += [
        "",
        "`il`: every line is from a work that is public domain in Israel. `il_us`: also public domain in the US.",
        "`niqqud` lines are pointed (density at or above the threshold); `plain` lines carry no points.",
        "",
        "## Length profile",
        "",
        "Characters per line; niqqud lines are measured without their points.",
        "",
        "| File | Max | Median | 31-55 | 36-47 | Passes |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for name, info in card["files"].items():
        profile = info["length_profile"]
        if not profile.get("lines"):
            continue
        passes = ", ".join(key for key, ok in info["length_profile_passes"].items() if not ok) or "all"
        if passes != "all":
            passes = "fails: " + passes
        lines.append(
            f"| `{name}` | {profile['max_chars']} | {profile['median']} | {profile['share_31_55']:.1%} | {profile['share_36_47']:.1%} | {passes} |"
        )
    targets = card["length_profile_targets"]
    lines += [
        "",
        f"Targets (S10b): at most {targets['max_chars']} characters; {targets['share_31_55'][0]:.0%}-{targets['share_31_55'][1]:.0%} "
        f"of lines at 31-55; at least {targets['min_share_36_47']:.0%} at 36-47; median {targets['median'][0]}-{targets['median'][1]}.",
        "",
        "## Rights",
        "",
        "| `pd_israel_basis` | Works |",
        "| --- | ---: |",
        *(f"| `{basis}` | {count} |" for basis, count in rights["pd_israel"].items()),
        "",
        "| `pd_us_basis` | Works |",
        "| --- | ---: |",
        *(f"| `{basis}` | {count} |" for basis, count in rights["pd_us"].items()),
        "",
        f"Works with lines in this build: {rights['works_in_corpus']} (`il`), {rights['works_in_il_us']} (`il_us`).",
        "",
        "## Build parameters and checks",
        "",
        f"- Genres: {', '.join(parameters['genres'])}.",
        f"- Niqqud threshold: {parameters['niqqud_threshold']}. Seed: {parameters['seed']}. "
        f"Max lines per work: {parameters['max_lines_per_work']}.",
        f"- Maqaf allowed: {parameters['maqaf_allowed']}.",
        (
            f"- Content screen: {parameters['content_screen']['terms']} terms from `{parameters['content_screen']['source']}`."
            if parameters["content_screen"]["source"]
            else "- Content screen: none applied. No words are filtered by default: HeOCR has to read real historical "
            "text as written. `--screen-terms` exists for builds that need a screen."
        ),
        f"- No-loss wrap check: {json.dumps(card['inputs']['fit_check'], ensure_ascii=False)}.",
        f"- Length profile source: {card['inputs']['length_profile_source']}.",
        "- Leakage: no line, and no word 3-gram, is shared with these protected texts (pointed and stripped forms):",
        *(f"  - `{fixture['repository']}` `{fixture['path']}` @ `{fixture['commit'][:12]}`" for fixture in card["inputs"]["leakage_fixtures"]),
        "",
        "## Pipeline counts",
        "",
        "| Step | Count |",
        "| --- | ---: |",
        *(f"| `{key}` | {value} |" for key, value in card["pipeline"].items() if not key.startswith("density_bin:")),
        "",
        "## Niqqud density histogram",
        "",
        "Segments that had a pointed form, by the share of Hebrew letters carrying a point.",
        "",
        "| Density | Segments |",
        "| --- | ---: |",
        *(f"| {bin_} | {count} |" for bin_, count in card["niqqud_density_histogram"].items()),
        "",
    ]
    return "\n".join(lines)

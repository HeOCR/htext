"""Build the ``knesset-laws`` corpus: enacted laws K1-8, as published, from their OCR text.

Inputs (no network):

- the fetch manifest (``htext.knesset.fetch``), which pins every file;
- the extracted texts (``htext.knesset.extract``), checked against those pins;
- transcription corpora for the lexicon (``htext.knesset.lexicon``);
- leakage fixtures and eval's reservations.

Per law:

1. **Booklet.** A Sefer HaChukim law (series 6071) is in booklet
   ``sefer_hachukim_<MagazineNumber>``; a budget law (series 6075) in
   ``chukei_taktziv_<MagazineNumber>`` (eval, 2026-11-18). Ids are matched in
   full, never by number alone (``kovetz_hatakanot_6075`` is another booklet).
   A law in another series, or with no booklet number, is held out, because
   its reservation cannot be checked. A law whose booklet eval reserves is
   left out whole.
2. **Text.** The DOC's text, cut into paragraphs (``htext.knesset.text``). A law
   with no DOC is left out in ``v1``.
3. **Lines.** Paragraphs are packed to the S10b length profile, as PBY prose is,
   and each line passes the PBY character rules, the lexicon filter, the leakage
   check by line (legal formulas repeat, so word 3-grams are not used; the
   reservation removes the whole booklet instead), deduplication, and the
   hocrsyngen wrap check.

Every law carries ``source_licence`` S6_LABEL, ``htext_release`` ``cc0`` and
``text_quality`` ``ocr_layer``; its lines never feed a lexicon.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import random
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from htext import __version__
from htext.knesset.extract import read_texts
from htext.knesset.fetch import MANIFEST_SCHEMA
from htext.knesset.lexicon import CONFUSIONS, Lexicon
from htext.knesset.text import UNRESOLVED_BREAK, paragraphs
from htext.leakage import Protected, sha256_text
from htext.pby.build import PROFILE_TARGETS, length_profile, profile_passes
from htext.pby.text import MAX_LINE_CHARS, LengthSampler, choose_segment, word_spans
from htext.release import S6_LABEL, Credit, ReleaseGuard, lexicon_eligible, release_fields
from htext.reservations import Reservations

SOURCE = "knesset-laws"
# A comma between digits that is not a thousands separator: the OCR reverses number lists ("75,74" for "74, 75").
_NUMBER_LIST = re.compile(r"\d,(?!\d{3}(?!\d))\d")
CARD_SCHEMA = "knesset_laws_corpus_card.v1"
RIGHTS_SCHEMA = "knesset_laws_rights_index.v1"
LINE_INDEX_SCHEMA = "knesset_laws_line_index.v1"
EXCLUSION_SCHEMA = "knesset_laws_excluded.v1"
EYE_SAMPLE_SCHEMA = "knesset_laws_eye_check_sample.v1"
EYE_CHECK_SCHEMA = "htext_eye_check.v1"
RIGHTS_INDEX_FILE = "knesset_laws_rights_index.v1.jsonl.gz"
LINE_INDEX_FILE = "knesset_laws_line_index.v1.jsonl.gz"
EXCLUSION_FILE = "knesset_laws_excluded.v1.json"
EYE_SAMPLE_FILE = "knesset_laws_eye_check_sample.v1.jsonl"
DEFAULT_CORPUS_VERSION = "v1"
DEFAULT_EYE_SAMPLE = 100

# Reshumot series (KNS_Bill.PublicationSeriesID) to eval's booklet id prefix.
BOOKLET_SERIES = {6071: "sefer_hachukim", 6075: "chukei_taktziv"}
CREDIT = Credit("The Knesset of Israel (Knesset database, laws as published in Reshumot)", "https://main.knesset.gov.il")


def confusion_pair(word: str, variant: str) -> str:
    """The confusion pair, as named on the card ("ב/כ"), that turns ``word`` into ``variant``."""

    for a, b in zip(word, variant):
        if a != b:
            for pair in CONFUSIONS:
                if {a, b} == set(pair):
                    return "/".join(pair)
    raise ValueError(f"{word!r} and {variant!r} differ by no known confusion")


def booklet_unit(bill: dict[str, Any]) -> str | None:
    """Eval's id for the law's Reshumot booklet, or None when the series has no mapping."""

    prefix = BOOKLET_SERIES.get(bill.get("publication_series_id"))
    number = bill.get("magazine_number")
    if prefix is None or number in (None, ""):
        return None
    return f"{prefix}_{int(number)}"


@dataclass
class LawsConfig:
    manifest: Path
    texts: Path
    lexicon_corpora: Sequence[Path]
    leakage_fixtures: Sequence[Path]
    output: Path
    length_profile: Sequence[int]
    length_profile_source: str
    reservations: Sequence[Path] = ()
    lexicon_min_count: int = 2
    as_of: int = 2026
    seed: int = 15
    corpus_version: str = DEFAULT_CORPUS_VERSION
    fit: Callable[[str], str | None] | None = None
    allow_maqaf: bool = False
    fit_provenance: dict[str, Any] = field(default_factory=dict)
    eye_sample_size: int = DEFAULT_EYE_SAMPLE
    # A completed htext_eye_check.v1 file for this build's sample; None until the check is done.
    eye_check: Path | None = None
    # Earlier eye-check sample files; their lines are never drawn again, so a check is never made on lines the rules were tuned on.
    eye_exclude: Sequence[Path] = ()
    # Prebuilt lexicon (tests); None builds it from lexicon_corpora.
    lexicon: Lexicon | None = None


@dataclass
class LawLine:
    text: str
    bill_id: int
    knesset: int
    booklet: str
    kind: str
    file: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_jsonl_gz(path: Path, rows, *, compact: bool = False) -> None:
    separators = (",", ":") if compact else (", ", ": ")
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as handle:
        for row in rows:
            handle.write((json.dumps(row, ensure_ascii=False, sort_keys=True, separators=separators) + "\n").encode("utf-8"))


def corpus_file_name(version: str = DEFAULT_CORPUS_VERSION) -> str:
    return f"knesset_laws_lines_plain_{version}.txt"


def _rights_record(bill: dict[str, Any], unit: str | None, as_of: int) -> dict[str, Any]:
    return {
        "entry_id": f"knesset_law:{bill['bill_id']}",
        "source": SOURCE,
        "bill_id": bill["bill_id"],
        "knesset": bill["knesset"],
        "name": bill["name"],
        "publication_date": bill["publication_date"],
        "publication_series_id": bill["publication_series_id"],
        "publication_series": bill["publication_series"],
        "magazine_number": bill["magazine_number"],
        "page_number": bill["page_number"],
        "booklet": unit,
        "files": [{"file": doc["file"], "format": doc["format"], "sha256": doc.get("sha256")} for doc in bill["documents"]],
        "pd_israel": True,
        "pd_israel_basis": "s6_official_text",
        "pd_us": "not_assessed",
        "pd_us_basis": "not_assessed",
        "as_of": as_of,
        **release_fields(source_licence=S6_LABEL, credit=CREDIT, text_quality="ocr_layer"),
        "text_source": None,
        "skipped": None,
    }


def _law_lines(
    bill: dict[str, Any],
    unit: str,
    docs: list[dict[str, Any]],
    texts: dict[str, dict[str, Any]],
    config: LawsConfig,
    lexicon: Lexicon,
    protected: Protected,
    seen: set[str],
    stats: Counter,
) -> list[LawLine]:
    out: list[LawLine] = []
    sampler = LengthSampler(config.length_profile, f"{config.seed}:law:{bill['bill_id']}")
    for doc in docs:
        text = texts[doc["file"]]["text"]
        law_stats: dict[str, int] = {}
        for paragraph in paragraphs(text, law_stats, is_word=lexicon.is_word):
            words = paragraph.text.split()
            for start, end in word_spans(words, verse=False, targets=sampler):
                stats["segments"] += 1
                candidate = " ".join(words[start:end])
                if UNRESOLVED_BREAK in candidate:
                    stats["segments_dropped:unresolved_line_break"] += 1
                    continue
                if _NUMBER_LIST.search(candidate):
                    stats["segments_dropped:number_list_order"] += 1
                    continue
                segment, why = choose_segment(None, candidate, threshold=1.0, allow_maqaf=config.allow_maqaf)
                if segment is None:
                    stats[f"segments_dropped:{why}"] += 1
                    continue
                if lexicon.unknown(segment.text):
                    stats["segments_dropped:lexicon"] += 1
                    continue
                suspects = lexicon.suspects(segment.text)
                if suspects:
                    stats["segments_dropped:lexicon_suspect"] += 1
                    for pair in sorted({confusion_pair(word, variant) for word, variant in suspects}):
                        stats[f"suspect_pair:{pair}"] += 1
                    continue
                if sha256_text(segment.text) in protected.lines:
                    stats["segments_dropped:leak_line"] += 1
                    continue
                if segment.text in seen:
                    stats["segments_dropped:duplicate"] += 1
                    continue
                if config.fit is not None:
                    failure = config.fit(segment.text)
                    if failure:
                        stats[f"segments_dropped:fit:{failure}"] += 1
                        continue
                seen.add(segment.text)
                out.append(LawLine(segment.text, bill["bill_id"], bill["knesset"], unit, paragraph.kind, doc["file"]))
        for key, value in law_stats.items():
            stats[f"text:{key}"] += value
    return out


def _excluded_sample_lines(paths: Sequence[Path]) -> tuple[set[str], list[dict[str, Any]]]:
    shas: set[str] = set()
    sources = []
    for path in paths:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()[1:]]
        shas.update(row["sha256"] for row in rows)
        sources.append({"file": path.name, "sha256": _sha256_file(path), "lines": len(rows)})
    return shas, sources


def _eye_sample(corpus: list[LawLine], size: int, seed: int, exclude: set[str] = frozenset()) -> list[dict[str, Any]]:
    eligible = [index for index, line in enumerate(corpus) if sha256_text(line.text) not in exclude]
    picks = sorted(random.Random(f"{seed}:eye").sample(eligible, min(size, len(eligible))))
    return [
        {
            "sha256": sha256_text(corpus[index].text),
            "text": corpus[index].text,
            "bill_id": corpus[index].bill_id,
            "knesset": corpus[index].knesset,
            "booklet": corpus[index].booklet,
            "kind": corpus[index].kind,
            "file": corpus[index].file,
        }
        for index in picks
    ]


def eye_check_summary(path: Path | None, sample_sha256: str, sample: list[dict[str, Any]]) -> dict[str, Any]:
    """The card's record of the eye check, checked against this build's sample."""

    if path is None:
        return {"ran": False, "sample_file_sha256": sample_sha256, "sample_lines": len(sample)}
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != EYE_CHECK_SCHEMA:
        raise ValueError(f"{path}: expected schema {EYE_CHECK_SCHEMA!r}")
    if document.get("sample_file_sha256") != sample_sha256:
        raise ValueError(f"{path}: the eye check was made on another sample ({document.get('sample_file_sha256')})")
    verdicts = {row["sha256"]: row for row in document["lines"]}
    if set(verdicts) != {row["sha256"] for row in sample}:
        raise ValueError(f"{path}: the eye check does not cover exactly the sample lines")
    errors = Counter()
    lines_with_error = 0
    words_wrong = 0
    words = 0
    unverifiable = 0
    for row in sample:
        verdict = verdicts[row["sha256"]]
        if verdict.get("unverifiable"):
            # The scan is damaged where the line is printed; it counts toward neither side.
            unverifiable += 1
            continue
        words += len(row["text"].split())
        if verdict["errors"]:
            lines_with_error += 1
        for error in verdict["errors"]:
            errors[error["kind"]] += 1
            words_wrong += int(error.get("words", 1))
    checked = len(sample) - unverifiable
    return {
        "ran": True,
        "sample_file_sha256": sample_sha256,
        "checked_by": document["checked_by"],
        "checked_at": document["checked_at"],
        "method": document["method"],
        "sample_lines": len(sample),
        "unverifiable_lines": unverifiable,
        "lines_checked": checked,
        "lines_with_error": lines_with_error,
        "line_error_rate": round(lines_with_error / checked, 4) if checked else None,
        "sample_words": words,
        "words_wrong": words_wrong,
        "word_error_rate": round(words_wrong / words, 4) if words else None,
        "errors_by_kind": dict(sorted(errors.items())),
        "file": {"name": path.name, "sha256": _sha256_file(path)},
    }


def build(config: LawsConfig, *, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    output = config.output
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(config.manifest.read_text(encoding="utf-8"))
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"{config.manifest}: expected schema {MANIFEST_SCHEMA!r}")
    texts_header, texts = read_texts(config.texts)
    protected = Protected.load(config.leakage_fixtures)
    reservations = Reservations.load(config.reservations)
    lexicon = config.lexicon or Lexicon.from_files(config.lexicon_corpora, min_count=config.lexicon_min_count)
    stats: Counter = Counter()
    seen: set[str] = set()
    corpus: list[LawLine] = []
    records: dict[int, dict[str, Any]] = {}
    bills = sorted(manifest["bills"], key=lambda bill: bill["bill_id"])
    for number, bill in enumerate(bills, 1):
        unit = booklet_unit(bill)
        record = records[bill["bill_id"]] = _rights_record(bill, unit, config.as_of)
        if unit is None:
            # No booklet means the reservation cannot be checked, so the law is held out.
            record["skipped"] = "series_unmapped" if bill.get("publication_series_id") not in BOOKLET_SERIES else "no_booklet_number"
        elif reservations.reserved("reshumot", unit):
            record["skipped"] = "eval_reserved"
        else:
            docs = []
            for doc in bill["documents"]:
                if doc["format"] != "DOC" or not doc.get("sha256"):
                    continue
                row = texts.get(doc["file"])
                if row is None or row["sha256"] != doc["sha256"]:
                    raise ValueError(f"{doc['file']}: no extracted text for the pinned file; rerun the extract step")
                if row.get("text") is None:
                    stats["files_skipped:extract_failed"] += 1
                    continue
                docs.append(doc)
            if not docs:
                record["skipped"] = "no_doc"
            else:
                record["text_source"] = [doc["file"] for doc in docs]
                lines = _law_lines(bill, unit, docs, texts, config, lexicon, protected, seen, stats)
                if not lines:
                    record["skipped"] = "no_line_kept"
                corpus.extend(lines)
        stats[f"laws:{record['skipped'] or 'with_lines'}"] += 1
        if progress and number % 200 == 0:
            progress(f"{number}/{len(bills)} laws, {len(corpus)} lines")

    name = corpus_file_name(config.corpus_version)
    with (output / name).open("w", encoding="utf-8", newline="\n") as handle:
        for line in corpus:
            handle.write(line.text + "\n")
    lengths = [len(line.text) for line in corpus]
    profile = length_profile(lengths)
    in_corpus = sorted({line.bill_id for line in corpus})
    files = {
        name: {
            "subset": "plain",
            "lines": len(corpus),
            "laws": len(in_corpus),
            "sha256": _sha256_file(output / name),
            "bytes": (output / name).stat().st_size,
            "length_profile": profile,
            "length_profile_passes": profile_passes(profile),
            "kinds": dict(sorted(Counter(line.kind for line in corpus).items())),
            "per_knesset": {str(k): v for k, v in sorted(Counter(line.knesset for line in corpus).items())},
        }
    }
    _write_jsonl_gz(
        output / LINE_INDEX_FILE,
        (
            {"sha256": sha256_text(line.text), "bill_id": line.bill_id, "knesset": line.knesset, "booklet": line.booklet, "kind": line.kind, "file": line.file}
            for line in corpus
        ),
        compact=True,
    )
    guard = ReleaseGuard("cc0")
    guard.admit_all(records[bill_id] for bill_id in in_corpus)
    assert not any(lexicon_eligible(records[bill_id]) for bill_id in in_corpus)
    keep = set(in_corpus)
    for bill_id, record in records.items():
        if bill_id not in keep:
            record["htext_release"] = None
    _write_jsonl_gz(output / RIGHTS_INDEX_FILE, (records[bill["bill_id"]] for bill in bills))
    exclusion = {
        "schema": EXCLUSION_SCHEMA,
        "note": "Every law with at least one line in this build, with its Reshumot booklet. Exclude these booklets from real-scan evaluation sets.",
        "corpus_sha256": {name: files[name]["sha256"]},
        "booklets": sorted({records[bill_id]["booklet"] for bill_id in in_corpus}),
        "laws": [{"bill_id": bill_id, "booklet": records[bill_id]["booklet"], "name": records[bill_id]["name"]} for bill_id in in_corpus],
    }
    (output / EXCLUSION_FILE).write_text(json.dumps(exclusion, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    excluded_shas, excluded_sources = _excluded_sample_lines(config.eye_exclude)
    sample = _eye_sample(corpus, config.eye_sample_size, config.seed, excluded_shas)
    with (output / EYE_SAMPLE_FILE).open("w", encoding="utf-8", newline="\n") as handle:
        header = {"schema": EYE_SAMPLE_SCHEMA, "seed": config.seed, "lines": len(sample), "excluded_samples": excluded_sources}
        handle.write(json.dumps(header, ensure_ascii=False) + "\n")
        for row in sample:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    eye = eye_check_summary(config.eye_check, _sha256_file(output / EYE_SAMPLE_FILE), sample)
    eye["excluded_samples"] = excluded_sources

    card = _card(config, manifest, texts_header, lexicon, protected, reservations, records, files, stats, guard, eye)
    (output / "corpus_card.json").write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "CORPUS_CARD.md").write_text(render_card(card), encoding="utf-8")
    names = sorted(path.name for path in output.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (output / "SHA256SUMS").write_text("".join(f"{_sha256_file(output / n)}  {n}\n" for n in names), encoding="utf-8")
    return card


def _card(config, manifest, texts_header, lexicon, protected, reservations, records, files, stats, guard, eye) -> dict[str, Any]:
    rows = list(records.values())
    considered = stats.get("segments", 0)
    lexicon_dropped = stats.get("segments_dropped:lexicon", 0)
    suspect_dropped = stats.get("segments_dropped:lexicon_suspect", 0)
    after_charset = considered - sum(
        value for key, value in stats.items() if key.startswith("segments_dropped:") and key.split(":", 1)[1] in {"charset", "too_few_letters", "too_long", "maqaf", "medial_final_form", "long_digit_run", "unresolved_line_break", "number_list_order"}
    )
    return {
        "schema": CARD_SCHEMA,
        "name": "Knesset laws as published (K1-8), OCR text layer",
        "builder": {"package": "htext", "version": __version__},
        "credit": CREDIT.as_dict(),
        "licence": {"outputs": "CC0-1.0", "source": S6_LABEL},
        "text_rights": "s6_official_text",
        "htext_release": guard.release,
        "release": guard.summary(),
        "text_quality": "ocr_layer",
        "lexicon_eligible": False,
        "schemas": {"rights_index": RIGHTS_SCHEMA, "line_index": LINE_INDEX_SCHEMA, "excluded": EXCLUSION_SCHEMA, "eye_check_sample": EYE_SAMPLE_SCHEMA},
        "source": {
            "fetch_manifest": {"file": config.manifest.name, "sha256": _sha256_file(config.manifest), "fetched_at": manifest["source"]["fetched_at"]},
            "odata": manifest["source"]["odata"],
            "knessets": manifest["knessets"],
            "bills": len(rows),
            "extractor": texts_header["extractor"],
            "texts_sha256": _sha256_file(config.texts),
        },
        "inputs": {
            "lexicon": lexicon.card(),
            "leakage_fixtures": protected.sources,
            "leakage_mode": "line (word 3-grams not used: legal formulas repeat; reserved booklets are left out whole)",
            "eval_reservations": reservations.card(),
            "booklet_series": {str(series): prefix for series, prefix in BOOKLET_SERIES.items()},
            "length_profile_source": config.length_profile_source,
            "fit_check": config.fit_provenance if config.fit is not None else {"ran": False},
        },
        "corpus_version": config.corpus_version,
        "parameters": {"as_of": config.as_of, "seed": config.seed, "max_line_chars": MAX_LINE_CHARS, "maqaf_allowed": config.allow_maqaf, "lexicon_min_count": lexicon.min_count},
        "laws": {
            "total": len(rows),
            "with_lines": sum(1 for row in rows if row["skipped"] is None),
            "skipped": dict(sorted(Counter(row["skipped"] for row in rows if row["skipped"]).items())),
            "per_series": {str(k): v for k, v in sorted(Counter(row["publication_series_id"] for row in rows).items())},
        },
        "lexicon_filter": {
            "segments_after_character_rules": after_charset,
            "segments_dropped": lexicon_dropped,
            "drop_rate": round(lexicon_dropped / after_charset, 4) if after_charset else None,
            "segments_dropped_suspect": suspect_dropped,
            "suspect_drop_rate": round(suspect_dropped / after_charset, 4) if after_charset else None,
            # A line with suspects from two pairs counts once under each.
            "suspect_drops_by_pair": {key.split(":", 1)[1]: value for key, value in sorted(stats.items()) if key.startswith("suspect_pair:")},
        },
        "eye_check": eye,
        "files": files,
        "pipeline": dict(sorted(stats.items())),
        "length_profile_targets": {key: list(value) if isinstance(value, tuple) else value for key, value in PROFILE_TARGETS.items()},
    }


def render_card(card: dict[str, Any]) -> str:
    eye = card["eye_check"]
    lex = card["lexicon_filter"]
    lines = [
        f"# {card['name']}",
        "",
        f"- **Release:** `{card['release']['release_name']}` ({card['release']['release_licence']}); source licence `{card['licence']['source']}`.",
        f"- **Text quality:** `{card['text_quality']}`. These lines are the Knesset's OCR of the printed page, not a transcription. They never feed word lists, lexicons or dawgs.",
        f"- **Credit:** {card['credit']['text']} ({card['credit']['url']}).",
        f"- **Source:** {card['source']['odata']}, Knessets {card['source']['knessets'][0]}-{card['source']['knessets'][-1]}, fetched {card['source']['fetch_manifest']['fetched_at']} (manifest sha256 `{card['source']['fetch_manifest']['sha256']}`).",
        f"- **Text extraction:** {card['source']['extractor']}; texts sha256 `{card['source']['texts_sha256']}`.",
        "",
        "## Laws",
        "",
        "| | Laws |",
        "| --- | ---: |",
        f"| In the catalogue | {card['laws']['total']:,} |",
        f"| With lines in this build | {card['laws']['with_lines']:,} |",
    ]
    lines += [f"| Left out: `{reason}` | {count:,} |" for reason, count in card["laws"]["skipped"].items()]
    lines += [
        "",
        "## Line quality",
        "",
        f"- **Lexicon filter:** a line is kept only when every word is in a lexicon of {card['inputs']['lexicon']['words']:,} words that occur at least {card['inputs']['lexicon']['min_count']} times in transcription corpora:",
    ]
    lines += [f"  - `{source['file']}` (sha256 `{source['sha256']}`, {source['lines']:,} lines)" for source in card["inputs"]["lexicon"]["sources"]]
    if lex["drop_rate"] is not None:
        rule = card["inputs"]["lexicon"]["suspect_rule"]
        lines += [
            f"- **Drop rate:** {lex['segments_dropped']:,} of {lex['segments_after_character_rules']:,} lines that passed the character rules ({lex['drop_rate']:.1%}) had a word outside the lexicon.",
            f"- **Table cells:** {card['pipeline'].get('text:lines_dropped:table_cell', 0):,} printed lines with fewer than two Hebrew letters were dropped as table cells.",
            f"- **Look-alike words:** {lex['segments_dropped_suspect']:,} more ({lex['suspect_drop_rate']:.1%}) had a word that one OCR confusion ({', '.join(rule['confusions'])}) turns into a word at least {rule['ratio']} times more common (and seen at least {rule['min_variant_count']} times).",
        ]
    if lex.get("suspect_drops_by_pair"):
        lines.append("  - By pair: " + ", ".join(f"{pair} {count:,}" for pair, count in lex["suspect_drops_by_pair"].items()) + ".")
    if eye.get("excluded_samples"):
        lines.append(
            "- **Fresh sample:** the eye-check sample excludes the lines of earlier samples the rules were tuned on: "
            + ", ".join(f"`{row['file']}` (sha256 `{row['sha256']}`, {row['lines']} lines)" for row in eye["excluded_samples"])
            + "."
        )
    if eye["ran"]:
        lines += [
            f"- **Eye check:** {eye['sample_lines']} lines sampled at random, checked against the scans by {eye['checked_by']} on {eye['checked_at']} ({eye['method']}).",
            f"  - Lines checked: {eye['lines_checked']} ({eye['unverifiable_lines']} could not be verified on a damaged scan and are left out of the rates).",
            f"  - Lines with at least one error: {eye['lines_with_error']} ({eye['line_error_rate']:.1%}).",
            f"  - Words wrong: {eye['words_wrong']} of {eye['sample_words']} ({eye['word_error_rate']:.2%}).",
        ]
        lines += [f"  - `{kind}`: {count}" for kind, count in eye["errors_by_kind"].items()]
    else:
        lines.append(f"- **Eye check:** not yet run. The sample is `{EYE_SAMPLE_FILE}` (sha256 `{eye['sample_file_sha256']}`).")
    lines += ["", "## Files", "", "| File | Lines | Laws | sha256 |", "| --- | ---: | ---: | --- |"]
    for name, info in card["files"].items():
        lines.append(f"| `{name}` | {info['lines']:,} | {info['laws']:,} | `{info['sha256']}` |")
    lines += ["", "## Leakage and reservations", "", f"- **Mode:** {card['inputs']['leakage_mode']}."]
    lines += [f"- Fixture: `{source.get('repository')}` `{source.get('path')}` at `{str(source.get('commit'))[:12]}`" for source in card["inputs"]["leakage_fixtures"]]
    lines += [f"- Reservations: set `{row['set']}`, file sha256 `{row['sha256']}`, units {row['units']}" for row in card["inputs"]["eval_reservations"]]
    lines += ["", "## Pipeline", "", "| Step | Count |", "| --- | ---: |"]
    lines += [f"| `{key}` | {value:,} |" for key, value in card["pipeline"].items()]
    lines.append("")
    return "\n".join(lines)

"""Build the ``knesset-plenary`` corpus: the plenary records ("דברי הכנסת") of K1-8 (to 1975) and K13-25.

Design: heocr-lead, 2026-11-20 (``docs/knesset_plenary.md``). Plenary records are official texts that the Israeli
Copyright Act does not protect (section 6), so the corpus is ``htext-cc0``. One release, two files:

- ``knesset_plenary_lines_ocr_<v>.txt``: K1-8, the Knesset's OCR of the printed record (``text_quality: ocr_layer``),
  kept only when every word is in a lexicon built from transcription entries and no word is a likely OCR look-alike;
- ``knesset_plenary_lines_transcription_<v>.txt``: K13-25, the born-digital protocols (``transcription``).

Steps (each its own command, so the expensive ones run once and the private material never leaves the work dir):

1. **extract** (``htext.knesset.extract``): the text of every pinned DOC/DOCX, pinned by sha256.
2. **candidates** (:func:`candidates`): each sitting's paragraphs, cut into lines by the S10b length profile and the
   PBY character rules. Writes the candidate lines and, per sitting, the stream the name tagger reads
   (``hocrgen.privacy.plenary_names.stream_text``). Both are private work files: they still hold every line.
3. **tag** (outside htext): hocrgen's ``ner_stream.py`` (``dicta-il/dictabert-ner``, a filter only) over the streams.
4. **build** (:func:`build`):
   - the privacy gate ``plenary_private_names_v1`` (``hocrgen.privacy.plenary_names.gate_stream_lines``), per
     sitting, before anything is written: a line that names a private person goes whole, and so does every line of
     a sitting the tagger never saw. K13-25 speaker markers prove a heading; K1-8 has only the roster shapes.
     ``refuse_ungated_plenary_lines`` runs on every row;
   - K1-8 only: the lexicon filter and the look-alike rule (as for the laws), with the lexicon built from the
     transcription corpora given and the gated K13-25 lines, never from OCR lines;
   - the eval-overlap drop list (``htext_eval_overlap_drop.v1``; units are sitting ids ``K<k>_<n>``);
   - eval reservations: no kept sitting may be reserved (reserved sittings were never fetched; this checks it);
   - exact duplicates dropped across the corpus;
   - the eye-check sample: K1-8 lines from the sittings whose PDF was fetched for it.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from htext import __version__
from htext.knesset.extract import PLENARY_TEXTS_SCHEMA, read_texts
from htext.knesset.laws import confusion_pair, eye_check_summary
from htext.knesset.lexicon import Lexicon, word_keys
from htext.knesset.plenary_fetch import MANIFEST_SCHEMA, unit_id
from htext.knesset.text import UNRESOLVED_BREAK, _join, fix_ocr
from htext.leakage import Protected, sha256_text
from htext.pby.build import PROFILE_TARGETS, length_profile, profile_passes
from htext.pby.text import MAX_LINE_CHARS, LengthSampler, choose_segment, normalise, word_spans
from htext.release import S6_LABEL, Credit, ReleaseGuard, lexicon_eligible, release_fields
from htext.reservations import Reservations

SOURCE = "knesset-plenary"
SOURCE_ID = "knesset_plenary"  # hocrgen's intake guard treats source ids starting with this as plenary rows
CARD_SCHEMA = "knesset_plenary_corpus_card.v1"
RIGHTS_SCHEMA = "knesset_plenary_rights_index.v1"
LINE_INDEX_SCHEMA = "knesset_plenary_line_index.v1"
CANDIDATES_SCHEMA = "htext_knesset_plenary_candidates.v1"
EYE_SAMPLE_SCHEMA = "knesset_plenary_eye_check_sample.v1"
DROP_SCHEMA = "htext_eval_overlap_drop.v1"
RIGHTS_INDEX_FILE = "knesset_plenary_rights_index.v1.jsonl.gz"
LINE_INDEX_FILE = "knesset_plenary_line_index.v1.jsonl.gz"
EYE_SAMPLE_FILE = "knesset_plenary_eye_check_sample.v1.jsonl"
DEFAULT_CORPUS_VERSION = "v1"
DEFAULT_EYE_SAMPLE = 100
OCR_KNESSETS = frozenset(range(1, 9))
CREDIT = Credit("The Knesset of Israel (Knesset database, plenary records, Divrei ha-Knesset)", "https://main.knesset.gov.il")
GATE_ID = "plenary_private_names_v1"


def corpus_file(quality: str, version: str = DEFAULT_CORPUS_VERSION) -> str:
    return {"ocr_layer": f"knesset_plenary_lines_ocr_{version}.txt", "transcription": f"knesset_plenary_lines_transcription_{version}.txt"}[quality]


def text_quality(knesset: int) -> str:
    return "ocr_layer" if int(knesset) in OCR_KNESSETS else "transcription"


# --- paragraphs: K1-8 (OCR of the printed record) ------------------------------------------------------------------

# A footnote of the printed record: "•) ...", "*) ...".
_OCR_FOOTNOTE = re.compile(r"^\s*[•*]+\s*\)")
_HEBREW_LETTER = re.compile(r"[א-ת]")
_SENTENCE_END = re.compile(r"[.:;?!][\"'”’״׳)]*$")
_HEADING = re.compile(r"^[^:]{2,70}:$")
# A paragraph ends at a line that ends a sentence and is clearly shorter than the column.
SHORT_FRACTION = 0.8


@dataclass(frozen=True)
class PlenaryParagraph:
    text: str
    kind: str  # "body" or "heading"
    structural: bool = False  # a heading the source's own speaker markers prove (K13-25)


def ocr_paragraphs(text: str, stats: dict[str, int] | None = None, is_word: Callable[[str], bool] | None = None) -> list[PlenaryParagraph]:
    """The paragraphs of one K1-8 sitting, from its DOC's OCR text (one printed line per line)."""

    stats = {} if stats is None else stats

    def bump(key: str) -> None:
        stats[key] = stats.get(key, 0) + 1

    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", "\n").split("\n")]
    widths = sorted(len(line) for line in lines if len(_HEBREW_LETTER.findall(line)) >= 2)
    column = widths[len(widths) // 2] if widths else 0
    out: list[PlenaryParagraph] = []
    block: list[str] = []

    def flush(kind: str = "body") -> None:
        if block:
            joined = normalise(fix_ocr(_join(block, is_word, stats), stats), strip_references=False)
            if joined:
                out.append(PlenaryParagraph(joined, kind))
                bump(f"paragraphs:{kind}")
            block.clear()

    for line in lines:
        if not line:
            flush()
            continue
        if _OCR_FOOTNOTE.match(line):
            bump("lines_dropped:footnote")
            flush()
            continue
        if len(_HEBREW_LETTER.findall(line)) < 2:
            # A page number, a column number or a label alone on its line.
            bump("lines_dropped:no_text")
            flush()
            continue
        if _HEADING.match(line) and len(line) < max(column, 1) * SHORT_FRACTION:
            flush()
            block.append(line)
            flush("heading")
            continue
        block.append(line)
        if _SENTENCE_END.search(line) and column and len(line) < column * SHORT_FRACTION:
            flush()
    flush()
    return out


# --- paragraphs: K13-25 (born-digital protocols) ---------------------------------------------------------------------


def born_digital_paragraphs(text: str, stats: dict[str, int] | None = None) -> list[PlenaryParagraph]:
    """The body paragraphs of one K13-25 sitting, with hocrgen's plenary paragraph rules.

    The protocol's markers (``<< דובר >>`` ...) are removed and prove a heading; the front matter (masthead, table of
    contents, agenda) goes, because the body starts at the first speaker heading.
    """

    from hocrgen.tools.knesset_lines import PLENARY, body_start, parse_paragraphs

    stats = {} if stats is None else stats
    paragraphs = parse_paragraphs(text, PLENARY)
    start = body_start(paragraphs)
    if start is None:
        stats["sittings:no_body_start"] = stats.get("sittings:no_body_start", 0) + 1
        return []
    stats["paragraphs_dropped:front_matter"] = stats.get("paragraphs_dropped:front_matter", 0) + start
    out = []
    for p in paragraphs[start:]:
        text_ = normalise(p["text"], strip_references=False)
        if not text_:
            continue
        kind = "heading" if p["heading_shape"] else "body"
        out.append(PlenaryParagraph(text_, kind, structural=bool(p["structural"])))
        stats[f"paragraphs:{kind}"] = stats.get(f"paragraphs:{kind}", 0) + 1
    return out


# --- candidates ----------------------------------------------------------------------------------------------------


@dataclass
class CandidatesConfig:
    manifest: Path
    texts: Path
    output: Path  # a private work dir: candidates.jsonl.gz, ner_input.jsonl
    length_profile: Sequence[int]
    length_profile_source: str
    lexicon_corpora: Sequence[Path] = ()  # transcription corpora: mend K1-8 line-end hyphens
    lexicon_min_count: int = 2
    seed: int = 15
    allow_maqaf: bool = False
    lexicon: Lexicon | None = None  # prebuilt (tests)


def _session_lines(session: dict[str, Any], paragraphs: Sequence[PlenaryParagraph], config: CandidatesConfig, stats: Counter) -> list[dict[str, Any]]:
    unit = unit_id(session)
    sampler = LengthSampler(config.length_profile, f"{config.seed}:plenary:{unit}")
    lines = []
    for index, paragraph in enumerate(paragraphs):
        words = paragraph.text.split()
        heading = paragraph.kind == "heading"
        spans = [(0, len(words))] if heading else word_spans(words, verse=False, targets=sampler)
        for start, end in spans:
            stats["segments"] += 1
            candidate = " ".join(words[start:end])
            if UNRESOLVED_BREAK in candidate:
                stats["segments_dropped:unresolved_line_break"] += 1
                continue
            if heading and len(candidate) > MAX_LINE_CHARS:
                stats["segments_dropped:too_long"] += 1
                continue
            segment, why = choose_segment(None, candidate, threshold=1.0, allow_maqaf=config.allow_maqaf)
            if segment is None:
                stats[f"segments_dropped:{why}"] += 1
                continue
            lines.append({"text": segment.text, "kind": paragraph.kind, "paragraph": index, "is_speaker_heading": paragraph.structural})
    return lines


def candidates(config: CandidatesConfig, *, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Write every sitting's candidate lines and its tagger stream. Nothing here is published."""

    from hocrgen.privacy.plenary_names import stream_text

    manifest = json.loads(config.manifest.read_text(encoding="utf-8"))
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"{config.manifest}: expected schema {MANIFEST_SCHEMA!r}")
    header, texts = read_texts(config.texts, PLENARY_TEXTS_SCHEMA)
    lexicon = config.lexicon or Lexicon.from_files(config.lexicon_corpora, min_count=config.lexicon_min_count)
    stats: Counter = Counter()
    config.output.mkdir(parents=True, exist_ok=True)
    out = config.output / "candidates.jsonl.gz"
    ner = config.output / "ner_input.jsonl"
    with gzip.open(out, "wt", encoding="utf-8") as cand, ner.open("w", encoding="utf-8") as stream_out:
        cand.write(json.dumps({"schema": CANDIDATES_SCHEMA, "texts_sha256": _sha256_file(config.texts), "extractor": header["extractor"],
                               "length_profile_source": config.length_profile_source, "seed": config.seed}) + "\n")
        for number, session in enumerate(sorted(manifest["sessions"], key=lambda s: (s["knesset"], s["number"], s["plenum_session_id"])), 1):
            unit = unit_id(session)
            docs = [d for d in session["documents"] if d["format"] == "DOC" and d.get("sha256")]
            if not docs:
                stats["sittings:no_doc"] += 1
                continue
            doc = docs[0]
            row = texts.get(doc["file"])
            if row is None or row["sha256"] != doc["sha256"]:
                raise ValueError(f"{doc['file']}: no extracted text for the pinned file; rerun the extract step")
            if row.get("text") is None:
                stats["sittings:extract_failed"] += 1
                continue
            local: dict[str, int] = {}
            if session["knesset"] in OCR_KNESSETS:
                paragraphs = ocr_paragraphs(row["text"], local, lexicon.is_word)
            else:
                paragraphs = born_digital_paragraphs(row["text"], local)
            stats.update(local)
            lines = _session_lines(session, paragraphs, config, stats)
            if not lines:
                stats["sittings:no_candidate_lines"] += 1
                continue
            stats["sittings:with_candidates"] += 1
            cand.write(json.dumps({"unit": unit, "knesset": session["knesset"], "number": session["number"],
                                   "plenum_session_id": session["plenum_session_id"], "file": doc["file"], "lines": lines},
                                  ensure_ascii=False) + "\n")
            text, _ = stream_text([{"text": line["text"]} for line in lines])
            stream_out.write(json.dumps({"id": unit, "text": text}, ensure_ascii=False) + "\n")
            if progress and number % 200 == 0:
                progress(f"{number} sittings")
    return {"candidates": str(out), "ner_input": str(ner), "stats": dict(sorted(stats.items()))}


def read_candidates(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        header = json.loads(next(handle))
        if header.get("schema") != CANDIDATES_SCHEMA:
            raise ValueError(f"{path}: expected schema {CANDIDATES_SCHEMA!r}")
        return header, [json.loads(line) for line in handle]


def read_spans(path: Path) -> dict[str, list[dict[str, Any]]]:
    """``ner_stream.py`` output: ``{id: person_spans}`` (stream coordinates)."""
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["id"]] = row["person_spans"]
    return out


# --- build ---------------------------------------------------------------------------------------------------------


@dataclass
class PlenaryConfig:
    manifest: Path
    candidates: Path
    spans: Path
    output: Path
    reservations: Sequence[Path]
    lexicon_corpora: Sequence[Path] = ()  # transcription corpora; the gated K13-25 lines are added
    leakage_fixtures: Sequence[Path] = ()
    lexicon_min_count: int = 2
    as_of: int = 2026
    seed: int = 15
    corpus_version: str = DEFAULT_CORPUS_VERSION
    eye_sample_size: int = DEFAULT_EYE_SAMPLE
    eye_check: Path | None = None
    eval_overlap_drop: Path | None = None
    roster: Any = None  # hocrgen Roster; None = the packaged public_roster_v1
    fit: Callable[[str], str | None] | None = None
    fit_provenance: dict[str, Any] = field(default_factory=dict)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_jsonl_gz(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as handle:
        for row in rows:
            handle.write((json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))


def load_overlap_drop(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    drop = json.loads(path.read_text(encoding="utf-8"))
    if drop.get("schema") != DROP_SCHEMA or drop.get("corpus") != "plenary":
        raise ValueError(f"{path}: expected a {DROP_SCHEMA} file for corpus 'plenary'")
    if not isinstance(drop.get("line_sha256"), list) or not isinstance(drop.get("units"), list):
        raise ValueError(f"{path}: line_sha256 and units must be lists")
    return drop


def _rights_record(session: dict[str, Any], as_of: int) -> dict[str, Any]:
    q = text_quality(session["knesset"])
    return {
        "entry_id": f"plenary:{unit_id(session)}",
        "unit_id": unit_id(session),
        "plenum_session_id": session["plenum_session_id"],
        "knesset": session["knesset"],
        "number": session["number"],
        "name": session.get("name"),
        "start_date": session.get("start_date"),
        "files": [{k: d.get(k) for k in ("format", "url", "file", "sha256", "bytes")} for d in session["documents"]],
        "pd_israel": True,
        "pd_israel_basis": "s6_official_text",
        "pd_us": None,
        "pd_us_basis": "not_assessed",
        "as_of": as_of,
        "source": SOURCE,
        "skipped": None,
        **release_fields(source_licence=S6_LABEL, credit=CREDIT, text_quality=q),
    }


def gate_sitting(row: dict[str, Any], spans: list[dict[str, Any]] | None, roster: Any) -> Any:
    """hocrgen's plenary gate over one sitting's candidate lines, in reading order."""
    from hocrgen.privacy.plenary_names import gate_stream_lines

    lines = [{**line, "knesset": row["knesset"], "unit_id": f"plenary:{row['unit']}", "source_id": SOURCE_ID} for line in row["lines"]]
    return gate_stream_lines(lines, spans, roster, structural_headings=row["knesset"] not in OCR_KNESSETS)


def build(config: PlenaryConfig, *, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    from hocrgen.privacy.plenary_names import packaged_roster, refuse_ungated_plenary_lines

    output = config.output
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(config.manifest.read_text(encoding="utf-8"))
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"{config.manifest}: expected schema {MANIFEST_SCHEMA!r}")
    sessions = {unit_id(s): s for s in manifest["sessions"]}
    cand_header, rows = read_candidates(config.candidates)
    spans = read_spans(config.spans)
    reservations = Reservations.load(config.reservations)
    roster = config.roster or packaged_roster()
    protected = Protected.load(config.leakage_fixtures)
    drop = load_overlap_drop(config.eval_overlap_drop)
    drop_lines = frozenset(drop["line_sha256"]) if drop else frozenset()
    drop_units = {str(u) for u in drop["units"]} if drop else set()
    stats: Counter = Counter()
    gate_reasons: Counter = Counter()
    gate_per_knesset: dict[str, Counter] = defaultdict(Counter)
    records = {u: _rights_record(s, config.as_of) for u, s in sessions.items()}

    # 1. Reservations: reserved sittings were never fetched. Fail closed if one is here anyway.
    reserved_here = sorted(u for u in sessions if reservations.reserved("plenary", u))
    if reserved_here:
        raise ValueError(f"{len(reserved_here)} eval-reserved sittings are in the manifest; refusing to build")

    # 2. Privacy gate, per sitting, before anything is written.
    gated: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for number, row in enumerate(rows, 1):
        unit = row["unit"]
        if unit not in sessions:
            raise ValueError(f"{unit}: candidate sitting not in the manifest")
        result = gate_sitting(row, spans.get(unit), roster)
        k = str(row["knesset"])
        gate_per_knesset[k]["lines_in"] += len(row["lines"])
        gate_per_knesset[k]["kept"] += len(result.kept)
        gate_per_knesset[k]["dropped"] += len(result.dropped)
        for reason, count in result.reasons.items():
            gate_reasons[reason] += count
        refuse_ungated_plenary_lines(result.kept, builder="htext knesset-plenary build")
        gated.append((row, result.kept))
        if progress and number % 500 == 0:
            progress(f"{number}/{len(rows)} sittings gated")

    # 3. Lexicon: transcription entries only (the corpora given, and the gated K13-25 lines).
    transcription_lines = [line["text"] for row, kept in gated if row["knesset"] not in OCR_KNESSETS for line in kept]
    lexicon = Lexicon.from_files(config.lexicon_corpora, min_count=config.lexicon_min_count) if config.lexicon_corpora else None
    extra = Lexicon.from_lines(transcription_lines, min_count=1)
    merged_counts = Counter(lexicon.counts if lexicon else {})
    merged_counts.update(extra.counts)
    kept_counts = {w: c for w, c in merged_counts.items() if c >= config.lexicon_min_count}
    sources = list(lexicon.sources) if lexicon else []
    sources.append({"source": "gated K13-25 lines of this build", "lines": len(transcription_lines)})
    lexicon = Lexicon(set(kept_counts), config.lexicon_min_count, sources, counts=kept_counts)
    ocr_local: Counter = Counter()
    for row, kept in gated:
        if row["knesset"] in OCR_KNESSETS:
            for line in kept:
                for token in line["text"].split():
                    ocr_local.update(word_keys(token))

    # 4. Per-line filters, dedup, and the files.
    seen: set[str] = set()
    out_lines: dict[str, list[dict[str, Any]]] = {"ocr_layer": [], "transcription": []}
    for row, kept in gated:
        unit, quality = row["unit"], text_quality(row["knesset"])
        record = records[unit]
        if unit in drop_units:
            stats["lines_dropped:eval_overlap_sitting"] += len(kept)
            record["skipped"] = "eval_overlap"
            continue
        n = 0
        for line in kept:
            text = line["text"]
            digest = sha256_text(text)
            if quality == "ocr_layer":
                if lexicon.unknown(text):
                    stats["lines_dropped:lexicon"] += 1
                    continue
                suspects = [(w, v) for w, v, rescued in lexicon.look_alikes(text, ocr_local) if not rescued]
                if suspects:
                    stats["lines_dropped:lexicon_suspect"] += 1
                    for pair in sorted({confusion_pair(w, v) for w, v in suspects}):
                        stats[f"suspect_pair:{pair}"] += 1
                    continue
            if digest in protected.lines:
                stats["lines_dropped:leak_line"] += 1
                continue
            if digest in drop_lines:
                stats["lines_dropped:eval_overlap"] += 1
                continue
            if text in seen:
                stats["lines_dropped:duplicate"] += 1
                continue
            if config.fit is not None:
                failure = config.fit(text)
                if failure:
                    stats[f"lines_dropped:fit:{failure}"] += 1
                    continue
            seen.add(text)
            n += 1
            out_lines[quality].append({"text": text, "unit_id": unit, "knesset": row["knesset"], "kind": line["kind"], "sha256": digest,
                                       "privacy_gate": line["privacy_gate"]})
        if not n:
            record["skipped"] = "no_line_kept"
    for unit, record in records.items():
        if record["skipped"] is None and not any(unit == r["unit"] for r, _ in gated):
            record["skipped"] = "no_candidate_lines"
    in_corpus = {line["unit_id"] for lines in out_lines.values() for line in lines}
    for unit, record in records.items():
        if unit not in in_corpus:
            record["htext_release"] = None
            record["skipped"] = record["skipped"] or "no_line_kept"
        stats[f"sittings:{record['skipped'] or 'with_lines'}"] += 1

    files = {}
    for quality, lines in out_lines.items():
        name = corpus_file(quality, config.corpus_version)
        with (output / name).open("w", encoding="utf-8", newline="\n") as handle:
            for line in lines:
                handle.write(line["text"] + "\n")
        profile = length_profile([len(line["text"]) for line in lines]) if lines else {}
        files[name] = {
            "text_quality": quality,
            "lines": len(lines),
            "sittings": len({line["unit_id"] for line in lines}),
            "sha256": _sha256_file(output / name),
            "bytes": (output / name).stat().st_size,
            "length_profile": profile,
            "length_profile_passes": profile_passes(profile) if lines else {},
            "per_knesset": {str(k): v for k, v in sorted(Counter(line["knesset"] for line in lines).items())},
        }
    _write_jsonl_gz(
        output / LINE_INDEX_FILE,
        ({"file": corpus_file(q, config.corpus_version), "unit_id": line["unit_id"], "knesset": line["knesset"], "kind": line["kind"],
          "sha256": line["sha256"]} for q, lines in out_lines.items() for line in lines),
    )
    guard = ReleaseGuard("cc0")
    guard.admit_all(records[u] for u in sorted(in_corpus))
    assert not any(lexicon_eligible(records[u]) and records[u]["knesset"] in OCR_KNESSETS for u in in_corpus)
    _write_jsonl_gz(output / RIGHTS_INDEX_FILE, (records[u] for u in sorted(records, key=lambda u: (records[u]["knesset"], records[u]["number"]))))
    # The reserved-unit check, again, on what is written.
    leaked = sorted(u for u in in_corpus if reservations.reserved("plenary", u))
    if leaked:
        raise ValueError(f"{len(leaked)} eval-reserved sittings reached the corpus; refusing")

    eye_units = {unit_id(s) for s in manifest["sessions"] if any(d["format"] == "PDF" and d.get("sha256") for d in s["documents"])}
    eligible = [line for line in out_lines["ocr_layer"] if line["unit_id"] in eye_units]
    rng = random.Random(f"{config.seed}:eye")
    sample = sorted(rng.sample(eligible, min(config.eye_sample_size, len(eligible))), key=lambda line: (line["knesset"], line["unit_id"]))
    sample_rows = [{"sha256": line["sha256"], "text": line["text"], "unit_id": line["unit_id"], "knesset": line["knesset"],
                    "pdf": next(d["file"] for d in sessions[line["unit_id"]]["documents"] if d["format"] == "PDF")} for line in sample]
    with (output / EYE_SAMPLE_FILE).open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"schema": EYE_SAMPLE_SCHEMA, "seed": config.seed, "lines": len(sample_rows)}, ensure_ascii=False) + "\n")
        for row in sample_rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    eye = eye_check_summary(config.eye_check, _sha256_file(output / EYE_SAMPLE_FILE), sample_rows)

    card = {
        "schema": CARD_SCHEMA,
        "name": "Knesset plenary records (K1-8 to 1975, K13-25)",
        "builder": {"package": "htext", "version": __version__},
        "credit": CREDIT.as_dict(),
        "licence": {"outputs": "CC0-1.0", "source": S6_LABEL},
        "text_rights": "s6_official_text",
        "htext_release": guard.release,
        "release": guard.summary(),
        "text_quality": {corpus_file(q, config.corpus_version): q for q in out_lines},
        "schemas": {"rights_index": RIGHTS_SCHEMA, "line_index": LINE_INDEX_SCHEMA, "eye_check_sample": EYE_SAMPLE_SCHEMA},
        "source": {
            "fetch_manifest": {"file": config.manifest.name, "sha256": _sha256_file(config.manifest), "fetched_at": manifest["source"]["fetched_at"]},
            "selection": manifest["counts"]["selection"],
            "extractor": cand_header["extractor"],
            "texts_sha256": cand_header["texts_sha256"],
            "candidates_sha256": _sha256_file(config.candidates),
            "spans_sha256": _sha256_file(config.spans),
        },
        "privacy": {
            "gate": GATE_ID,
            "tagger": "dicta-il/dictabert-ner (hocrgen ner_stream.py) + hocrgen's cue heuristic; a filter only",
            "roster": {"source": Path(getattr(roster, "source", "") or "").name, "sha256": getattr(roster, "sha256", None)},
            "structural_headings": {"K1-8": False, "K13-25": True},
            "lines_dropped_by_reason": dict(sorted(gate_reasons.items())),
            "per_knesset": {k: dict(v) for k, v in sorted(gate_per_knesset.items(), key=lambda kv: int(kv[0]))},
        },
        "inputs": {
            "lexicon": {**lexicon.card(), "built_from": "transcription only: " + ", ".join(p.name for p in config.lexicon_corpora)
                        + (" + " if config.lexicon_corpora else "") + "the gated K13-25 lines"},
            "leakage_fixtures": protected.sources,
            "eval_reservations": reservations.card(),
            "reserved_sittings_in_corpus": 0,
            "eval_overlap_drop": (
                {"file": config.eval_overlap_drop.name, "sha256": _sha256_file(config.eval_overlap_drop), "targets": len(drop.get("targets", {})),
                 "run_threshold": drop.get("run_threshold"), "line_sha256s": len(drop_lines), "units": len(drop_units),
                 "lines_dropped": stats.get("lines_dropped:eval_overlap", 0), "lines_dropped_with_sittings": stats.get("lines_dropped:eval_overlap_sitting", 0)}
                if drop else {"ran": False}
            ),
            "length_profile_source": cand_header["length_profile_source"],
            "fit_check": config.fit_provenance if config.fit is not None else {"ran": False},
        },
        "corpus_version": config.corpus_version,
        "parameters": {"as_of": config.as_of, "seed": config.seed, "max_line_chars": MAX_LINE_CHARS, "lexicon_min_count": config.lexicon_min_count},
        "sittings": {
            "in_manifest": len(records),
            "with_lines": len(in_corpus),
            "skipped": dict(sorted(Counter(r["skipped"] for r in records.values() if r["skipped"]).items())),
        },
        "eye_check": eye,
        "files": files,
        "pipeline": dict(sorted(stats.items())),
        "length_profile_targets": {key: list(value) if isinstance(value, tuple) else value for key, value in PROFILE_TARGETS.items()},
    }
    (output / "corpus_card.json").write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "CORPUS_CARD.md").write_text(render_card(card), encoding="utf-8")
    names = sorted(p.name for p in output.iterdir() if p.is_file() and p.name != "SHA256SUMS")
    (output / "SHA256SUMS").write_text("".join(f"{_sha256_file(output / n)}  {n}\n" for n in names), encoding="utf-8")
    return card


def render_card(card: dict[str, Any]) -> str:
    p, s = card["privacy"], card["sittings"]
    lines = [
        f"# {card['name']}",
        "",
        f"- **Release:** `htext-cc0` (CC0-1.0); source licence `{card['licence']['source']}`.",
        "- **Text quality:** per file. The K1-8 file is the Knesset's OCR of the printed record (`ocr_layer`); its lines "
        "never feed word lists, lexicons or dawgs. The K13-25 file is the born-digital protocols (`transcription`).",
        f"- **Credit:** {card['credit']['text']} ({card['credit']['url']}).",
        f"- **Source:** fetch manifest sha256 `{card['source']['fetch_manifest']['sha256']}`, fetched "
        f"{card['source']['fetch_manifest']['fetched_at']}; text extraction: {card['source']['extractor']}.",
        "",
        "## Sittings",
        "",
        "| | Sittings |",
        "| --- | ---: |",
        f"| In the fetch manifest | {s['in_manifest']:,} |",
        f"| With lines in this build | {s['with_lines']:,} |",
    ]
    lines += [f"| Left out: `{reason}` | {count:,} |" for reason, count in s["skipped"].items()]
    sel = card["source"]["selection"]
    lines += ["", f"Eval-reserved sittings ({sel.get('reserved_sittings', 0):,}) and sittings with no sitting number "
              f"({sel.get('no_unit_id', 0):,}) were never fetched; no reserved sitting is in the build.", "",
              "## Privacy", "",
              f"- **Gate:** `{p['gate']}` (hocrgen): a line that names a private person is dropped whole. Tagger: {p['tagger']}.",
              "- **Lines dropped by reason:** " + (", ".join(f"`{k}` {v:,}" for k, v in p["lines_dropped_by_reason"].items()) or "none") + ".",
              "", "| Knesset | Lines in | Kept | Dropped |", "| --- | ---: | ---: | ---: |"]
    lines += [f"| {k} | {v.get('lines_in', 0):,} | {v.get('kept', 0):,} | {v.get('dropped', 0):,} |" for k, v in p["per_knesset"].items()]
    eye = card["eye_check"]
    lines += ["", "## Line quality (K1-8)", ""]
    if eye.get("ran"):
        lines += [f"- **Eye check:** {eye['sample_lines']} lines sampled at random, checked against the scans by {eye['checked_by']} on {eye['checked_at']} ({eye['method']}).",
                  f"  - Lines with at least one error: {eye['lines_with_error']} ({eye['line_error_rate']:.1%}); words wrong: {eye['words_wrong']} of {eye['sample_words']} ({eye['word_error_rate']:.2%})."]
    else:
        lines.append(f"- **Eye check:** not yet run. The sample is `{EYE_SAMPLE_FILE}` (sha256 `{eye['sample_file_sha256']}`).")
    lex = card["inputs"]["lexicon"]
    lines.append(f"- **Lexicon:** built from {lex['built_from']}, words seen at least {card['parameters']['lexicon_min_count']} times.")
    lines += ["", "## Files", "", "| File | Text quality | Lines | Sittings | sha256 |", "| --- | --- | ---: | ---: | --- |"]
    lines += [f"| `{n}` | `{i['text_quality']}` | {i['lines']:,} | {i['sittings']:,} | `{i['sha256']}` |" for n, i in card["files"].items()]
    lines += ["", "## Leakage and reservations", ""]
    lines += [f"- Fixture: `{src.get('repository')}` `{src.get('path')}` at `{str(src.get('commit'))[:12]}`" for src in card["inputs"]["leakage_fixtures"]]
    lines += [f"- Reservations: set `{row['set']}`, file sha256 `{row['sha256']}`, units {row['units']}" for row in card["inputs"]["eval_reservations"]]
    drop = card["inputs"]["eval_overlap_drop"]
    if drop.get("ran") is False:
        lines.append("- **Overlap with evaluation text:** not checked in this build.")
    else:
        lines.append(f"- **Overlap with evaluation text:** lines sharing any 6-word sequence with HeOCR's evaluation sets ({drop['targets']} private "
                     f"development, test and held-out targets) were removed, as were sittings with long shared runs. Drop list `{drop['file']}` "
                     f"(sha256 `{drop['sha256']}`): {drop['lines_dropped']:,} lines dropped, and {drop['units']:,} sittings "
                     f"({drop['lines_dropped_with_sittings']:,} lines) left out whole.")
    lines.append("")
    return "\n".join(lines)

"""Build the ``sefaria`` v3 corpus: Sefaria's open-licence Hebrew versions, one release (lane) per build.

The works and the exact versions are pinned in ``data/sefaria/v3/sources.v3.json`` (made from Sefaria's public bulk
export, ``Sefaria/Sefaria-Export`` ``books.json`` at a pinned commit, with the API only for versions the export lacks).
Each version carries Sefaria's licence label, the release it maps to (:mod:`htext.release`), the rights basis, and the
sha256 of the version file as fetched. The builder refuses a file whose sha256 differs.

Rights rule (applied when the sources file is made, recorded per version):

- a CC0, CC-BY or CC-BY-SA label is a licence grant, so it is enough;
- a "Public Domain" label also needs every author dead by 1955 (Sefaria's author topic), else born by 1860 or of a
  pre-modern era; an anonymous work needs a pre-modern era or a composition date by 1860; otherwise the work is out and
  the card lists why.

Text rules: Sefaria segments are walked in order; footnotes (``<sup class="footnote-marker">`` and
``<i class="footnote">``) are removed with their content, other markup is dropped, entities are unescaped. Each
segment is cut by the S10b length profile and the PBY character and niqqud rules into plain and pointed lines.

Reserved works are dropped: a work listed by identity in the eval reservations (``sefaria_works``, e.g. the P-hist
hold-out books, which are held out whole with every edition) is out of every lane and listed in ``out``.
Tags, not drops (contamination policy v2, amendment 1, 2026-11-26): protected-text matches are tagged in the line
index; in-corpus duplicates and lines already in other htext releases (``--dedup-against``) are removed, as a
corpus-quality step. Aramaic-heavy works (Talmud tractates, Targum, Zohar) go
to separate ``*_arc`` files so a Hebrew-only fit can leave them out.
"""

from __future__ import annotations

import gzip
import hashlib
import html
import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence

from htext import __version__
from htext.hebrew import strip_marks
from htext.leakage import Protected
from htext.pby.build import PROFILE_TARGETS, length_profile, profile_passes
from htext.pby.text import DEFAULT_NIQQUD_THRESHOLD, MAX_LINE_CHARS, LengthSampler, choose_segment, normalise, word_spans
from htext.release import RELEASE_LICENCES, RELEASES, Credit, LicenceRefused, ReleaseGuard, release_fields, release_for_licence
from htext.reservations import Reservations

SOURCE = "sefaria"
CREDIT = Credit("Sefaria", "https://www.sefaria.org")
SOURCES_SCHEMA = "htext_sefaria_sources.v3"
CARD_SCHEMA = "sefaria_corpus_card.v3"
RIGHTS_INDEX_FILE = "sefaria_rights_index.v3.jsonl.gz"
LINE_INDEX_FILE = "sefaria_line_index.v3.tsv.gz"
DEFAULT_CORPUS_VERSION = "v3"
SUBSETS = ("plain", "niqqud")
LANGS = ("he", "arc")
_HEBREW = re.compile(r"[א-ת]")


def corpus_file_name(subset: str, lang: str, lane: str, version: str = DEFAULT_CORPUS_VERSION) -> str:
    return f"sefaria_{lane}_lines_{subset}_{lang}_{version}.txt"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


class _Strip(HTMLParser):
    """Text of a Sefaria segment without footnotes and markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[bool] = []  # per open element: inside a footnote?

    def _in_note(self) -> bool:
        return any(self.stack)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        cls = dict(attrs).get("class") or ""
        note = (tag == "sup" and "footnote-marker" in cls) or (tag == "i" and "footnote" in cls)
        if tag in ("br", "p", "div"):
            self.out.append(" ")
        if tag not in ("br", "img", "hr"):
            self.stack.append(note)

    def handle_endtag(self, tag: str) -> None:
        if self.stack and tag not in ("br", "img", "hr"):
            self.stack.pop()

    def handle_data(self, data: str) -> None:
        if not self._in_note():
            self.out.append(data)


def clean_segment(raw: str) -> str:
    """Sefaria segment HTML to text: footnotes removed with their content, other markup dropped."""
    p = _Strip()
    p.feed(raw)
    p.close()
    return normalise(html.unescape("".join(p.out)), strip_references=False)


def segments(text: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[str, str]]:
    """Walk a Sefaria ``text`` value (nested lists, or a dict for complex texts) in order: (segment path, raw)."""
    if isinstance(text, str):
        if text.strip():
            yield ".".join(path), text
    elif isinstance(text, list):
        for i, x in enumerate(text, 1):
            yield from segments(x, path + (str(i),))
    elif isinstance(text, dict):
        for k, x in text.items():
            yield from segments(x, path + (k or "_",))


CODE_VERSION = "sefaria-v3-shards-1"


@dataclass
class SefariaConfig:
    sources: Path  # data/sefaria/v3/sources.v3.json
    inputs: Path  # dir holding the version files as fetched (each version names its ``file``)
    output: Path
    lane: str  # cc0 | by | by-sa
    length_profile: Sequence[int]
    length_profile_source: str
    reservations: Sequence[Path] = ()
    leakage_fixtures: Sequence[Path] = ()
    dedup_against: Sequence[Path] = ()
    seed: int = 15
    corpus_version: str = DEFAULT_CORPUS_VERSION
    niqqud_threshold: float = DEFAULT_NIQQUD_THRESHOLD
    allow_maqaf: bool = False
    fit: Callable[[str], str | None] | None = None  # serial runs (tests); workers use fit_factory
    fit_provenance: dict[str, Any] = field(default_factory=dict)
    fit_factory: str | None = None  # "module:Class": each worker builds one; its .failure is the fit check
    work_dir: Path | None = None  # shards and receipts; default <output>.shards next to the output
    jobs: int = 1


def _key(text: str) -> bytes:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=12).digest()


def atomic_write(path: Path, data: bytes) -> None:
    """Temp file in the same dir, fsync, rename: a crash leaves the old file or none, never a half-written one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    with tmp.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def dedup_hash_file(paths: Sequence[Path], work_dir: Path) -> Path | None:
    """Hashes of the plain forms of every line in other htext releases, computed once into a pinned file."""
    if not paths:
        return None
    pin = hashlib.sha256("".join(f"{p.name}:{_sha256(p)}\n" for p in paths).encode()).hexdigest()[:16]
    out = work_dir / f"dedup_against_{pin}.bin"
    if out.exists():
        return out
    seen: set[bytes] = set()
    for p in paths:
        with (gzip.open(p, "rt", encoding="utf-8") if p.suffix == ".gz" else p.open(encoding="utf-8")) as f:
            for line in f:
                if line.strip():
                    seen.add(_key(strip_marks(line.rstrip("\n"))))
    atomic_write(out, b"".join(sorted(seen)))
    return out


def _load_hashes(path: Path | None) -> frozenset[bytes]:
    if path is None:
        return frozenset()
    raw = path.read_bytes()
    return frozenset(raw[i:i + 12] for i in range(0, len(raw), 12))


def shard_id(title: str, version_title: str) -> str:
    return hashlib.sha1(f"{title}|{version_title}".encode("utf-8")).hexdigest()[:16]


_WORKER: dict[str, Any] = {}


def _init_worker(fit_factory: str | None) -> None:
    if fit_factory:
        import importlib
        mod, cls = fit_factory.split(":")
        _WORKER["fit"] = getattr(importlib.import_module(mod), cls)().failure


def _cached(kind: str, arg: Any, load: Callable[[Any], Any]) -> Any:
    k = (kind, arg)
    if k not in _WORKER:
        _WORKER[k] = load(arg)
    return _WORKER[k]


def build_shard(job: dict[str, Any], fit: Callable[[str], str | None] | None = None) -> dict[str, Any]:
    """One version: cut, filter and tag its lines; commit lines.tsv, then the receipt. Returns the receipt."""
    sdir = Path(job["shard_dir"])
    path = Path(job["path"])
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != job["sha256"]:
        raise ValueError(f"{path}: sha256 does not match the pinned sources")
    doc = json.loads(raw.decode("utf-8"))
    if doc.get("versionTitle") != job["versionTitle"] or doc.get("license") != job["license"]:
        raise ValueError(f"{path}: version title or licence differs from the pinned sources")
    fit = fit if fit is not None else _WORKER.get("fit")
    protected = _cached("protected", tuple(job["leakage_fixtures"]), lambda a: Protected.load([Path(x) for x in a]))
    against = _cached("against", job["dedup_hashes"], lambda a: _load_hashes(Path(a) if a else None))
    sampler = LengthSampler(job["length_profile"], f"{job['seed']}:sefaria:{job['title']}|{job['versionTitle']}")
    stats: Counter = Counter()
    seen: set[bytes] = set()
    rows: list[str] = []
    for seg_path, raw_seg in segments(doc.get("text")):
        para = clean_segment(raw_seg)
        if not para or not _HEBREW.search(para):
            stats["segments_dropped:no_hebrew"] += 1
            continue
        words = para.split()
        plain_words = [strip_marks(w) for w in words]
        for start, end in word_spans(plain_words, verse=False, targets=sampler):
            stats["segments"] += 1
            segment, why = choose_segment(" ".join(words[start:end]), " ".join(plain_words[start:end]),
                                          threshold=job["niqqud_threshold"], allow_maqaf=job["allow_maqaf"])
            if segment is None:
                stats[f"segments_dropped:{why}"] += 1
                continue
            if _key(segment.plain_form) in against:
                stats["segments_dropped:in_other_htext_release"] += 1
                continue
            tk = _key(segment.subset + "\0" + segment.text)
            if tk in seen:
                stats["segments_dropped:duplicate"] += 1
                continue
            if fit is not None and (failure := fit(segment.text)):
                stats[f"segments_dropped:fit:{failure}"] += 1
                continue
            seen.add(tk)
            tags = list(job["work_tags"])
            if leak := protected.leak(segment.text, segment.plain_form):
                tags.append(f"protected_text:{leak}")
                stats[f"lines_tagged:protected_text:{leak}"] += 1
            if "\t" in segment.text or "\n" in segment.text:
                raise ValueError("a line holds a tab or newline")
            rows.append(f"{segment.subset}\t{len(segment.plain_form)}\t{seg_path}\t{','.join(tags)}\t{segment.text}\n")
    data = "".join(rows).encode("utf-8")
    atomic_write(sdir / "lines.tsv", data)
    receipt = {"input_key": job["input_key"], "lines": len(rows), "lines_sha256": hashlib.sha256(data).hexdigest(),
               "stats": dict(sorted(stats.items()))}
    atomic_write(sdir / "receipt.json", json.dumps(receipt, sort_keys=True).encode("utf-8"))
    return receipt


def _done(job: dict[str, Any]) -> bool:
    r = Path(job["shard_dir"]) / "receipt.json"
    if not r.exists():
        return False
    rec = json.loads(r.read_text(encoding="utf-8"))
    lines = Path(job["shard_dir"]) / "lines.tsv"
    return rec.get("input_key") == job["input_key"] and lines.exists() and _sha256(lines) == rec["lines_sha256"]


def build(config: SefariaConfig, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Incremental build: shards per version (skipped when their receipt matches), then a deterministic merge."""
    if config.lane not in RELEASES:
        raise ValueError(f"lane must be one of {RELEASES}")
    sources = json.loads(config.sources.read_text(encoding="utf-8"))
    if sources.get("schema") != SOURCES_SCHEMA:
        raise ValueError(f"{config.sources}: expected schema {SOURCES_SCHEMA!r}")
    reservations = Reservations.load(config.reservations) if config.reservations else None
    protected = Protected.load(config.leakage_fixtures)
    work_dir = config.work_dir or config.output.with_name(config.output.name + ".shards")
    work_dir.mkdir(parents=True, exist_ok=True)
    dedup = dedup_hash_file(list(config.dedup_against), work_dir)
    fit_on = config.fit is not None or config.fit_factory is not None
    common = {
        "lane": config.lane, "seed": config.seed, "niqqud_threshold": config.niqqud_threshold, "allow_maqaf": config.allow_maqaf,
        "length_profile": list(config.length_profile), "leakage_fixtures": [str(p) for p in config.leakage_fixtures],
        "dedup_hashes": str(dedup) if dedup else None,
    }
    pin = json.dumps({"code": CODE_VERSION, "lane": config.lane, "seed": config.seed, "niqqud": config.niqqud_threshold,
                      "maqaf": config.allow_maqaf, "profile": hashlib.sha256(json.dumps(list(config.length_profile)).encode()).hexdigest(),
                      "protected": protected.sources, "dedup": dedup.name if dedup else None,
                      "fit": config.fit_provenance if fit_on else {"ran": False}}, sort_keys=True, default=str)
    jobs, out_list, meta = [], [], []
    for work in sources["works"]:
        for version in work["versions"]:
            try:
                lane = release_for_licence(version["license"])
            except LicenceRefused as refused:
                # Fail closed: a label the release gate does not list is out until a decision admits it.
                if config.lane == "cc0":
                    out_list.append({"title": work["title"], "version": version["versionTitle"], "reason": f"licence_refused:{refused.reason}:{version['license']}"})
                continue
            if lane != config.lane:
                continue
            if not version["rights"]["pass"]:
                out_list.append({"title": work["title"], "version": version["versionTitle"], "reason": version["rights"]["basis"]})
                continue
            if reservations is not None and reservations.reserved("sefaria", work["title"]):
                # Listed by identity in the eval reservations: the work itself is held out, so it leaves the lane.
                out_list.append({"title": work["title"], "version": version["versionTitle"], "reason": "eval_reserved_work"})
                continue
            work_tags = list(work.get("tags", []))
            sid = shard_id(work["title"], version["versionTitle"])
            job = dict(common, title=work["title"], versionTitle=version["versionTitle"], license=version["license"],
                       sha256=version["sha256"], path=str(config.inputs / version["file"]), work_tags=work_tags,
                       shard_dir=str(work_dir / config.lane / sid))
            job["input_key"] = hashlib.sha256(json.dumps([pin, version["sha256"], work["title"], version["versionTitle"], work_tags,
                                                          bool(work.get("aramaic_heavy"))], sort_keys=True).encode()).hexdigest()
            jobs.append(job)
            meta.append((work, version, work_tags))
    pending = [j for j in jobs if not _done(j)]
    if progress:
        progress(f"{config.lane}: {len(jobs)} shards, {len(jobs) - len(pending)} done, {len(pending)} to build")
    if config.jobs > 1 and pending:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(config.jobs, initializer=_init_worker, initargs=(config.fit_factory,)) as ex:
            for k, _ in enumerate(ex.map(build_shard, pending, chunksize=1), 1):
                if progress and k % 100 == 0:
                    progress(f"{config.lane}: {k}/{len(pending)} shards built")
    else:
        if config.fit_factory and config.fit is None:
            _init_worker(config.fit_factory)
        for k, job in enumerate(pending, 1):
            build_shard(job, fit=config.fit)
            if progress and k % 100 == 0:
                progress(f"{config.lane}: {k}/{len(pending)} shards built")
    return _merge(config, sources, jobs, meta, out_list, reservations, protected, dedup, fit_on)


def _merge(config: SefariaConfig, sources: dict[str, Any], jobs: list[dict[str, Any]], meta: list[tuple], out_list: list[dict[str, Any]],
           reservations: Reservations | None, protected: Protected, dedup: Path | None, fit_on: bool) -> dict[str, Any]:
    """Concatenate the shards in sources order, drop in-corpus duplicates (first occurrence wins), write the outputs."""
    stats: Counter = Counter()
    seen: set[bytes] = set()
    out = config.output
    out.mkdir(parents=True, exist_ok=True)
    names = {(s, g): corpus_file_name(s, g, config.lane, config.corpus_version) for s in SUBSETS for g in LANGS}
    tmp = {k: out / f".{n}.tmp" for k, n in names.items()}
    fhs = {k: p.open("w", encoding="utf-8") for k, p in tmp.items()}
    lengths: dict[tuple[str, str], list[int]] = {k: [] for k in names}
    index_tmp = out / f".{LINE_INDEX_FILE}.tmp"
    import io
    index_raw = index_tmp.open("wb")
    index = io.TextIOWrapper(gzip.GzipFile(filename="", mode="wb", fileobj=index_raw, mtime=0), encoding="utf-8")  # mtime 0: same bytes every run
    index.write("subset\tlang\twork\tversion\tsegment\ttags\n")
    records = []
    guard = ReleaseGuard(config.lane)
    try:
        for job, (work, version, work_tags) in zip(jobs, meta):
            if not _done(job):
                raise RuntimeError(f"shard {job['shard_dir']} is not complete")
            receipt = json.loads((Path(job["shard_dir"]) / "receipt.json").read_text(encoding="utf-8"))
            stats.update(receipt["stats"])
            lang = "arc" if work.get("aramaic_heavy") else "he"
            counts: Counter = Counter()
            with (Path(job["shard_dir"]) / "lines.tsv").open(encoding="utf-8") as f:
                for row in f:
                    subset, plen, seg_path, tags, text = row.rstrip("\n").split("\t", 4)
                    tk = _key(subset + "\0" + text)
                    if tk in seen:
                        stats["segments_dropped:duplicate"] += 1
                        continue
                    seen.add(tk)
                    fhs[(subset, lang)].write(text + "\n")
                    lengths[(subset, lang)].append(int(plen))  # as PBY: pointed lines by their plain length
                    counts[f"{subset}_{lang}"] += 1
                    index.write(f"{subset}\t{lang}\t{work['title']}\t{version['versionTitle']}\t{seg_path}\t{tags}\n")
            record = {
                "entry_id": f"sefaria:{work['title']}|{version['versionTitle']}", "title": work["title"],
                "heTitle": work.get("heTitle"), "categories": work.get("categories", []),
                "versionTitle": version["versionTitle"], "versionSource": version.get("versionSource"),
                "sha256": version["sha256"], "fetched_from": version.get("url"), "lines": dict(counts),
                "rights_basis": version["rights"]["basis"], "lang": lang, "tags": work_tags, "source": SOURCE,
                **release_fields(source_licence=version["license"], credit=Credit(f"{version['versionTitle']}, via Sefaria", CREDIT.url)),
            }
            guard.admit(record)
            records.append(record)
    finally:
        for f in fhs.values():
            f.close()
        index.close()
        index_raw.close()
    for k, p in tmp.items():
        os.replace(p, out / names[k])
    os.replace(index_tmp, out / LINE_INDEX_FILE)
    rights = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records).encode("utf-8")
    atomic_write(out / RIGHTS_INDEX_FILE, gzip.compress(rights, mtime=0))
    files = {}
    for k, n in names.items():
        prof = length_profile(lengths[k]) if lengths[k] else {}
        files[n] = {"subset": k[0], "lang": k[1], "lines": len(lengths[k]), "sha256": _sha256(out / n), "bytes": (out / n).stat().st_size,
                    "length_profile": prof, "length_profile_passes": profile_passes(prof) if prof else {}}
    card = {
        "schema": CARD_SCHEMA, "name": f"Sefaria open-licence Hebrew texts ({config.lane})",
        "builder": {"package": "htext", "version": __version__, "code": CODE_VERSION}, "credit": CREDIT.as_dict(),
        "licence": {"outputs": RELEASE_LICENCES[config.lane]}, "htext_release": guard.release, "release": guard.summary(),
        "text_quality": "transcription", "source_tag": SOURCE,
        "source": {k: sources[k] for k in ("export", "rights_rule") if k in sources} | {"sources_sha256": _sha256(config.sources)},
        "works": len({r["title"] for r in records}), "versions": len(records), "out": out_list,
        "inputs": {"eval_reservations": reservations.card() if reservations else [], "leakage_fixtures": protected.sources,
                   "dedup_against": [{"file": p.name, "sha256": _sha256(p)} for p in config.dedup_against],
                   "dedup_hashes": {"file": dedup.name, "sha256": _sha256(dedup)} if dedup else None,
                   "length_profile_source": config.length_profile_source,
                   "fit_check": config.fit_provenance if fit_on else {"ran": False}},
        "corpus_version": config.corpus_version, "contamination_policy": "v2 amendment 1: matches are tags (line index), not drops",
        "parameters": {"seed": config.seed, "niqqud_threshold": config.niqqud_threshold, "max_line_chars": MAX_LINE_CHARS},
        "files": files, "pipeline": dict(sorted(stats.items())),
        "length_profile_targets": {k: list(v) if isinstance(v, tuple) else v for k, v in PROFILE_TARGETS.items()},
    }
    atomic_write(out / "corpus_card.json", (json.dumps(card, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    atomic_write(out / "CORPUS_CARD.md", render_card(card).encode("utf-8"))
    sums = sorted(p.name for p in out.iterdir() if p.is_file() and p.name != "SHA256SUMS" and not p.name.startswith("."))
    atomic_write(out / "SHA256SUMS", "".join(f"{_sha256(out / n)}  {n}\n" for n in sums).encode("utf-8"))
    return card


def render_card(card: dict[str, Any]) -> str:
    out = [f"# {card['name']}", "",
           f"- **Release:** `{card['htext_release']}` ({card['licence']['outputs']}). Source tag `{card['source_tag']}`.",
           f"- **Credit:** {card['credit']['text']} ({card['credit']['url']}); each version's own credit is in the rights index.",
           f"- **Works / versions:** {card['works']:,} / {card['versions']:,}.",
           "- **Aramaic-heavy works** (Talmud tractates, Targum, Zohar) are in the `*_arc` files; leave them out for a Hebrew-only fit.",
           f"- **Contamination:** {card['contamination_policy']}.",
           "", "## Files", "", "| File | Lines | sha256 |", "| --- | ---: | --- |"]
    out += [f"| `{n}` | {i['lines']:,} | `{i['sha256']}` |" for n, i in card["files"].items()]
    out += ["", f"## Left out ({len(card['out'])})", "", "| Work | Version | Reason |", "| --- | --- | --- |"]
    out += [f"| {o['title']} | {o['version']} | `{o['reason']}` |" for o in card["out"]]
    out.append("")
    return "\n".join(out)

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

Tags, not drops (contamination policy v2, amendment 1, 2026-11-26): eval-reserved works and protected-text matches
are tagged in the line index; only in-corpus duplicates and lines already in other htext releases
(``--dedup-against``) are removed, as a corpus-quality step. Aramaic-heavy works (Talmud tractates, Targum, Zohar) go
to separate ``*_arc`` files so a Hebrew-only fit can leave them out.
"""

from __future__ import annotations

import gzip
import hashlib
import html
import json
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
    fit: Callable[[str], str | None] | None = None
    fit_provenance: dict[str, Any] = field(default_factory=dict)


def _key(text: str) -> bytes:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=12).digest()


def _dedup_set(paths: Iterable[Path]) -> set[bytes]:
    seen: set[bytes] = set()
    for p in paths:
        with (gzip.open(p, "rt", encoding="utf-8") if p.suffix == ".gz" else p.open(encoding="utf-8")) as f:
            for line in f:
                if line.strip():
                    seen.add(_key(strip_marks(line.rstrip("\n"))))
    return seen


def build(config: SefariaConfig) -> dict[str, Any]:
    if config.lane not in RELEASES:
        raise ValueError(f"lane must be one of {RELEASES}")
    sources = json.loads(config.sources.read_text(encoding="utf-8"))
    if sources.get("schema") != SOURCES_SCHEMA:
        raise ValueError(f"{config.sources}: expected schema {SOURCES_SCHEMA!r}")
    reservations = Reservations.load(config.reservations) if config.reservations else None
    protected = Protected.load(config.leakage_fixtures)
    against = _dedup_set(config.dedup_against)
    stats: Counter = Counter()
    seen: set[bytes] = set()
    config.output.mkdir(parents=True, exist_ok=True)
    outs = {(s, g): (config.output / corpus_file_name(s, g, config.lane, config.corpus_version)).open("w", encoding="utf-8")
            for s in SUBSETS for g in LANGS}
    lengths: dict[tuple[str, str], list[int]] = {k: [] for k in outs}
    index = gzip.open(config.output / LINE_INDEX_FILE, "wt", encoding="utf-8")
    index.write("subset\tlang\twork\tversion\tsegment\ttags\n")
    records, out_list = [], []
    guard = ReleaseGuard(config.lane)
    try:
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
                path = config.inputs / version["file"]
                if _sha256(path) != version["sha256"]:
                    raise ValueError(f"{path}: sha256 does not match the pinned sources")
                doc = json.loads(path.read_text(encoding="utf-8"))
                if doc.get("versionTitle") != version["versionTitle"] or doc.get("license") != version["license"]:
                    raise ValueError(f"{path}: version title or licence differs from the pinned sources")
                lang = "arc" if work.get("aramaic_heavy") else "he"
                work_tags = list(work.get("tags", []))
                if reservations is not None and reservations.reserved("sefaria", work["title"]):
                    work_tags.append("eval_reserved_work")
                sampler = LengthSampler(config.length_profile, f"{config.seed}:sefaria:{work['title']}|{version['versionTitle']}")
                counts = Counter()
                for seg_path, raw in segments(doc.get("text")):
                    para = clean_segment(raw)
                    if not para or not _HEBREW.search(para):
                        stats["segments_dropped:no_hebrew"] += 1
                        continue
                    words = para.split()
                    plain_words = [strip_marks(w) for w in words]
                    for start, end in word_spans(plain_words, verse=False, targets=sampler):
                        stats["segments"] += 1
                        segment, why = choose_segment(" ".join(words[start:end]), " ".join(plain_words[start:end]),
                                                      threshold=config.niqqud_threshold, allow_maqaf=config.allow_maqaf)
                        if segment is None:
                            stats[f"segments_dropped:{why}"] += 1
                            continue
                        k = _key(segment.plain_form)
                        if k in against:
                            stats["segments_dropped:in_other_htext_release"] += 1
                            continue
                        tk = _key(segment.subset + "\0" + segment.text)
                        if tk in seen:
                            stats["segments_dropped:duplicate"] += 1
                            continue
                        if config.fit is not None and (failure := config.fit(segment.text)):
                            stats[f"segments_dropped:fit:{failure}"] += 1
                            continue
                        seen.add(tk)
                        tags = list(work_tags)
                        if leak := protected.leak(segment.text, segment.plain_form):
                            tags.append(f"protected_text:{leak}")
                            stats[f"lines_tagged:protected_text:{leak}"] += 1
                        outs[(segment.subset, lang)].write(segment.text + "\n")
                        lengths[(segment.subset, lang)].append(len(segment.text))
                        counts[f"{segment.subset}_{lang}"] += 1
                        index.write(f"{segment.subset}\t{lang}\t{work['title']}\t{version['versionTitle']}\t{seg_path}\t{','.join(tags)}\n")
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
        for f in outs.values():
            f.close()
        index.close()
    with gzip.open(config.output / RIGHTS_INDEX_FILE, "wt", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    files = {}
    for (s, g), fh in outs.items():
        p = Path(fh.name)
        prof = length_profile(lengths[(s, g)]) if lengths[(s, g)] else {}
        files[p.name] = {"subset": s, "lang": g, "lines": len(lengths[(s, g)]), "sha256": _sha256(p), "bytes": p.stat().st_size,
                         "length_profile": prof, "length_profile_passes": profile_passes(prof) if prof else {}}
    card = {
        "schema": CARD_SCHEMA, "name": f"Sefaria open-licence Hebrew texts ({config.lane})",
        "builder": {"package": "htext", "version": __version__}, "credit": CREDIT.as_dict(),
        "licence": {"outputs": RELEASE_LICENCES[config.lane]}, "htext_release": guard.release, "release": guard.summary(),
        "text_quality": "transcription", "source_tag": SOURCE,
        "source": {k: sources[k] for k in ("export", "rights_rule") if k in sources} | {"sources_sha256": _sha256(config.sources)},
        "works": len({r["title"] for r in records}), "versions": len(records), "out": out_list,
        "inputs": {"eval_reservations": reservations.card() if reservations else [], "leakage_fixtures": protected.sources,
                   "dedup_against": [{"file": p.name, "sha256": _sha256(p)} for p in config.dedup_against],
                   "length_profile_source": config.length_profile_source,
                   "fit_check": config.fit_provenance if config.fit is not None else {"ran": False}},
        "corpus_version": config.corpus_version, "contamination_policy": "v2 amendment 1: matches are tags (line index), not drops",
        "parameters": {"seed": config.seed, "niqqud_threshold": config.niqqud_threshold, "max_line_chars": MAX_LINE_CHARS},
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

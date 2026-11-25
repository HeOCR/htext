"""Command-line entry point for the htext corpus builders."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from htext.pby.build import DEFAULT_CORPUS_VERSION, DEFAULT_GENRES, DEFAULT_MAX_LINES_PER_WORK, BuildConfig, build
from htext.pby.text import DEFAULT_NIQQUD_THRESHOLD

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CREATORS = ROOT / "data" / "pby" / "creators.json"
DEFAULT_LEAKAGE = ROOT / "data" / "leakage"
S10B_TRAIN = "hebrew_lines_train_v1.txt"


def _length_profile(path: Path | None) -> tuple[list[int], str]:
    if path is None:
        from hocrsyngen.assets import synthetic_data_path

        path = synthetic_data_path(f"texts/{S10B_TRAIN}")
        source = f"hocrsyngen texts/{S10B_TRAIN}"
    else:
        source = str(path)
    lengths = [len(line) for line in path.read_text(encoding="utf-8").split("\n") if line]
    return lengths, source


def _build(args: argparse.Namespace) -> int:
    if not args.reserved and not args.no_reservations:
        raise SystemExit(
            "pass eval's reservations with --reserved (heocr-restricted-eval reservations/eval_reservations_v1.json), "
            "or --no-reservations for an experiment that will not be published"
        )
    lengths, profile_source = _length_profile(args.length_profile)
    fit = None
    allow_maqaf = False
    provenance: dict = {}
    if not args.no_fit_check:
        import hocrsyngen

        from htext.fit import FitChecker, hocrsyngen_commit

        commit = hocrsyngen_commit() or args.hocrsyngen_commit
        if not commit:
            raise SystemExit("hocrsyngen was not installed from git; pass --hocrsyngen-commit so the card records it")
        checker = FitChecker()
        fit = checker.failure
        allow_maqaf = checker.maqaf_allowed()
        provenance = {
            "ran": True,
            "hocrsyngen_version": getattr(hocrsyngen, "__version__", None),
            "hocrsyngen_commit": commit,
            "bodies": [body.__dict__ for body in checker.bodies],
            "maqaf_glyph_check": allow_maqaf,
        }
    terms: list[str] = []
    if args.screen_terms:
        terms = [line.strip() for line in args.screen_terms.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
    leakage = sorted(args.leakage.glob("*.hashes.json")) if args.leakage.is_dir() else [args.leakage]
    config = BuildConfig(
        dump=args.dump,
        creators=args.creators,
        leakage_fixtures=leakage,
        reservations=args.reserved,
        output=args.output,
        length_profile=lengths,
        length_profile_source=profile_source,
        as_of=args.as_of,
        seed=args.seed,
        niqqud_threshold=args.niqqud_threshold,
        genres=tuple(args.genres.split(",")),
        max_lines_per_work=args.max_lines_per_work or None,
        corpus_version=args.corpus_version,
        screen_terms=terms,
        screen_terms_source=str(args.screen_terms) if args.screen_terms else None,
        fit=fit,
        allow_maqaf=allow_maqaf,
        fit_provenance=provenance,
    )
    card = build(config, progress=lambda message: print(message, file=sys.stderr))
    for name, info in card["files"].items():
        print(f"{name}: {info['lines']} lines, {info['bytes']} bytes")
    return 0


def _fit(args: argparse.Namespace) -> tuple:
    if args.no_fit_check:
        return None, False, {}
    import hocrsyngen

    from htext.fit import FitChecker, hocrsyngen_commit

    commit = hocrsyngen_commit() or args.hocrsyngen_commit
    if not commit:
        raise SystemExit("hocrsyngen was not installed from git; pass --hocrsyngen-commit so the card records it")
    checker = FitChecker()
    allow_maqaf = checker.maqaf_allowed()
    provenance = {
        "ran": True,
        "hocrsyngen_version": getattr(hocrsyngen, "__version__", None),
        "hocrsyngen_commit": commit,
        "bodies": [body.__dict__ for body in checker.bodies],
        "maqaf_glyph_check": allow_maqaf,
    }
    return checker.failure, allow_maqaf, provenance


def _laws_extract(args: argparse.Namespace) -> int:
    import json

    from htext.knesset.extract import extract_all

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    counts = extract_all(manifest, args.inputs, args.output, progress=lambda message: print(message, file=sys.stderr))
    print(json.dumps(counts))
    return 1 if counts["failed"] else 0


def _laws_build(args: argparse.Namespace) -> int:
    from htext.knesset.laws import LawsConfig, build as build_laws

    if not args.reserved and not args.no_reservations:
        raise SystemExit("pass eval's reservations with --reserved, or --no-reservations for an experiment that will not be published")
    if not args.lexicon_corpus:
        raise SystemExit("pass at least one transcription corpus with --lexicon-corpus (for example the pby v2 plain and niqqud files)")
    lengths, profile_source = _length_profile(args.length_profile)
    fit, allow_maqaf, provenance = _fit(args)
    leakage = sorted(args.leakage.glob("*.hashes.json")) if args.leakage.is_dir() else [args.leakage]
    config = LawsConfig(
        manifest=args.manifest,
        texts=args.texts,
        lexicon_corpora=args.lexicon_corpus,
        leakage_fixtures=leakage,
        reservations=args.reserved,
        output=args.output,
        length_profile=lengths,
        length_profile_source=profile_source,
        lexicon_min_count=args.lexicon_min_count,
        seed=args.seed,
        corpus_version=args.corpus_version,
        fit=fit,
        allow_maqaf=allow_maqaf,
        fit_provenance=provenance,
        eye_sample_size=args.eye_sample,
        eye_exclude=args.eye_exclude,
        eye_check=args.eye_check,
        eval_overlap_drop=args.eval_overlap_drop,
        eye_check_inherited=tuple(args.eye_check_inherited) if args.eye_check_inherited else None,
    )
    card = build_laws(config, progress=lambda message: print(message, file=sys.stderr))
    for name, info in card["files"].items():
        print(f"{name}: {info['lines']} lines from {info['laws']} laws")
    print(f"lexicon drop rate: {card['lexicon_filter']['drop_rate']}")
    return 0


def _plenary_candidates(args: argparse.Namespace) -> int:
    import json

    from htext.knesset.plenary import CandidatesConfig, candidates

    lengths, profile_source = _length_profile(args.length_profile)
    result = candidates(
        CandidatesConfig(
            manifest=args.manifest, texts=args.texts, output=args.work, length_profile=lengths, length_profile_source=profile_source,
            lexicon_corpora=args.lexicon_corpus, seed=args.seed,
        ),
        progress=lambda message: print(message, file=sys.stderr),
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _plenary_build(args: argparse.Namespace) -> int:
    from htext.knesset.plenary import PlenaryConfig, build as build_plenary

    if not args.reserved:
        raise SystemExit("pass eval's reservations with --reserved; the plenary build has no experiment mode")
    fit, _allow_maqaf, provenance = _fit(args)
    leakage = sorted(args.leakage.glob("*.hashes.json")) if args.leakage.is_dir() else [args.leakage]
    card = build_plenary(
        PlenaryConfig(
            manifest=args.manifest, candidates=args.work / "candidates.jsonl.gz", spans=args.spans, output=args.output,
            reservations=args.reserved, lexicon_corpora=args.lexicon_corpus, leakage_fixtures=leakage, seed=args.seed,
            corpus_version=args.corpus_version, eye_sample_size=args.eye_sample, eye_check=args.eye_check,
            eval_overlap_drop=args.eval_overlap_drop, fit=fit, fit_provenance=provenance,
        ),
        progress=lambda message: print(message, file=sys.stderr),
    )
    for name, info in card["files"].items():
        print(f"{name}: {info['lines']} lines from {info['sittings']} sittings ({info['text_quality']})")
    print(f"privacy gate drops: {card['privacy']['lines_dropped_by_reason']}")
    return 0


def _gutenberg_build(args: argparse.Namespace) -> int:
    from htext.gutenberg import GutenbergConfig, build as build_gutenberg

    if not args.reserved:
        raise SystemExit("pass eval's reservations with --reserved")
    lengths, profile_source = _length_profile(args.length_profile)
    fit, allow_maqaf, provenance = _fit(args)
    leakage = sorted(args.leakage.glob("*.hashes.json")) if args.leakage.is_dir() else [args.leakage]
    card = build_gutenberg(GutenbergConfig(
        sources=args.sources, inputs=args.inputs, output=args.output, length_profile=lengths, length_profile_source=profile_source,
        reservations=args.reserved, leakage_fixtures=leakage, dedup_against=args.dedup_against, seed=args.seed,
        corpus_version=args.corpus_version, allow_maqaf=allow_maqaf, fit=fit, fit_provenance=provenance,
    ))
    for name, info in card["files"].items():
        print(f"{name}: {info['lines']} lines")
    print(f"works: {len(card['works'])} in, {len(card['out'])} out")
    return 0


def _tanakh_build(args: argparse.Namespace) -> int:
    from htext.tanakh import WLC_COMMIT, TanakhConfig, build as build_tanakh

    if not args.reserved and not args.no_reservations:
        raise SystemExit("pass eval's reservations with --reserved, or --no-reservations for an experiment that will not be published")
    if args.source_commit != WLC_COMMIT:
        raise SystemExit(f"--source-commit {args.source_commit} is not the pinned WLC commit {WLC_COMMIT}; update WLC_COMMIT in a reviewed PR first")
    lengths, profile_source = _length_profile(args.length_profile)
    fit, allow_maqaf, provenance = _fit(args)
    leakage = sorted(args.leakage.glob("*.hashes.json")) if args.leakage.is_dir() else [args.leakage]
    config = TanakhConfig(
        wlc=args.wlc,
        leakage_fixtures=leakage,
        output=args.output,
        length_profile=lengths,
        length_profile_source=profile_source,
        source_commit=args.source_commit,
        reservations=args.reserved,
        seed=args.seed,
        corpus_version=args.corpus_version,
        fit=fit,
        allow_maqaf=allow_maqaf,
        fit_provenance=provenance,
    )
    card = build_tanakh(config, progress=lambda message: print(message, file=sys.stderr))
    for name, info in card["files"].items():
        print(f"{name}: {info['lines']} lines from {info['books']} books")
    return 0


def _wikisource_build(args: argparse.Namespace) -> int:
    from htext.wikisource import BuildConfig, build

    lengths, profile_source = _length_profile(args.length_profile)
    fit, allow_maqaf, provenance = _fit(args)
    leakage = sorted(args.leakage.glob("*.hashes.json")) if args.leakage.is_dir() else [args.leakage]
    card = build(
        BuildConfig(
            dump=args.dump, output=args.output, reservations=args.reserved, eval_overlap_drop=args.eval_overlap_drop,
            length_profile=lengths, length_profile_source=profile_source, leakage_fixtures=leakage,
            seed=args.seed, corpus_version=args.corpus_version, niqqud_threshold=args.niqqud_threshold,
            fit=fit, allow_maqaf=allow_maqaf, fit_provenance=provenance,
            works=args.works, law_sources=args.law_sources, knesset_laws_v2=args.knesset_laws_v2,
        ),
        progress=lambda message: print(message, file=sys.stderr),
    )
    for name, info in [*card["files"].items(), ("Total", card["totals"])]:
        print(f"{name}: {info['pages']:,} pages, {info['lines']:,} lines, {info['characters']:,} characters")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="htext")
    commands = parser.add_subparsers(dest="command", required=True)
    pby = commands.add_parser("pby", help="Project Ben-Yehuda corpus")
    pby_commands = pby.add_subparsers(dest="pby_command", required=True)
    build_parser = pby_commands.add_parser("build", help="build the PBY corpus from a local dump checkout")
    build_parser.add_argument("--dump", type=Path, required=True, help="local public_domain_dump checkout at the pinned commit")
    build_parser.add_argument("--output", type=Path, required=True)
    build_parser.add_argument("--creators", type=Path, default=DEFAULT_CREATORS)
    build_parser.add_argument("--leakage", type=Path, default=DEFAULT_LEAKAGE, help="a fixture file, or a directory of *.hashes.json")
    build_parser.add_argument(
        "--reserved", type=Path, action="append", default=[],
        help="an htext_reservations.v1 file of eval-reserved works (repeatable); reserved works are left out whole",
    )
    build_parser.add_argument(
        "--no-reservations", action="store_true",
        help="build without eval reservations (experiments only; the card records that none were loaded)",
    )
    build_parser.add_argument("--as-of", type=int, default=2026)
    build_parser.add_argument("--seed", type=int, default=15)
    build_parser.add_argument("--niqqud-threshold", type=float, default=DEFAULT_NIQQUD_THRESHOLD)
    build_parser.add_argument("--genres", default=",".join(DEFAULT_GENRES))
    build_parser.add_argument("--max-lines-per-work", type=int, default=DEFAULT_MAX_LINES_PER_WORK or 0, help="0 for no cap (the default since v2)")
    build_parser.add_argument("--corpus-version", default=DEFAULT_CORPUS_VERSION, help="names the corpus files (default %(default)s)")
    build_parser.add_argument("--screen-terms", type=Path, default=None, help="content screen: one term per line")
    build_parser.add_argument("--length-profile", type=Path, default=None, help="text file whose line lengths are the target profile (default: hocrsyngen S10b train)")
    build_parser.add_argument("--hocrsyngen-commit", default=None, help="record this hocrsyngen commit when pip did not record one")
    build_parser.add_argument("--no-fit-check", action="store_true", help="skip the hocrsyngen no-loss wrap check (the card records it)")
    build_parser.set_defaults(handler=_build)

    laws = commands.add_parser("knesset-laws", help="Knesset laws as published (K1-8)")
    laws_commands = laws.add_subparsers(dest="laws_command", required=True)
    extract_parser = laws_commands.add_parser("extract", help="extract the text of every pinned DOC file")
    extract_parser.add_argument("--manifest", type=Path, required=True, help="the fetch manifest (htext_knesset_laws_sources.v1)")
    extract_parser.add_argument("--inputs", type=Path, required=True, help="the fetch's download directory")
    extract_parser.add_argument("--output", type=Path, required=True, help="texts file to write (.jsonl.gz)")
    extract_parser.set_defaults(handler=_laws_extract)
    laws_build = laws_commands.add_parser("build", help="build the corpus from the manifest and the extracted texts")
    laws_build.add_argument("--manifest", type=Path, required=True)
    laws_build.add_argument("--texts", type=Path, required=True, help="the extract step's output")
    laws_build.add_argument("--output", type=Path, required=True)
    laws_build.add_argument("--lexicon-corpus", type=Path, action="append", default=[], help="a transcription corpus file (repeatable)")
    laws_build.add_argument("--lexicon-min-count", type=int, default=2)
    laws_build.add_argument("--leakage", type=Path, default=DEFAULT_LEAKAGE)
    laws_build.add_argument("--reserved", type=Path, action="append", default=[])
    laws_build.add_argument("--no-reservations", action="store_true")
    laws_build.add_argument("--seed", type=int, default=15)
    laws_build.add_argument("--corpus-version", default="v1")
    laws_build.add_argument("--eye-sample", type=int, default=100, help="lines in the eye-check sample")
    laws_build.add_argument(
        "--eye-exclude", type=Path, action="append", default=[],
        help="an earlier eye-check sample file whose lines are not drawn again (repeatable)",
    )
    laws_build.add_argument("--eye-check", type=Path, default=None, help="a completed htext_eye_check.v1 file for this build's sample")
    laws_build.add_argument(
        "--eye-check-inherited",
        nargs=2,
        type=Path,
        metavar=("SAMPLE", "CHECK"),
        default=None,
        help="an earlier build's eye-check sample and its htext_eye_check.v1 file: their verdicts on lines still in this build stand in",
    )
    laws_build.add_argument(
        "--eval-overlap-drop", type=Path, default=None, help="an htext_eval_overlap_drop.v1 file: lines and laws that overlap HeOCR's evaluation text"
    )
    laws_build.add_argument("--length-profile", type=Path, default=None)
    laws_build.add_argument("--hocrsyngen-commit", default=None)
    laws_build.add_argument("--no-fit-check", action="store_true")
    laws_build.set_defaults(handler=_laws_build)

    plenary = commands.add_parser("knesset-plenary", help="Knesset plenary records (K1-8 to 1975, K13-25)")
    plenary_commands = plenary.add_subparsers(dest="plenary_command", required=True)
    p_extract = plenary_commands.add_parser("extract", help="extract the text of every pinned DOC/DOCX file")
    p_extract.add_argument("--manifest", type=Path, required=True, help="the fetch manifest (htext_knesset_plenary_sources.v1)")
    p_extract.add_argument("--inputs", type=Path, required=True, help="the fetch's download directory")
    p_extract.add_argument("--output", type=Path, required=True, help="texts file to write (.jsonl.gz)")
    p_extract.set_defaults(handler=_laws_extract)
    p_cand = plenary_commands.add_parser("candidates", help="candidate lines and tagger streams (private work files)")
    p_cand.add_argument("--manifest", type=Path, required=True)
    p_cand.add_argument("--texts", type=Path, required=True, help="the extract step's output")
    p_cand.add_argument("--work", type=Path, required=True, help="private work dir (never published or committed)")
    p_cand.add_argument("--lexicon-corpus", type=Path, action="append", default=[], help="a transcription corpus file, for line-end hyphens (repeatable)")
    p_cand.add_argument("--seed", type=int, default=15)
    p_cand.add_argument("--length-profile", type=Path, default=None)
    p_cand.set_defaults(handler=_plenary_candidates)
    p_build = plenary_commands.add_parser("build", help="gate, filter and write the corpus")
    p_build.add_argument("--manifest", type=Path, required=True)
    p_build.add_argument("--work", type=Path, required=True, help="the candidates step's work dir")
    p_build.add_argument("--spans", type=Path, required=True, help="hocrgen ner_stream.py output over WORK/ner_input.jsonl")
    p_build.add_argument("--output", type=Path, required=True)
    p_build.add_argument("--reserved", type=Path, action="append", default=[])
    p_build.add_argument("--lexicon-corpus", type=Path, action="append", default=[], help="a transcription corpus file (repeatable)")
    p_build.add_argument("--leakage", type=Path, default=DEFAULT_LEAKAGE)
    p_build.add_argument("--seed", type=int, default=15)
    p_build.add_argument("--corpus-version", default="v1")
    p_build.add_argument("--eye-sample", type=int, default=100)
    p_build.add_argument("--eye-check", type=Path, default=None)
    p_build.add_argument("--eval-overlap-drop", type=Path, default=None)
    p_build.add_argument("--hocrsyngen-commit", default=None)
    p_build.add_argument("--no-fit-check", action="store_true")
    p_build.set_defaults(handler=_plenary_build)

    gutenberg = commands.add_parser("gutenberg", help="Project Gutenberg public-domain Hebrew texts")
    gutenberg_commands = gutenberg.add_subparsers(dest="gutenberg_command", required=True)
    g_build = gutenberg_commands.add_parser("build", help="build the corpus from the pinned sources and the fetched texts")
    g_build.add_argument("--sources", type=Path, default=Path("data/gutenberg/sources.v1.json"))
    g_build.add_argument("--inputs", type=Path, required=True, help="dir with pg<N>.txt as fetched from the pinned mirror URLs")
    g_build.add_argument("--output", type=Path, required=True)
    g_build.add_argument("--reserved", type=Path, action="append", default=[])
    g_build.add_argument("--leakage", type=Path, default=DEFAULT_LEAKAGE)
    g_build.add_argument("--dedup-against", type=Path, action="append", default=[], help="another corpus's lines file: its lines are dropped (repeatable)")
    g_build.add_argument("--seed", type=int, default=15)
    g_build.add_argument("--corpus-version", default="v1")
    g_build.add_argument("--length-profile", type=Path, default=None)
    g_build.add_argument("--hocrsyngen-commit", default=None)
    g_build.add_argument("--no-fit-check", action="store_true")
    g_build.set_defaults(handler=_gutenberg_build)

    tanakh = commands.add_parser("tanakh", help="the Westminster Leningrad Codex, pointed and plain")
    tanakh_commands = tanakh.add_subparsers(dest="tanakh_command", required=True)
    tanakh_build = tanakh_commands.add_parser("build", help="build the corpus from a local morphhb checkout at the pinned commit")
    tanakh_build.add_argument("--wlc", type=Path, required=True, help="the checkout's wlc/ directory (openscriptures/morphhb)")
    tanakh_build.add_argument("--source-commit", required=True, help="the morphhb commit the checkout is at; must equal htext.tanakh.WLC_COMMIT")
    tanakh_build.add_argument("--output", type=Path, required=True)
    tanakh_build.add_argument("--leakage", type=Path, default=DEFAULT_LEAKAGE)
    tanakh_build.add_argument("--reserved", type=Path, action="append", default=[])
    tanakh_build.add_argument("--no-reservations", action="store_true")
    tanakh_build.add_argument("--seed", type=int, default=15)
    tanakh_build.add_argument("--corpus-version", default="v1")
    tanakh_build.add_argument("--length-profile", type=Path, default=None)
    tanakh_build.add_argument("--hocrsyngen-commit", default=None)
    tanakh_build.add_argument("--no-fit-check", action="store_true")
    tanakh_build.set_defaults(handler=_tanakh_build)

    wikisource = commands.add_parser("wikisource", help="Hebrew Wikisource text")
    ws_commands = wikisource.add_subparsers(dest="wikisource_command", required=True)
    ws_build = ws_commands.add_parser("build", help="build from the pinned local Hebrew Wikisource dump")
    ws_build.add_argument("--dump", type=Path, required=True, help="the pinned pages-articles.xml.bz2 file")
    ws_build.add_argument("--output", type=Path, required=True, help="a new output directory")
    ws_build.add_argument("--reserved", type=Path, action="append", required=True, help="eval reservation manifest (repeatable)")
    ws_build.add_argument("--eval-overlap-drop", type=Path, required=True, help="htext_eval_overlap_drop.v1 for corpus 'wikisource'")
    ws_build.add_argument("--works", type=Path, help="reviewed works.v1.json; selects main-namespace mode")
    ws_build.add_argument("--law-sources", type=Path, help="reviewed article revisions and Reshumot booklet IDs")
    ws_build.add_argument("--knesset-laws-v2", type=Path, help="published knesset_laws_lines_plain_v2.txt for deduplication")
    ws_build.add_argument("--leakage", type=Path, default=DEFAULT_LEAKAGE)
    ws_build.add_argument("--length-profile", type=Path, default=None)
    ws_build.add_argument("--seed", type=int, default=15)
    ws_build.add_argument("--corpus-version", default="v1")
    ws_build.add_argument("--niqqud-threshold", type=float, default=DEFAULT_NIQQUD_THRESHOLD)
    ws_build.add_argument("--hocrsyngen-commit", default=None)
    ws_build.add_argument("--no-fit-check", action="store_true")
    ws_build.set_defaults(handler=_wikisource_build)
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())

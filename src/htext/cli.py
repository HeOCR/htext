"""Command-line entry point: ``htext pby build``, ``htext knesset-laws extract`` and ``htext knesset-laws build``."""

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
        eye_check=args.eye_check,
    )
    card = build_laws(config, progress=lambda message: print(message, file=sys.stderr))
    for name, info in card["files"].items():
        print(f"{name}: {info['lines']} lines from {info['laws']} laws")
    print(f"lexicon drop rate: {card['lexicon_filter']['drop_rate']}")
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
    laws_build.add_argument("--eye-check", type=Path, default=None, help="a completed htext_eye_check.v1 file for this build's sample")
    laws_build.add_argument("--length-profile", type=Path, default=None)
    laws_build.add_argument("--hocrsyngen-commit", default=None)
    laws_build.add_argument("--no-fit-check", action="store_true")
    laws_build.set_defaults(handler=_laws_build)
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())

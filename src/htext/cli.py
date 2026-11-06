"""Command-line entry point: ``htext pby build``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from htext.pby.build import DEFAULT_GENRES, DEFAULT_MAX_LINES_PER_WORK, BuildConfig, build
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
        output=args.output,
        length_profile=lengths,
        length_profile_source=profile_source,
        as_of=args.as_of,
        seed=args.seed,
        niqqud_threshold=args.niqqud_threshold,
        genres=tuple(args.genres.split(",")),
        max_lines_per_work=args.max_lines_per_work or None,
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
    build_parser.add_argument("--as-of", type=int, default=2026)
    build_parser.add_argument("--seed", type=int, default=15)
    build_parser.add_argument("--niqqud-threshold", type=float, default=DEFAULT_NIQQUD_THRESHOLD)
    build_parser.add_argument("--genres", default=",".join(DEFAULT_GENRES))
    build_parser.add_argument("--max-lines-per-work", type=int, default=DEFAULT_MAX_LINES_PER_WORK, help="0 for no cap")
    build_parser.add_argument("--screen-terms", type=Path, default=None, help="content screen: one term per line")
    build_parser.add_argument("--length-profile", type=Path, default=None, help="text file whose line lengths are the target profile (default: hocrsyngen S10b train)")
    build_parser.add_argument("--hocrsyngen-commit", default=None, help="record this hocrsyngen commit when pip did not record one")
    build_parser.add_argument("--no-fit-check", action="store_true", help="skip the hocrsyngen no-loss wrap check (the card records it)")
    build_parser.set_defaults(handler=_build)
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())

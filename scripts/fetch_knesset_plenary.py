"""Fetch the Knesset plenary protocols in scope and write a pinned manifest.

Usage (from the repository root, with network access; run once per pin):

    python scripts/fetch_knesset_plenary.py \
        --reserved PATH/TO/eval_reservations_v4.json \
        --inputs PATH/OUTSIDE/GIT/knesset-plenary \
        --manifest PATH/OUTSIDE/GIT/knesset-plenary/sources.v1.json

This is the only step of the ``knesset-plenary`` intake that uses the network;
see ``htext.knesset.plenary_fetch`` for what it fetches and how. Eval's
reservations are required: reserved sittings are dropped before any file is
fetched. Files go to ``--inputs``, which must be outside git. ``--log``
(default: ``<inputs>/fetch_log.jsonl``) records every request.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_knesset_laws import _inside_git  # noqa: E402

from htext.knesset.fetch import PoliteClient  # noqa: E402
from htext.knesset.plenary_fetch import EYE_CHECK_PDFS, download, fetch_catalogue, manifest  # noqa: E402
from htext.reservations import Reservations  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reserved", type=Path, action="append", required=True, help="eval reservations file (repeatable)")
    parser.add_argument("--inputs", type=Path, required=True, help="download directory, outside git")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--log", type=Path, default=None)
    parser.add_argument("--eye-check-pdfs", type=int, default=EYE_CHECK_PDFS, help=f"K1-8 sittings whose PDF is fetched (default {EYE_CHECK_PDFS})")
    parser.add_argument("--seed", type=int, default=15)
    parser.add_argument("--min-interval", type=float, default=1.0, help="seconds between requests (at least 1)")
    parser.add_argument("--catalogue-only", action="store_true", help="list sittings and files, download nothing")
    args = parser.parse_args()

    if args.min_interval < 1.0:
        parser.error("--min-interval must be at least 1 second")
    if _inside_git(args.inputs):
        parser.error(f"{args.inputs} is inside a git work tree; downloads stay outside git")
    reservations = Reservations.load(args.reserved)
    if not reservations.count("plenary"):
        parser.error("the reservations name no plenary units; refusing to fetch without them")
    args.inputs.mkdir(parents=True, exist_ok=True)
    client = PoliteClient(min_interval=args.min_interval, log_path=args.log or args.inputs / "fetch_log.jsonl")

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    catalogue = fetch_catalogue(client, reservations, eye_check_pdfs=args.eye_check_pdfs, seed=args.seed)
    print(json.dumps(catalogue["selection"]), file=sys.stderr)
    counts = {"downloaded": 0, "reused": 0, "failed": 0}
    if not args.catalogue_only:
        counts = download(client, catalogue, args.inputs)
    document = manifest(catalogue, reservations=reservations, counts=counts, fetched_at=fetched_at)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in document["counts"].items() if k != "per_knesset"}), file=sys.stderr)
    if counts["failed"]:
        sys.exit(f"{counts['failed']} files failed; rerun to retry them")


if __name__ == "__main__":
    main()

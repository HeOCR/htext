"""Fetch the Knesset's enacted laws (K1-8 by default) and write a pinned manifest.

Usage (from the repository root, with network access; run once per pin):

    python scripts/fetch_knesset_laws.py --knessets 1-8 \
        --inputs PATH/OUTSIDE/GIT/knesset-laws \
        --manifest data/knesset_laws/sources.v1.json

This is the only step of the ``knesset-laws`` intake that uses the network; see
``htext.knesset.fetch`` for what it fetches and how. Files go to ``--inputs``,
which must be outside git. The manifest pins every file by sha256 and is the
build's input list. ``--log`` (default: ``<inputs>/fetch_log.jsonl``) records
every request.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from htext.knesset.fetch import FORMATS, PoliteClient, download, fetch_catalogue, manifest, parse_knessets


def _inside_git(path: Path) -> bool:
    probe = path if path.exists() else path.parent
    while not probe.exists():
        probe = probe.parent
    result = subprocess.run(
        ["git", "-C", str(probe), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True, check=False
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--knessets", default="1-8", help="e.g. 1-8 or 1,3,5 (default 1-8)")
    parser.add_argument("--formats", default=",".join(FORMATS), help="file formats to fetch (default DOC,PDF)")
    parser.add_argument("--inputs", type=Path, required=True, help="download directory, outside git")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--log", type=Path, default=None)
    parser.add_argument("--min-interval", type=float, default=1.0, help="seconds between requests (at least 1)")
    parser.add_argument("--catalogue-only", action="store_true", help="list bills and files, download nothing")
    args = parser.parse_args()

    if args.min_interval < 1.0:
        parser.error("--min-interval must be at least 1 second")
    if _inside_git(args.inputs):
        parser.error(f"{args.inputs} is inside a git work tree; downloads stay outside git")
    knessets = parse_knessets(args.knessets)
    formats = [fmt.strip().upper() for fmt in args.formats.split(",") if fmt.strip()]
    args.inputs.mkdir(parents=True, exist_ok=True)
    client = PoliteClient(min_interval=args.min_interval, log_path=args.log or args.inputs / "fetch_log.jsonl")

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    catalogue = fetch_catalogue(client, knessets, formats)
    print(f"{len(catalogue['bills'])} bills, {sum(len(b['documents']) for b in catalogue['bills'])} files", file=sys.stderr)
    counts = {"downloaded": 0, "reused": 0, "failed": 0}
    if not args.catalogue_only:
        counts = download(client, catalogue, args.inputs)
    document = manifest(catalogue, knessets=knessets, formats=formats, counts=counts, fetched_at=fetched_at)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(document["counts"], ensure_ascii=False), file=sys.stderr)
    if counts["failed"]:
        sys.exit(f"{counts['failed']} files failed; rerun to retry them")


if __name__ == "__main__":
    main()

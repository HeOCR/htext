"""Write a hash-only leakage fixture for protected evaluation text.

Usage (from the repository root):

    python scripts/leakage_hashes.py --repository HeOCR/hocrsyngen --commit <full sha> \
        --output data/leakage/<name>.hashes.json \
        LOCAL_FILE=REPO_PATH [LOCAL_FILE=REPO_PATH ...]

Each LOCAL_FILE is a copy of REPO_PATH read at the given commit (for example
from ``git show <sha>:<path>``). The fixture stores hashes only; see
``htext.leakage``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from htext.leakage import fixture_for_file


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("files", nargs="+", help="LOCAL_FILE=REPO_PATH")
    args = parser.parse_args()

    fixtures = []
    for item in args.files:
        local, _, repo_path = item.partition("=")
        if not repo_path:
            raise SystemExit(f"expected LOCAL_FILE=REPO_PATH, got {item!r}")
        fixtures.append(fixture_for_file(Path(local), repository=args.repository, source_path=repo_path, commit=args.commit))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"fixtures": fixtures}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

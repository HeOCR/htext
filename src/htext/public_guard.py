"""Fail closed before anything is staged for a public target (HF, Zenodo, this repository).

Evaluation custody material must never be published: exclusion lists, reservation
files, rosters, hold-out or DEV/test id lists, or the ids of dropped rows. Public text
gives counts and generic reasons only.

Checks, per staged file:

1. **Name.** Both the local path and the public target path are checked against
   :data:`FORBIDDEN_NAME`.
2. **JSON keys.** A key at any depth of a ``.json`` or ``.jsonl`` file that holds a
   non-empty list and is in :data:`FORBIDDEN_KEYS` (the field names of the private
   lists) is refused. String and dict values are references (a file name, a sha pin)
   and pass.
3. **Private tokens.** If ``HTEXT_PRIVATE_EXCLUSIONS`` names a private exclusion
   file (one or more paths, separated by ``os.pathsep``), every identifier in it is
   searched for in text-like staged files. Its ``note`` and ``rules`` fields are
   skipped, and so are identifiers shorter than 5 characters. Pass ``allow_tokens``
   for identifiers that are legitimately public, such as a part's own published
   source scans.

Usage in a release script::

    from htext.public_guard import assert_public_safe
    assert_public_safe(staged.values(), targets=staged.keys())

Or from the command line, where the exit status is 1 on any finding::

    python -m htext.public_guard FILE [FILE ...]
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable

FORBIDDEN_NAME = re.compile(
    r"exclusion|reservation|roster|custody|denylist|deny_list|hold[-_]?out|dev[-_]?panel|test[-_]?ids|eval[-_]?refs|drop[-_]?ids|row[-_]?ids|dropped[-_]?rows",
    re.I,
)
FORBIDDEN_KEYS = frozenset({
    "release_row_ids", "phist_dev_panel_books", "c2_sources", "ia_ids", "pby_ids", "author_rules",
    "exclusions", "reservations", "reserved_ids", "roster", "heldout_ids", "holdout_ids", "test_ids",
    "dev_ids", "dev_panel",
})
TEXT_SUFFIXES = frozenset({".json", ".jsonl", ".md", ".txt", ".csv", ".tsv", ".py", ".yaml", ".yml", ".html"})
SKIP_TOKEN_FIELDS = frozenset({"note", "rules"})
MIN_TOKEN = 5
ENV = "HTEXT_PRIVATE_EXCLUSIONS"


class PublicStagingError(RuntimeError):
    """Raised when a staged public file carries evaluation custody material."""


def _strings(o, skip=SKIP_TOKEN_FIELDS):
    if isinstance(o, dict):
        for k, v in o.items():
            if k not in skip:
                yield from _strings(v, skip)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v, skip)
    elif isinstance(o, (str, int)) and not isinstance(o, bool):
        yield str(o)


def private_tokens(paths: Iterable[str | os.PathLike] | None = None) -> set[str]:
    """Identifiers from the private exclusion file(s). Default: those named by ``$HTEXT_PRIVATE_EXCLUSIONS``."""
    if paths is None:
        paths = [p for p in os.environ.get(ENV, "").split(os.pathsep) if p]
    out: set[str] = set()
    for p in paths:
        for s in _strings(json.loads(Path(p).read_text(encoding="utf-8"))):
            # composite "part|row id" entries: the row id alone is the identifier
            for t in (s, s.rsplit("|", 1)[-1]):
                if len(t) >= MIN_TOKEN:
                    out.add(t)
    return out


def _keys(o):
    """Keys whose value is a list: an id list. A string or dict value is a reference (a file name, a sha pin)."""
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, list) and v:
                yield k
            yield from _keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from _keys(v)


def _json_objects(path: Path, text: str):
    if path.suffix == ".jsonl":
        for line in text.splitlines():
            if line.strip():
                yield json.loads(line)
    else:
        yield json.loads(text)


def check_public_files(
    paths: Iterable[str | os.PathLike],
    targets: Iterable[str] | None = None,
    tokens: set[str] | None = None,
    allow_tokens: Iterable[str] = (),
) -> list[str]:
    """Return one finding per problem. Findings name the file and the kind of hit, never the matched identifier."""
    paths = [Path(p) for p in paths]
    targets = list(targets) if targets is not None else [str(p) for p in paths]
    if len(targets) != len(paths):
        raise ValueError("targets must match paths one to one")
    toks = (private_tokens() if tokens is None else set(tokens)) - set(allow_tokens)
    findings: list[str] = []
    for path, target in zip(paths, targets):
        for label, name in (("local name", str(path)), ("target name", str(target))):
            if FORBIDDEN_NAME.search(name):
                findings.append(f"{target}: {label} looks like custody material")
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix in (".json", ".jsonl"):
            try:
                bad = {k for o in _json_objects(path, text) for k in _keys(o) if k in FORBIDDEN_KEYS}
            except json.JSONDecodeError:
                bad = set()
                findings.append(f"{target}: unparseable JSON, cannot verify")
            if bad:
                findings.append(f"{target}: private-list keys present ({len(bad)})")
        if toks:
            n = sum(1 for t in toks if t in text)
            if n:
                findings.append(f"{target}: {n} private identifier(s) present")
    return findings


def assert_public_safe(paths, targets=None, tokens=None, allow_tokens=()) -> None:
    """Raise :class:`PublicStagingError` if any staged file fails :func:`check_public_files`."""
    paths = list(paths)
    findings = check_public_files(paths, targets=targets, tokens=tokens, allow_tokens=allow_tokens)
    if findings:
        raise PublicStagingError("refusing to publish:\n  " + "\n  ".join(findings))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    findings = check_public_files(argv)
    for f in findings:
        print(f, file=sys.stderr)
    print(f"{len(argv)} file(s) checked, {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

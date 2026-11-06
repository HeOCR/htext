# Agent notes for htext

- Read `README.md` first. The PBY corpus follows the `hocrsyngen` plan
  `docs/pby_public_domain_text_intake_plan.md` (`S15a`) and ADR 0007.
- Never commit a source dump or any file a corpus card does not list. If a
  build output is large, report its size before committing it; large outputs
  go to release assets or Git LFS.
- Tests are offline. Do not add a test that needs the network or a local dump.
- Code is MIT (`LICENSE`); data and build outputs are CC0-1.0 (`LICENSE-DATA`).
  Keep that split when adding files.
- Work on a feature branch, open a PR, and squash-merge. Commits use
  conventional `type(scope): subject` messages.

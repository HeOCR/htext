#!/bin/bash
# Sefaria v3 release build: fit check (hocrsyngen 88c61af), dedup against released htext lines, all three lanes,
# incremental shards (rerun resumes). Code: htext main @ the htext-sefaria-v3 worktree (detached origin/main).
set -euo pipefail
W=/Users/shaypalachy/agents/environments/opensource/projects/heocr/agent_worktrees/htext-sefaria-v3
V=/Users/shaypalachy/agents/environments/opensource/projects/heocr/tasks/heocr-data/venvs/fit
D=~/temp/heocr/downloads
DD=$D/htext-sefaria/dedup
DISK_FLOOR_BYTES=10000000000
LANE_WRITE_AND_HEADROOM_BYTES=6000000000
cd "$W"
for lane in cc0 by by-sa; do
  df -h /
  df -Pk "$D" | awk -v lane="$lane" -v floor="$DISK_FLOOR_BYTES" -v headroom="$LANE_WRITE_AND_HEADROOM_BYTES" '
    END {
      available = $4 * 1024
      if (available <= floor + headroom) {
        printf "LOW DISK before %s: %.0f B free, need above %.0f B after allowing for the build\n", lane, available, floor + headroom
        exit 1
      }
    }'
  DYLD_LIBRARY_PATH=/opt/homebrew/lib /usr/bin/time -l "$V/bin/htext" sefaria build --sources data/sefaria/v3/sources.v3.json \
    --inputs "$D/htext-sefaria/v3/export" --output "$D/htext-sefaria/v3/release-$lane" --lane "$lane" \
    --reserved "$D/htext-gutenberg/eval_reservations_v13.json" --length-profile "$D/htext-gutenberg/hebrew_lines_train_v1.txt" \
    --hocrsyngen-commit 88c61af --jobs 6 $(for f in "$DD"/*.txt; do printf -- "--dedup-against %s " "$f"; done)
done
echo RELEASE_BUILD_DONE

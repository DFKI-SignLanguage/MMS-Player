#!/usr/bin/env bash
#
# Updates the animated GIFs in Docs/Videos with the more recent versions
# generated in MMS-examples.
#
# Only GIFs already present in Docs/Videos are updated (no new files are added).
# If a GIF was not generated in MMS-examples, the old version in Docs/Videos is kept.
#
# Usage: ./update_docs_gifs.sh [-n]   (-n = dry run)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/MMS-examples"
DST_DIR="$SCRIPT_DIR/Docs/Videos"

DRY_RUN=()
if [[ "${1:-}" == "-n" ]]; then
    DRY_RUN=(--dry-run)
fi

# --existing : only update files that already exist in the destination
# --update   : skip files that are newer in the destination
rsync -av "${DRY_RUN[@]+"${DRY_RUN[@]}"}" --existing --update \
    --include='*.gif' --exclude='*' \
    "$SRC_DIR/" "$DST_DIR/"

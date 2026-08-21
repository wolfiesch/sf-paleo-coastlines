#!/bin/sh
# Restore public/data/paleo-coastlines from the Contabo storage VPS.
#
# The dataset is intentionally NOT stored in git or GitHub LFS anymore
# (it outgrew both). This script materializes the local copy that the
# vite app serves from public/.
#
# Usage: scripts/sync-data-from-storage.sh
set -eu

HOST="${SF_PALEO_STORAGE_HOST:-contabo-storage}"
REMOTE_PATH="${SF_PALEO_STORAGE_PATH:-/srv/data/sf-paleo-coastlines/paleo-coastlines}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$REPO_ROOT/public/data/paleo-coastlines"

echo "Syncing $HOST:$REMOTE_PATH -> $DEST"
mkdir -p "$DEST"
exec rsync -a -e ssh "$HOST:$REMOTE_PATH/" "$DEST/"

#!/bin/bash
# Link (or copy) the addon into a WoW install so edits show up after /reload.
# Usage: ./scripts/link-addon.sh _anniversary_ [--copy]
set -euo pipefail

FLAVOR="${1:-_anniversary_}"
MODE="${2:-}"
WOW="${WOW_DIR:-/Applications/World of Warcraft}"
SRC="$(cd "$(dirname "$0")/.." && pwd)/addon/NickHubTracker"
DEST_DIR="$WOW/$FLAVOR/Interface/AddOns"
DEST="$DEST_DIR/NickHubTracker"

if [ ! -d "$WOW/$FLAVOR" ]; then
  echo "Can't find $WOW/$FLAVOR"
  echo "Folders in $WOW:"; ls "$WOW" 2>/dev/null | grep '^_' || echo "  (none — is WoW installed somewhere else? set WOW_DIR)"
  exit 1
fi

mkdir -p "$DEST_DIR"
if [ -e "$DEST" ] || [ -L "$DEST" ]; then
  echo "Replacing existing $DEST"
  rm -rf "$DEST"
fi

if [ "$MODE" = "--copy" ]; then
  cp -R "$SRC" "$DEST"
  echo "Copied addon to $DEST (re-run after each change)"
else
  ln -s "$SRC" "$DEST"
  echo "Linked $DEST -> $SRC"
  echo "Edits in VS Code are live after /reload in game."
fi

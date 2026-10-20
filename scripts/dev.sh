#!/bin/sh
# Run the app from source with a throw-away data dir (./data, git-ignored) so the
# real log in ~/Library/Application Support is never touched while developing.
#   scripts/dev.sh            # start the app
#   scripts/dev.sh --debug    # also open the WebKit inspector
cd "$(dirname "$0")/.." || exit 1
[ -x .venv/bin/python3 ] || { python3 -m venv .venv && .venv/bin/pip install -r requirements.txt; } || exit 1
export POTA_HELPER_DATA="$PWD/data"
[ "$1" = "--debug" ] && export POTA_HELPER_DEBUG=1
exec .venv/bin/python3 app.py

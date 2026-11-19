#!/usr/bin/env bash
set -euo pipefail

# Run the `sweep`-marked pytest suite inside a throwaway python:3.15-slim
# container on the mainframe, against a checkout pinned to a fixed commit.
#
# The single canonical sweep entry point:
#   scripts/sweep-mainframe.sh <40-hex-sha> [--collect-only]
#
# Exit codes:
#   2  usage / SHA-format error (no SSH attempted)
#   3  mainframe checkout HEAD does not match the pinned SHA (before Docker)
#   4  mainframe checkout is dirty (before Docker)
#   *  anything else passes through: ssh -> remote sh -> docker run -> pytest

usage() {
    printf 'usage: %s <40-hex-sha> [--collect-only]\n' "$0" >&2
}

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    usage
    exit 2
fi

sha_raw="$1"
mode="full"

if [ "$#" -eq 2 ]; then
    if [ "$2" != "--collect-only" ]; then
        usage
        exit 2
    fi
    mode="collect"
fi

if ! printf '%s' "$sha_raw" | grep -Eq '^[0-9a-fA-F]{40}$'; then
    usage
    exit 2
fi
sha="$(printf '%s' "$sha_raw" | tr '[:upper:]' '[:lower:]')"

exec ssh -o BatchMode=yes mainframe sh -s -- "$sha" "$mode" <<'REMOTE'
sha="$1"
mode="$2"
checkout=/home/kbdejavu/servers/indiegenerator

actual="$(git -C "$checkout" rev-parse HEAD)"
if [ "$actual" != "$sha" ]; then
    printf 'expected HEAD %s, checkout is at %s\n' "$sha" "$actual" >&2
    exit 3
fi

if [ -n "$(git -C "$checkout" status --porcelain)" ]; then
    printf 'checkout is dirty; refusing to sweep a tree that is not the pinned tree\n' >&2
    exit 4
fi

case "$mode" in
    collect) suffix=' --collect-only' ;;
    *)       suffix='' ;;
esac

docker run --rm \
    -v /home/kbdejavu/servers/indiegenerator:/work:ro \
    python:3.15-slim \
    sh -c "mkdir -p /scratch && cp -a /work/. /scratch/ && pip install -e '/scratch[dev]' && cd /scratch && pytest -q -m sweep${suffix}"
REMOTE

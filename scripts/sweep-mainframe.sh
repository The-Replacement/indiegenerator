#!/usr/bin/env bash
set -euo pipefail

# Run the `sweep`-marked pytest suite inside a throwaway python:3.15-slim
# container on the mainframe, against a checkout pinned to a fixed commit.
#
# The single canonical sweep entry point:
#   scripts/sweep-mainframe.sh <40-hex-sha> [--collect-only]
#
# Exit codes:
#   2  usage / SHA-format error / bad SWEEP_TIMEOUT (no SSH attempted)
#   3  mainframe checkout HEAD does not match the pinned SHA (before Docker)
#   4  mainframe checkout is dirty (before Docker)
#  124 the sweep exceeded SWEEP_TIMEOUT (default 3600s) and was stopped
#   *  anything else passes through: ssh -> remote sh -> docker run -> pytest
#
# SWEEP_TIMEOUT: seconds the whole container run may take. A hung pytest used
# to hold the SSH session open forever; the default is an hour because a full
# 85-test sweep measured 21 minutes on this box.

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

timeout_s="${SWEEP_TIMEOUT:-3600}"
if ! printf '%s' "$timeout_s" | grep -Eq '^[0-9]+$'; then
    printf 'SWEEP_TIMEOUT must be whole seconds, got %s\n' "$timeout_s" >&2
    exit 2
fi

exec ssh -o BatchMode=yes mainframe sh -s -- "$sha" "$mode" "$timeout_s" <<'REMOTE'
sha="$1"
mode="$2"
timeout_s="$3"
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

# Copy the tree with two exclusions instead of `cp -a` of everything.
# render history would turn one sweep into a multi-gigabyte copy, and `.git` is
# dead weight for pytest. `git archive` is not an option: python:3.15-slim
# ships no git. tar, however, is in the image, and its --exclude prunes whole
# subtrees, so the blocklist stays cheap. An allowlist would be stricter and
# more dangerous: a path missing from it breaks the sweep silently.
timeout -k 30 "$timeout_s" docker run --rm \
    -v /home/kbdejavu/servers/indiegenerator:/work:ro \
    python:3.15-slim \
    sh -c "mkdir -p /scratch && tar -C /work --exclude=./data --exclude=./.git -cf - . | tar -xf - -C /scratch && pip install -e '/scratch[dev]' && cd /scratch && pytest -q -m sweep${suffix}"
REMOTE

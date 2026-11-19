#!/usr/bin/env sh
# Run the bounded seed sweep in a container.
#
# For hosts without a Python 3.15 venv (mainframe's host is 3.14.8) and to keep
# a multi-minute CPU pin off the laptop. The sweep renders in memory and never
# touches data/indiegen/state.json, so it cannot fork the serve cursor.
#
#   ./scripts/sweep.sh                 # pytest -q -m sweep
#   ./scripts/sweep.sh --collect-only  # appended: -q -m sweep --collect-only
#   ./scripts/sweep.sh -k motorik      # appended: -q -m sweep -k motorik
#
# Builds the `sweep` target from this checkout into `indiegen-sweep` and runs it
# in a throwaway --rm container. Nothing runs against the production
# `radio-indiegen` container; no volumes are mounted.
set -eu
cd "$(dirname "$0")/.."

image="${INDIEGEN_SWEEP_IMAGE:-indiegen-sweep}"
docker build --target sweep -t "$image" .
exec docker run --rm "$image" -q -m sweep "$@"

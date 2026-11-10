#!/bin/sh
# One generation cycle for the radio: render, replace the library, restart
# Liquidsoap. Intended to run inside the indiegenerator container or on a host
# with indiegen installed. All knobs come from the environment so a git hook
# or `docker compose exec` can trigger it without arguments.
set -eu

exec indiegen cycle \
  --music-dir "${INDIEGEN_MUSIC_DIR:-/music}" \
  --work-dir "${INDIEGEN_WORK_DIR:-/var/lib/indiegen}" \
  --presets-dir "${INDIEGEN_PRESETS_DIR:-/app/presets}" \
  --preset "${INDIEGEN_PRESET:-station}" \
  --count "${INDIEGEN_COUNT:-10}" \
  --seed-base "${INDIEGEN_SEED_BASE:-1000}" \
  --seed-strategy "${INDIEGEN_SEED_STRATEGY:-advance}" \
  --cycle-index "${INDIEGEN_CYCLE_INDEX:-0}" \
  --restart "${INDIEGEN_RESTART:-docker:radio-liquidsoap}"

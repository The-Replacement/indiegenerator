# Handoff — c56-mainframe-sweep

## What changed

The `sweep`-marked suite no longer defaults to the laptop. It runs in a
throwaway `python:3.15-slim` container on the mainframe, against a checkout
pinned to a fixed commit, via one committed script:

```bash
scripts/sweep-mainframe.sh <40-hex-sha> [--collect-only]
```

```bash
scripts/sweep-mainframe.sh <40-hex-sha> --collect-only
```

The laptop path `.venv/bin/pytest -q -m sweep` still works but is no longer
the documented default. The CI `sweep` job (`.github/workflows/gate.yml:65-90`,
45-minute timeout) is retained as an independent second gate.

The script validates and normalizes the SHA locally (exit 2 on bad input, no
SSH attempted), then over SSH asserts the mainframe checkout HEAD equals the
pinned SHA (exit 3 on mismatch) and that the tree is clean (exit 4), before
one `docker run --rm` of `python:3.15-slim` with a single read-only mount of
the checkout at `/work:ro`, copying it to a writable `/scratch`, installing
the `[dev]` extra from pypi, and running `pytest -q -m sweep`.

The sole authoritative `state.json` is `/home/kbdejavu/servers/radio/data/indiegen/state.json` on the mainframe, bind-mounted into `radio-indiegen` at `/var/lib/indiegen`; that host path is its only owner. Sweeps never touch it — they pass no `--work-dir` and call neither `load_state` nor `save_state` — so moving sweep compute to the mainframe forks no cursor. Never run sweep with `--work-dir /var/lib/indiegen`.

## Why

Issue #56. The laptop pays ~69 minutes single-process for the 85-cell sweep.
The mainframe has the headroom and the checkout; the throwaway container
supplies the `>=3.15,<3.16` interpreter the host (3.14.8) cannot. Moving the
compute must never move the cursor: sweeps are recomputable from
(preset, seed, commit), and only `state.json` is non-derivable.

## Falsifier

(1) zero-render smoke on mainframe reports exactly 85 collected; (2) full run at pinned SHA yields 85 passed with same gate verdicts as laptop same commit; (3) state.json sha256 + stat byte-identical before/after; (4) both checkouts stay clean; (5) no push, no rotation, no restart, radio-indiegen image ID and mounts unchanged.

The change is VERIFIED only if all five hold; otherwise it is withheld and
the failing item root-caused.

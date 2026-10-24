# Handoff — c28-seed-sweep-gate-coverage

## What changed

A bounded seed sweep now lives in the suite. `tests/test_sweep.py` renders
five lanes at seeds {1042, 2000, 4002}, 240 s each, and runs gates 4, 5, 6,
7 and 13 — the gates that judge the arrangement against itself — on the
pre-master mix and the int16 pcm, exactly as `run_gates` does.

It is marked `sweep` and runs as its own CI job:
`.github/workflows/gate.yml`'s gate job now runs `pytest -q -m "not sweep"`,
and a new `sweep` job runs `pytest -q -m sweep`.

## Why

c27 was found by a hand-run sweep, not by the suite. The suite pins one seed
per lane, so a gate failure that depends on the drawn arrangement is invisible
until a human watches a batch die. 87 of 200 ambient seeds draw the two-section
form that failed; the sweep is the detector that would have said so.

## Result

The full sweep is green: **15 passed in 468 s (7:48)**. No latent failure
beyond c27 surfaced at these seeds and lanes. The instrumentation is the
deliverable; a green sweep is a statement about these fifteen points, not
about the whole seed space.

## Where it lives

- `tests/test_sweep.py` — the sweep; seeds chosen (1042 the golden, 2000 the
  c27 failure, 4002 a third arrangement), never random.
- `pyproject.toml` — the `sweep` marker.
- `.github/workflows/gate.yml` — the gate job deselects `sweep`; the `sweep`
  job is its own run with a 30-minute timeout.

## Verification

- `ruff check .` / `ruff format --check .` clean, `mypy src` clean.
- `pytest -q -m "not sweep"`: 508 passed, 15 deselected.
- `pytest -q -m sweep`: 15 passed.
- No production code changed; no golden moved.

## Limits / next

- Three seeds is a probe, not a proof. Widening the seed list is the obvious
  lever if a future failure slips through; the cost is linear in renders.
- The sweep runs gates 4-7 and 13 only. Gates 1-3 and 8-12 are the master and
  codec gates, covered by the default run and by ffmpeg in the gate job.
- The gate job and the sweep job both render; on a contended CI runner the
  sweep may approach its timeout. The 30-minute ceiling on a 7:48 local run
  has room but is worth watching.

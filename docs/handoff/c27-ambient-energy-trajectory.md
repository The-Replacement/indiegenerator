# Handoff — c27-ambient-energy-trajectory

## What changed

Gate 5 no longer fails a static plan for being static.

The station's section graph lets the ambient walk take `intro → outro` when
it draws a two-node path. Those two nodes are 200 millibels apart, so the
plan's whole level curve spans 0.2 dB. Gate 5 correlated the delivered
per-second RMS against that curve; inside a 240 s sparse ambient section the
per-second RMS swings by far more than 0.2 dB (poly-period on-windows, long
pad attacks), so the Pearson was noise and the verdict a coin flip. Seven of
the ten rendered two-section seeds failed.

`validate.energy_correlation` now returns 1.0 when the planned section levels
span `STATIC_LEVEL_SPREAD_MILLIBELS` (300, i.e. 0.3 dB) or less — the same
protection gate 6 already gives a static timbre, and the same sentence BRIEF
§11 writes for gate 5. A curve that actually moves is correlated as before.

## Where it lives

- `src/indiegen/validate.py`: `STATIC_LEVEL_SPREAD_MILLIBELS = 300` and the
  spread guard in `energy_correlation`. `filecheck._check_gate_5_recorded`
  reads the stored correlation, so the recorded path needed no change.
- `tests/test_c27.py`: 7 tests — both failing seeds, the exact boundary
  (300 passes, 301 does not), a moving plan still correlating, a normal
  three-section ambient not exempt, duration independence, the directed plan.
- `README.md`: the gate-5 bullet now says "less than 0.3 dB".

## Verification

- `ruff check .` / `ruff format --check .` clean, `mypy src` clean.
- `pytest -m "not slow"`: 505 passed, 3 deselected.
- `pytest -m slow`: 3 passed.
- End to end: `indiegen render --preset ambient --seed 2000 --seconds 480`
  and `--seed 3005` now exit 0 and write their files (they exited 2 before).

## Blast radius / limits

- No audio changed: no plan field, no render path. Goldens moved only in the
  README text; the PCM/plan hashes are unchanged.
- The exemption is a blanket at 0.3 dB. A plan with a real but sub-0.3 dB
  curve is now always a pass — but 0.3 dB is inaudible as a shape.
- BRIEF §11's literal metric ("per-second RMS") is untouched; only the
  already-implied static case is handled, as gate 6 does.

## Deferred (the "C" the user chose to do later)

The music itself: a sixteen-minute `intro → outro` ambient with 0.2 dB of
shape is a boring form. A separate creative change should give the short
ambient a real arc — either a stronger `outro` contrast in the shared
station graph or a floor of three sections for the ambient — without relying
on the gate exemption to carry it. Tracked as the deferred half of c27.

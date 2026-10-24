# Handoff — c26-microtiming-groove

## What changed

The non-drum material now has a groove. Two per-lane integer knobs, applied
at compose time so the Plan still says exactly what plays when:

- `swing_permille` (0..1000): an onset that lands on an **odd beat** moves
  later by `frames_per_beat * swing_permille // 6000` frames. At 1000 that is
  a sixth of a beat — the triplet feel. A lane with `pulse: seconds` makes it
  a strict no-op.
- `melodic_jitter_frames` (0..200): each pluck (the deja-vu stabs, the KS
  chorus, the motif) drifts on a compose-side low-frequency stream in
  `[-depth, +depth]`. A detuned chorus pair is one gesture, so both voices
  drift together.

Swing lands on `PluckEvent.start_frame` and on every `RhythmEvent` hit on an
odd beat (kick, snare, hat, bass); jitter lands on plucks only. The motif's
recorded appearances move in lockstep with their plucks, or the Director
could not find them again.

## Where it lives

- `src/indiegen/plan.py`: `Plan.swing_permille`, `Plan.melodic_jitter_frames`.
- `src/indiegen/config.py`: the same two fields on `LanePreset`.
- `src/indiegen/compose/rng.py`: `groove_offsets(seed, count, depth)`, an
  integer one-pole over a dedicated SplitMix64 stream. The main compose RNG
  is never drawn from, so the draw order (and every plan that changes no
  event) is untouched.
- `src/indiegen/compose/planner.py`: `_apply_groove` / `_groove_event` /
  `_shift_hits`, called between `_planar_offset` and `_ornament_events` so
  grace relations and the L16 clone nulls stay exact.
- `presets/*.yaml`: motorik 600/40, kosmische 250/30, dub-electronic 500/25,
  indie-noise 300/45, ambient 0/30.

## Verification

- `ruff check .`, `ruff format --check .`, `mypy src` clean.
- `pytest -m "not slow"`: 498 passed, 3 deselected.
- `pytest -m slow`: 3 passed.
- Goldens re-derived in this change: `plan_motorik_1042.json` +
  `.sha256` (plan hash moved: new defaulted fields plus shifted onsets) and
  `pcm_ambient_1042.sha256` (ambient jitter 30). README quickstart block and
  the eight-minute table refreshed.

## Known limits / next

- Swing is on/off per beat; no per-subdivision swing (16th swing) yet.
- Jitter is compose-side and therefore shifts `MotifAppearance.start_frame`.
  Any future pass that rewrites plucks must do the same.
- Pre-master energy trajectory gates (5/6) were not measured across a seed
  sweep with swing on; the 60 s motorik and 90 s ambient renders pass, and
  the 8-minute lane table was re-measured. A seed sweep is the honest next
  step.
- The opening/body and closing/body tests in `test_artifact.py` used a
  window **peak**, which a single transient decides: 40 frames of motorik
  jitter could move a peak out of the body window and flip the assertion
  without the music changing. They now use window **RMS** (the same
  yardstick as gate 5's per-second energy), so the claim is about the
  energy trajectory and is stable from 0 to 200 frames of jitter
  (measured opening/body ≈ 0.53, closing/body ≈ 0.43). Motorik keeps the
  intended 40-frame jitter.

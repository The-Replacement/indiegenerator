# Handoff — c30-timbral-grit

## What changed

The instrument path now earns harmonic content, and the kit snaps.

- `synth/grit.py` (new): the waveshaper, `tanh(x * gain) / gain` with
  `gain = 1 + 6 * drive/1000`. At `drive_permille == 0` it returns the input
  object, so the default render cannot move.
- `EventBase.drive_permille` and `RhythmEvent.snap_permille` (0..1000, default
  0) on the Plan; `LanePreset` carries both.
- The shaper is applied in **`synth/ks.py` only**, after the loop filter and
  before the DC blocker: the string is shaped, its decay and tuning are not.
- The snap is a four millisecond noise burst added to the kick, snare and hat
  attacks, scaled by `snap_permille`.
- `_apply_timbre` stamps the lane's drive on the **plucked** voices and its
  snap on the `RhythmEvent` hits.
- Presets: motorik drive 300 / snap 400, kosmische drive 200 (no drums),
  dub-electronic 350 / 350, indie-noise 300 / 700, ambient drive 150.

## The design decision, and why

The shaper was first applied to **every** voice — pad, drone and poly-period
included. That broke BRIEF §6's loudness-range rule:

| motorik 480 s, seed 1042 | LRA |
|---|---|
| baseline, no grit | 10.76 LU |
| drive 300 on all voices, snap 0 | **16.48 LU** |
| drive 0, snap 400 | 10.76 LU |
| drive 300 on the plucks only | **10.78 LU** |

A tanh adds harmonics in proportion to level, so the *sustained* bed (the pad
and drone that define the loudness envelope) brightens most where it is
loudest, and the short-term range widens. The snap is innocent. The drive is
therefore stamped on the plucked/string voices only, and the pad, drone and
poly-period stay clean. The string is where the audit's "AI glaze" is most
audible, so this is the right half to ship first.

The additive pad still needs the shaper the audit asked for, but it needs a
**level-neutral** one (per-block RMS-matched, or a parallel dry/wet blend) or
the loudness envelope walks. That is the first task of the deferred timbre
work, recorded here rather than faked.

## Verification

- `ruff check .`, `ruff format --check .`, `mypy src` clean.
- `pytest -q -m "not sweep"`: 526 passed, 15 deselected.
- `pytest -m slow`: 4 passed (ambient golden, migration S0, plus c29).
- `pytest -q -m sweep`: the seed sweep, on the new presets.
- The S0 migration hash still passes: the frozen plan has no drive, so the
  identity default holds.
- Goldens re-derived in this change: `plan_motorik_1042` (`cabd718a…`),
  `pcm_ambient_1042` (`77510545…`), the README quickstart and the eight-minute
  table.

## The eight-minute table (seed 1042, one serial run)

| lane | time | LUFS | dBTP | LRA | plan_sha | pcm_sha |
|---|---|---|---|---|---|---|
| motorik | 88.7 s | −16.084 | −4.299 | 10.78 | 899bb792… | f1c8de79… |
| kosmische | 112.6 s | −16.051 | −4.299 | 10.06 | e6b4f52f… | 2423db5b… |
| dub-electronic | 119.5 s | −16.104 | −4.297 | 11.71 | 1d9f6d08… | 63016d07… |
| indie-noise | 94.2 s | −16.095 | −4.293 | 10.79 | 6bbb1d60… | aecfa8e9… |
| ambient | 134.9 s | −16.095 | −4.299 | 11.44 | dc02de9e… | 4a586f55… |

Every LRA is back inside BRIEF §6's 4–12. The render is ~12–15% slower than
before c30 on the same host (the extra `tanh` per block); the budget is 180 s
for eight minutes.

## Two pre-existing defects found while landing this (not c30's)

1. **`validate` fails gate 12 (codec) for indie-noise.** Cold (drive 0) it
   measures 0.905 LU against the 0.5 limit; warm it is 0.978. c30 widens the
   delta by ~0.07 LU but does not create the failure. motorik, dub and ambient
   validate ok. This is the codec-awareness item → the masking change.
2. **kosmische fails gate 6 at 60 s** (−0.10 cold, −0.013 warm; passes at
   240 s). The station's interlude form is 45–120 s, so a legal short
   kosmische track is refused → a short-form trajectory change.

## Limits / next

- Sustained-bed grit (pad/drone/poly) is deferred: it needs a level-neutral
  shaper so it does not move the loudness range.
- No oversampling: the drive is bounded and the added high-frequency energy is
  judged by the codec gate, which indie-noise already fails for its own
  reasons. Oversampling and a >12 kHz shelf belong with the masking change.
- The masking change (the 200–500 Hz bass-keyed duck and the codec shelf) and
  the short-form trajectory fix are next.

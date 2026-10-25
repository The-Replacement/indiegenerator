# Handoff — c33: the drum's micro-timing moves into the Plan

## What changed

The drift that used to be applied while the track was cut into blocks is now
decided when the Plan is frozen.

- `indiegen/control.py` (new): the 1/f control-rate stream moved out of
  `synth/noise.py` verbatim — `CONTROL_RATE`, `HISTORY`, `SOURCE_COUNT`, the
  band constants, the stream ids (`VELOCITY`/`PAN`/`TIMING`,
  `DETUNE`/`AMPLITUDE`), `PinkState`, `pink_state`, `stream_key`,
  `uniform_stream`, `pink_stream_block`, `pink_stream`, `control_slice`,
  `control_count`. `pink_stream_block` now allocates its own zeros instead of
  importing `synth.osc.zero_block`, so the module imports no synth code.
- `synth/noise.py` keeps `interpolate_block` / `interpolate_to` and imports
  `CONTROL_RATE` from `control`. Every importer was repointed:
  `synth/drums.py`, `synth/drone.py`, `synth/ks.py`, `fx/dub.py`, and the
  three tests.
- `compose/microtiming.py` (new): `apply_micro_timing` reads the whole timing
  stream once per pattern and writes each hit's played frame.
- `plan.py`: `HitBase.drift_frames` (default 0) and `HitBase.grid_frame()`.
  `frame` keeps its meaning — where the hit plays.
- `synth/drums.py`: `DrumState` loses the timing stream; the renderer no
  longer computes an offset and no longer refuses a hit whose offset leaves
  the block; the four noise reads and `_snap` key on `grid_frame()`.
- `render.py`: `kick_hits` and `bass_hits` are built from `grid_frame()`.
- `compose/planner.py`: `apply_micro_timing(events, frames, SAMPLE_RATE)` runs
  **last** in `compose()`, after `_build_fx_deck_and_replay`.
- `compose/director.py`: the Director's hit windows read `grid_frame()`.

## The rule that came out of it

**The drift is the performance; every decision asks the grid.** Three readers
had to be taught this, and each one was found by measurement, not by reading:

| reader | what it asked | what it must ask |
|---|---|---|
| the voice's noise key (`synth/drums.py`, 4 sites + `_snap`) | `hit.frame` | `grid_frame()` |
| the bus keyframes (`render.py`: c31's duck, T10's kick sidechain) | `hit.frame` | `grid_frame()` |
| the Director's hit windows and reharmonization (`director.py:152,167,238`) | `hit.frame` | `grid_frame()` |
| c32's section-density test | `hit.frame` | `grid_frame()` |

The Director one is the one that would have shipped a bug. With the drift
applied inside `compose()` and the Director still windowing on `hit.frame`,
motorik at 480 s changed **arrangement**: the deck kept 761 kicks where it
used to keep 759, because two hits drifted across a window edge. It showed up
only as a 480 s render hash mismatch against the pre-change tree — 20 s and
90 s were bit-identical, which is exactly why the table's duration is not a
detail to skip. Applying the drift in `director()` instead would also have
"worked", but it would leave a plan from `compose()` alone without its
groove; the drift is part of the plan, so the readers move instead.

## The defect

`docs/next-session.md` carried a c31 finding — "a drum voice longer than
`RENDER_BLOCK` loses its tail past the second block" — as the top item. That
one was already fixed, by `4ed10b5`, which made `_mix_pending` re-carry. It
was measured clean here at 131072 / 65536 / 16384 / 8191 / 4099 / 1024 on all
four lanes. What c31 never found is the defect next to it.

Scanning `RENDER_BLOCK` over 4000..4199 on motorik (20 s, seed 1042), **10 of
200 sizes differed**, each first difference one frame before a hit whose
frame was an exact multiple of the block size (219240 = 4060 × 54):

| size | first differing frame |
|---|---|
| 4011 | 360990 |
| 4043 | 857116 |
| 4050 | 566999 |
| 4060 | 219239 |
| 4080 | 257039 |
| 4095 | 663389 |
| 4130 | 446039 |
| 4140 | 521639 |
| 4158 | 332640 |
| 4185 | 732374 |

The render-time offset pushed the hit out of its own block, and both
neighbours refused it: the block that had gone by had broken at
`hit.frame >= stop` before reaching it, and the block that held it saw
`frame < start` or `frame >= stop`.

Pre-declared falsifier: rebuild the same plan with `micro_timing_frames = 0`.
Declared 12 → 10 of 10 sizes differ; 0 → **0 of 10**. Mechanism confirmed.

It was latent, not live: counting `_drum_voice` calls against the plan,
motorik played 170/170 and dub-electronic 126/126 at 131072, 65536, 16384,
8192 and 4099, and motorik played 169/170 at 4060. It bites when a hit's
unjittered frame lands within `micro_timing_frames` (9–14 on four lanes) of a
block boundary.

## Why the fix is not in the renderer

Bit-identity across block sizes needs the hit's frame to be independent of the
block. An offset applied at render time is not: clamping is
boundary-dependent, and a hit that drifts backwards would have to write into
audio already written. So the drift has to be decided before the render, in
the Plan — where BRIEF's "audio is a pure function of the Plan" puts it, and
where c26 already put the swing and the pluck jitter.

## Two decisions forced by measurement

**The voice's noise must not follow the drift.** The first implementation
moved only `frame`. The voices key their noise on `hit.frame`
(`uniform_stream(noise_seed, hit.frame, ...)`), so every moved hit re-drew
its whole voice: motorik differed on 415506 of 882000 frames, max 3.4e-1.
`drift_frames` plus `grid_frame()` restored bit-identity — 0 differing
frames. The distinction is real: a drummer's drift is timing, not a
different drum.

**The bus keyframes stay on the grid.** The c31 duck and the T10 kick
sidechain read hit frames in `render.py`. Keying them on the played frame
moved the duck by up to 12 frames and changed motorik's mix by 9.4e-2 in the
200–500 Hz band. Re-keying the duck is an audible change and belongs in its
own change with its own gates, so `render.py` reads `grid_frame()` and the
audio does not move.

## Verification

| check | result |
|---|---|
| block invariance, 200 sizes 4000..4199, motorik 20 s | **0 differ** (was 10) |
| block invariance, six round sizes, four lanes | identical to 131072 |
| hits played vs planned (motorik / dub, 6 sizes) | 170/170, 126/126 at every size incl. 4060 |
| pre-master mix vs the pre-change tree, 20 s | **0 differing frames** on motorik, dub-electronic, indie-noise |
| pre-master mix vs the pre-change tree, 90 s | identical (motorik `b5da7a03`, dub `093564a6`) |
| pre-master mix vs the pre-change tree, 480 s | identical (motorik `7001c989`, dub `b7a520f3`, indie-noise `c3ad866d`) |
| CLI render 60 s motorik | `plan_sha256 afab3b54`, `validate` ok |
| S0 frozen plan (`tests/golden/plan_station_1042_s0`) | untouched — the plan is pad-only |
| ambient PCM golden | untouched — the lane has no drums |
| `plan_motorik_1042` golden | re-derived (`afab3b54`), because hit frames and `drift_frames` are plan bytes |
| ruff check / format / mypy src | clean (60 files) |
| `pytest -m "not sweep and not slow"` | 650 passed, 20 deselected |
| `pytest -m sweep` / `-m slow` | 15 / 5 passed |

The drift is a representation move, not a re-draw of the kit, so no gate
verdict can have changed: the pre-master mix at the production block size is
byte-identical. That was the point of reading the same stream the renderer
read.

## Tests

- `tests/test_c33.py` (6): the drift is frozen and bounded; the hits stay
  strictly increasing; the grid is preserved against a `micro_timing_frames=0`
  control; the drift is reproducible per seed and moves on a new seed; zero
  depth is a strict no-op; the noise is keyed on the grid, not the played
  frame.
- `tests/test_blockwise.py`: `test_a_drum_hit_at_a_block_boundary_is_not_lost`
  pins `RENDER_BLOCK` 4060 — the size that swallowed the snare at 219240 —
  and `test_every_drum_hit_is_played_once_whatever_the_block_size` counts
  `_drum_voice` calls at 131072 / 8191 / 4099 / 4060. The old test's 65536
  could never have caught either defect.
- `tests/test_c32.py`: the section-density gate asks `hit.grid_frame()`. It
  is a question about the section a hit was **scheduled** into; the drift can
  pull a hit up to 12 frames across a section line and always could — before
  c33 the plan simply hid it, because the renderer added the offset after the
  gate had looked. Asking the grid frame keeps the assertion strict instead
  of widening it into a tolerance.

## Known, recorded, not fixed

- The duck is still keyed on the **grid** frame, so it leads the bass by up
  to `micro_timing_frames` (0.3 ms). Preserved deliberately. A change that
  re-keys it on the played frame is audible (9.4e-2 where it engages) and
  needs its own measurement across the band and the longform.
- `RENDER_BLOCK` is now safe to lower for memory. Nobody has lowered it.

## The table row, re-derived (480 s, seed 1042, CLI)

The measured table in `docs/next-session.md` was already stale before this
change — `4ed10b5` moved the harmony — so it was re-derived here on the final
tree:

| lane | wall | loudness | true peak | LRA | pcm_sha256 |
|---|---|---|---|---|---|
| motorik | 118.8 s | -16.071 LUFS | -4.299 dBTP | 9.221 LU | 7a5b7afb… |
| kosmische | 148.9 s | -16.058 LUFS | -4.298 dBTP | 10.553 LU | 499c6efb… |
| dub-electronic | 149.2 s | -16.059 LUFS | -4.298 dBTP | 12.297 LU | 445142e2… |
| indie-noise | 159.4 s | -16.092 LUFS | -4.279 dBTP | 9.436 LU | d7c75aa8… |
| ambient | 167.7 s | -16.008 LUFS | -4.300 dBTP | 11.282 LU | 1ca0885d… |

dub-electronic's 12.297 LU is above BRIEF 6's 12, and it is the documented
dub exception in the S4 declaration. Every other lane is inside 4–12.


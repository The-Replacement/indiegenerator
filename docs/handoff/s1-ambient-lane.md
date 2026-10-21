# Handoff — `s1-ambient-lane`

Slice S1 of the build order in `BRIEF.md` §15. Date: 2026-10-20.
Status: implemented, 257 tests green, ruff and mypy clean, one remediation cycle done, pending the SDD verify verdict.

## What was accomplished

- **The Plan is now a discriminated union of events** — `pad`, `poly_period`,
  `drone`, `pluck` — over a shared frozen base. Each technique carries only the
  parameters it uses; there are no dead fields and no invalid combinations.
- **T1 (poly-period loops)**: 3–9 voices with *distinct* periods in 15–90 s
  drawn without replacement, so the superpattern never repeats. The composer
  counts the **exact** sounding frames over the track's real length and
  asserts the 0.5–2 density band; the chord comes from the lane's scale with
  at most one minor second, repaired deterministically.
- **T11 (spectral drone stack)**: near-unison partials on exact rational
  ratios, each with its **own** 1/f drift on detune and on amplitude, clipped
  to the declared depth.
- **T13 (Karplus–Strong)**: the station's signature timbre, with a detuned
  chorus pair and the dotted-eighth delay resolved to an integer frame count
  at compose time. The tuning is corrected: the plain two-tap string measures
  **51.6 cents** flat over the guitar's range, the corrected one **0.315
  cents**.
- **A short Schroeder reverb** (8 parallel combs into 4 series allpasses) and
  the **two-bus graph**, with the KS bus's dry never summed and the reverb
  tapping the bus after the lowpass.
- **Gates 2 and 8 are in force**, with `validate.py`, the `GateFailure` data
  holder and the exit-code-2 path. A failing render writes **nothing**.
- **The 1/f primitive** is a deterministic, counter-based signal: a sum of
  one-pole lowpassed counter-based white sources with geometrically spaced
  cutoffs. The Voss–McCartney row sum was measured and rejected (4.7σ
  inter-sample steps = an audible pitch jump).

## Current state

- 265 tests pass; `ruff check`, `ruff format --check` and `mypy --strict` are clean.
- Measured on this machine: the 90 s ambient piece renders in 10.74 s of
  audio time (8.4× faster than realtime) with 331 MB peak RSS; the 10 s
  station render in 0.21 s with 143 MB; the 15-minute piece in 111 s with
  890 MB. Peak −18.001 dBFS, true peak −17.995 dBTP, integrated loudness
  −32.506 LUFS (ambient) and −26.297 LUFS (station). Both hashes stable
  across runs and across processes.
- The **frozen S0 artifact is still bit-identical**: its committed plan bytes
  are migrated into the new model and re-render to `892cb06a…` (a test, not
  a claim).

## Known issues and blockers

- **The render is memory-block-wise as of 2026-10-21.** The voices, the bus
  graph, the master chain and the loudness meter are all cut into blocks and
  carry their state; the 90 s piece peaks at 332 MB and a 15-minute one at
  887 MB, inside the 1.5 GB budget. What still grows with the track is the
  mix itself — one stereo float64 array, 605 MB at fifteen minutes — because
  the master chain needs the peak of the whole mix before it can stage it.
- **T1's phase did not advance, and now it does.** `np.cumsum` of a Python
  float is a one-element array, so the poly-period voice was the envelope
  times a constant: the loops were some 74 dB under the drone, which is to
  say inaudible, and the README's claim of "a bank of poly-period loops" was
  stronger than the artifact. Fixed on 2026-10-21 by carrying the running
  phase the way the pad and the drone do. The plan does not change, so the
  plan hash holds; the audio does, so the ambient golden moved to
  `f0909aa0…` and the piece is 1.75 LU quieter, because the loops are now
  the loudest thing in the mix and the master stages to the peak.
- **The other four lanes are still the S0 pad.** Only the ambient lane has
  the drone, the loops and the guitar, so most seeds of the station blend
  still land on a pad.
- **The live station render's hashes moved** (spec deviation D-9): the
  compose PRNG is seeded from the canonical JSON of the *whole* preset set,
  so changing any lane file changes every draw. The S0 artifact itself is
  preserved by freezing its plan (deviation D-9, test `test_migration.py`).
- **Gate 2's DC offset is measured on the delivered PCM, not the pre-master
  float mix** (deviation D-14). The pre-master mix has no absolute scale of
  its own, so an absolute limit there measures the arrangement rather than the
  master.
- **The DC blockers live in the instruments, not in the master chain**, so the
  S0 pad's bytes are untouched. A reverb's comb bank has a DC gain of
  1/(1−g) each, so the sources are blocked before the reverb and the comb
  sum is blocked again after it.
- **The Karplus–Strong above midi ≈ 89** exceeds three cents: the linear
  fractional read's second-order error grows. Out of the guitar's range for
  now.
- **The 1/f control rate is 4410 Hz** and the drift is interpolated to the
  audio rate with integer arithmetic, so a control point lands exactly on its
  own value.

## Next steps

1. ~~Get the `sdd-verify` verdict~~ — done: APPROVED, with the caveat that
   the remediation table was re-audited by the orchestrator and not by a
   second independent pair of eyes. That second pass is still owed.
2. ~~`sdd-archive` writes `sdd-s1-ambient-lane-done`~~ — done.
3. ~~**Make the render block-wise in memory**~~ — done, 2026-10-21. A
   15-minute piece fits the budget at 887 MB.
4. ~~**Fix T1's phase**~~ — done, 2026-10-21. The ambient golden moved to
   `f0909aa0…`; the S1 verify needs a re-run over the T1 criteria.
5. **S2 `s2-motorik-lane`** — drums, T6 euclidean rhythms with conditional
   triggers, T7 as a technique, T5 deja-vu sequencing, one 3-minute piece.
   Gates 2, 4, 7, 8.
6. **S3 `s3-arranger`** — section graph, tension curve, motif transforms, T14
   as a general arranger, T16 modal shift, kosmische and dub lanes. Gates 5,
   6, 13. **Stop and ask the human at the S3 checkpoint.**
7. S4 mix/master and the full gate set, S5 catalog and install, S6 the taste
   pass with a human listening.

## Relevant files

| Path | What it is |
|---|---|
| `src/indiegen/plan.py` | the event union, the Plan, the canonical hash |
| `src/indiegen/compose/rng.py` | the integer-only SplitMix64, the only randomness |
| `src/indiegen/compose/planner.py` | `compose()`: the only place a die is rolled |
| `src/indiegen/compose/techniques/` | T1, T11 and T13 as compose-time techniques |
| `src/indiegen/compose/director.py` | the pure Director, with its per-kind applicability |
| `src/indiegen/synth/noise.py` | the 1/f primitive and the counter-based mixer |
| `src/indiegen/synth/ks.py` | the tuned Karplus–Strong string |
| `src/indiegen/synth/drone.py` | the T11 drone stack |
| `src/indiegen/synth/poly_period.py` | the T1 voice |
| `src/indiegen/fx/line.py` | the block-structured delay lines |
| `src/indiegen/fx/reverb.py` | the short Schroeder reverb |
| `src/indiegen/fx/delay.py` | the dotted-eighth delay |
| `src/indiegen/render.py` | the two-bus graph and the block renderer |
| `src/indiegen/validate.py` | gates 2 and 8, and only those |
| `presets/ambient.yaml` | the ambient lane: T1, T11, T13, the reverb, 90 s |
| `tests/test_migration.py` | the frozen S0 artifact's bit-preservation test |
| `tests/golden/` | the plan goldens, the PRNG draws, the ambient PCM hash |
| `BRIEF.md` | the source brief. Immutable. The input to the SDD phases, never a file to refactor. |

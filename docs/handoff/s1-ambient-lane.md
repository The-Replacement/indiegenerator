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

- 257 tests pass; `ruff check`, `ruff format --check` and `mypy --strict` are clean.
- Measured on this machine: the 90 s ambient piece renders in 21.05 s of
  audio time (4.3× faster than realtime) with 823 MB peak RSS; the 10 s
  station render in 0.30 s with 211 MB. Peak −18.001 dBFS, true peak
  −17.995 dBTP, integrated loudness −31.079 LUFS (ambient) and −26.791 LUFS
  (station). Both hashes stable across runs and across processes.
- The **frozen S0 artifact is still bit-identical**: its committed plan bytes
  are migrated into the new model and re-render to `892cb06a…` (a test, not
  a claim).

## Known issues and blockers

- **The render is not yet memory-block-wise.** 90 s costs 823 MB, so a
  6–15 minute ambient piece will not fit the 1.5 GB budget. The voices are
  rendered whole and the mix is held in full. This is the next thing to fix,
  and it is a real limit of the current slice.
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

1. Get the `sdd-verify` verdict for `s1-ambient-lane`; fix and re-verify if
   it is NEEDS_WORK (max two cycles, then surface the table and stop).
2. `sdd-archive` writes `sdd-s1-ambient-lane-done`.
3. **Make the render block-wise in memory** so a 6–15 minute piece fits the
   budget. This belongs to the start of S2 or S3.
4. **S2 `s2-motorik-lane`** — drums, T6 euclidean rhythms with conditional
   triggers, T7 as a technique, T5 deja-vu sequencing, one 3-minute piece.
   Gates 2, 4, 7, 8.
5. **S3 `s3-arranger`** — section graph, tension curve, motif transforms, T14
   as a general arranger, T16 modal shift, kosmische and dub lanes. Gates 5,
   6, 13. **Stop and ask the human at the S3 checkpoint.**
6. S4 mix/master and the full gate set, S5 catalog and install, S6 the taste
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

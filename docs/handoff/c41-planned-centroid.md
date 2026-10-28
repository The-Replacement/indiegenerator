# c41 — the declared centroid, and the drone in the tension model (issue #37)

**Status: shipped. The gate-6 target is untouched, and that is the point.**

## What shipped

- `src/indiegen/spectrum.py` (new) — `declared_centroid_millihz(events, start, stop)`:
  the amplitude- and duration-weighted centroid of every partial of every
  additive event overlapping a section window, in integer millihz. `0` means
  "this section declares no additive spectrum". It imports
  `synth.osc.midi_to_hz` rather than restating the tuning, so it cannot drift
  from what the renderer plays. It lives outside `compose/` because
  `test_hygiene.py` forbids `compose/` importing `indiegen.synth`.
- `plan.py` — `SectionPlan.declared_centroid_millihz: int = Field(default=0, ge=0)`.
  Read by nothing at runtime. It is the plan naming its own material, so a later
  change can say how far that material moved.
- `compose/planner.py` — computed per section from the composed events.
- `compose/director.py` — **re-derived from the final events**. The deck contains
  `transpose_up_fourth`, which rewrites pad, drone and lead midi; a field
  computed before the moves would be stale in exactly the way gate 6's table is
  stale, inside the field that exists to name the staleness. Motorik 60 s
  section 4 reads 440 594 composed and 533 236 directed.
- `compose/tension.py` — `pitched_notes` gains `DroneEvent`.

## The design that was measured and refuted first

The issue originally said "derive the planned centroid from the declared
spectra". Measured over the 427-section corpus: an amplitude+duration-weighted
centroid of the declared partials reproduces the lane `timbre` table on **0 of
427 sections** within ±5 % (motorik 0.05–0.47×, kosmische 0.05–0.35×), and
rendered as gate 6's target it fails **2 of 15** sweep cells (motorik 240 s 1042
static variance 0.411 > 0.25; kosmische 2000 240 s r 0.373 < 0.4 against 0.817
for the table).

Cause: the table is a **render measurement**, and the presets say so —
`presets/motorik.yaml:37` "Measured on real renders of this lane (BRIEF 5:
measured, then tuned)". Motorik's pad is 2–N rolled-off harmonic partials on
root 57; its declared centroid is ~440 Hz against a table value of 4875 for the
plateau. The two numbers answer different questions. Replacing the target is not
a no-op and never can be.

So this change records, and does not derive-for-gate-6. The refutation is in the
issue body so it is not re-proposed.

## The drone enters the model as one note, not sixteen partials

`DroneEvent` contributes its segment root. Its partials are near-unison members
of a JI stack, and `tension.ROUGHNESS_WEIGHTS` is an interval-class model over
`(a−b) % 12`: reading sixteen near-unison partials as sixteen notes would turn
it into a beating model it is not. The root is the modal root, so a modal shift
still reaches the model through the same field the pad uses.

Falsifier, now passing: kosmische 240 s 1042 with the drone root +7 semitones
used to produce a **byte-identical** `FeatureSet`. Pitch now falls in every
section, and roughness rises except in the outro, where the drone sounds alone
and "fewer than two notes" is not a pair.

## Re-gauge: measured, constants kept, deviation declared

`TENSION_FEATURE_STD` is a single global mapping. "Re-gauge it for the drone
lanes" is not expressible without a per-lane table, which is a new mechanism and
out of scope. What was measured instead:

- corridor misses: unchanged on both seed sets, and unchanged per lane;
- trims: down (see below);
- sweep: 15/15.

On that evidence the constants stay, and the deviation is recorded as declared
staleness rather than fitted away. Note the shipped pitch constant is 905 while
this corpus measures 754 today — 20 % stale before this change — so re-fitting
it to the drone branch's own delta would be pseudo-precision.

## Effect on the c39 numbers

Measured by `/tmp/opencode/c41_corpus.py` (wraps `tension.walk`; a trim is an
index-wise difference between the declared level and the solved one), before at
`eb648c8` and after on this tree:

| corpus | sections | trims before → after | misses before → after |
|---|---|---|---|
| 5 lanes × {1042,2000,3005} × 6 durations | 424 | 8 → **5** | 0 → 0 |
| 5 lanes × {1042,2000,4002} × 6 durations | 427 | 10 → **8** | 2 → 2 |
| 30 station draws (5000–5029, 60 s) | 140 | 2 → **1** | 1 → 1 |

Trim magnitude grows even as the count falls: the largest lane trim goes from
−1700 mb to −2200 mb (kosmische 4002 90 s outro), and the largest station trim
from +500 mb to **+2900 mb** (station 5001 `break`, level −10 000 → −7100).
That station cell passes gates 4/5/6/7/13; it was rendered and checked because
no sweep case covers it.

## The unreachable corridor, and what the actuator spends on it

Station 5001 `break` still lands at −166 permille against a −160 floor **after**
a +2900 mb trim. `solve()` orders candidates by
`(inside_corridor, corridor_miss, distance_from_declared)`, so when nothing
lands it minimises the miss first: it bought 6 permille with 2.9 dB of level on
a break and still missed. Motorik 4002 `outro` does the same at −372 against
−340.

This is not fixed here — it is the actuator's documented behaviour. It is the
strongest argument for #10 having a rule for unreachable corridors ("spend
nothing when the corridor cannot be met") rather than a tolerance.

## The c39 figures were wrong, and are now corrected

`docs/handoff/c39-tension-budget.md` claimed 567 sections, 0 corridor misses, 11
trims. Measured at `eb648c8`: **564 sections, 1 miss, 10 trims**. The station
5001 miss and the motorik 4002 misses were never in the 424-section set. That
document now carries the measurement and a dated correction.

## Gates and checks

- `ruff check`, `ruff format --check`, `mypy src` — clean (62 files).
- `pytest -m sweep` — **15/15** in 11:13.
- 300 tests across the blast radius: `test_c41.py` (19), `test_plan`,
  `test_migration`, `test_validate`, `test_techniques`, `test_preset_consumption`,
  `test_c39` (196), `test_artifact`, `test_c32`, `test_hygiene`, `test_c21`,
  `test_c24`, `test_c25`, `test_director` (85).
- The frozen S0 plan still renders to `f97584b6…`; the ambient 90 s master is
  still `18aa71cd…`.
- The whole default suite was **not** run to completion in one process — it
  exceeds 30 minutes here. Coverage is the targeted files above plus the sweep.

## README

Two concurrent records were stale, and both were verified before touching them:

- the ambient 90 s sample block still described a **3-section** render with
  `pcm_sha256` `77510545…`; today's render has **4 sections** and
  `pcm_sha256` `18aa71cd…` (the committed artifact golden), so that block
  predates c27's widening of ambient's section graph. Replaced with the
  measured output.
- the five-lane `plan_sha256` row did not reproduce either: `git show eb648c8 --
  README.md` contains no `sha256` line at all, so c39 added plan fields and a
  README paragraph without ever re-measuring the row. Both rows are re-derived
  from renders at this commit and labelled with the commit they were measured
  at.

c39's README paragraph also carried the wrong calibration figures; it now says
564 sections, 1 miss, 10 trims, and names the unreachable cell.

## What this does not fix

- **Gate 6 still has no material-following target.** `timbre` is
  `function -> hz`, eight entries per lane. A per-section chord needs a
  per-section target, and the *shape* of that map is the blocker, not its
  values. #17 stays blocked on that, not on this issue.
- **#9b's cost is irreducible.** The table is a render measurement; any change
  to what sounds requires re-measuring it. That is calibration, not machinery,
  and this change does not make it cheaper — it makes the staleness nameable.
- No chord choice, no layer selection, no gate metric or limit change.

## Files

- `src/indiegen/spectrum.py` (new)
- `src/indiegen/plan.py` — the leaf
- `src/indiegen/compose/planner.py` — the composed value
- `src/indiegen/compose/director.py` — the re-derived value
- `src/indiegen/compose/tension.py` — the `DroneEvent` branch
- `tests/test_c41.py` (19), `tests/golden/plan_motorik_1042.*`
- `README.md` — re-derived hash rows
- `docs/handoff/c39-tension-budget.md` — the correction

## Harnesses

| harness | what it measures |
|---|---|
| `/tmp/opencode/c41_corpus.py` | sections, trims, corridor misses; runs on either tree via `PYTHONPATH` |
| `/tmp/opencode/c41-before/` | worktree at `eb648c8`, the before column |
| `/tmp/opencode/c39/features.py`, `gauge.py` | the four features and the corpus moments |

## Next

- **The gate-6 shape issue**: a per-section target, with the table as reference
  and the declared spectrum as ratio. Unmeasured; needs a probe before it is
  promised.
- **#10**: now has `declared_centroid_millihz`, `tension_permille` and the
  corridor, plus the unreachable-corridor evidence above.
- **#17** stays open and blocked on the shape issue, with its explore in memory.

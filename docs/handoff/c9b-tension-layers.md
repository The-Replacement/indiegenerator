# c9b tension layers (issue #9b, Commit2)

> **Re-scope & activation (2026-11-10, c38 fixed):** tension now tracks
> arrangement fullness (issue #38), so admission is re-scoped to
> **`T <= 421 → all` (fill sparse/fullness dips, pass1), else `density`**.
> Threshold 421 is evidence-based: pass1 T=421 (dub-electronic 4002/240s outro)
> admitted passes sweep gates, while pass1 T=422 (dub-electronic 2000/240s
> outro) admitted broke gate 6; kosmische 1042/60s outro pass1 T=420 remains
> admitted. The prior three-way `≥550 all / ≤450 bed / else density` rule and
> its gate/sweep results below reflect the pre-#38 walk and are retained as
> historical record; they do **not** describe the landed semantics.
> Activation (this change, `c9b-admission-activation`): four pitched lanes
> ship `tension_admission_enabled: true`, ambient remains off. Bed is
> pad+drone only via `CARD_SPECS.bed` (motorik `{pad}`, kosmische `{drone}`,
> dub/indie `{}` → density fallback). Director is unchanged; deck consumes
> admitted ranges. Production `check_gate_14` is unchanged (enforces
> `T=0.14985622568500778`).

Commit2 admits layers by planned tension level T where a lane opts in.
Under the landed (c38) semantics, sections at or below 421 (pass1) admit all
layers; above 421 the node's density is in charge. Thresholding emits only
`all` or `density` (`_admission_mode`); `admits()` still supports a `bed`
branch but it is not emitted by the current rule. K2 authority is reported,
not gated.

## Implementation (T6-T8)

- **T6** `LanePreset.tension_admission_enabled: bool = False` (`config.py:331`);
  YAML true in motorik/kosmische/dub/indie, ambient absent. `CardSpec.bed`
  pad/drone True, others False (`planner.py:1287,1440`). Plumbing only;
  `test_plan`/`test_presets` green, motorik golden byte-identical at T6.
- **T7** `TechniqueContext` gains `tension_admission_enabled`,
  `section_admission_modes`, `bed_instruments` and
  `admits(section, instrument, density, min_density)`:
  off/no-modes → density, `all` → True, `density` → `density >= min_density`,
  `bed` → `instrument in bed` (empty bed → density), unknown → `PlanError`.
  `SplitMix64.snapshot/restore` (`rng.py`). Vectors
  T{449,450,451,549,550,551} → bed/bed/density/density/all/all, first 500
  density, empty-bed density, snapshot-restore identity verified in
  `tests/test_c9b_tension_layers.py`.
- **T8** Two-pass `compose()` (`planner.py:1081`).
  OFF is a strict no-op: no snapshot/restore/second emit/rederive,
  byte-identical `canonical_json` vs HEAD for ambient (45/60/90/240 s hashes
  identical) and forced-False 60 s for all four lanes
  (motorik `b1c99cf6…`, kosmische `82d14fbf…`, dub `678bcf7b…`,
  indie `6d3d01ba…`). ON: snap before events → Pass1 density → `_tension_walk`
  (solve) → modes (≥550 all, ≤450 bed, else density) → restore → Pass2
  admitted → motif/postproc → rederive at Pass1 levels (no re-solve) →
  sections → deck with admitted ranges → micro timing.
  Two deviations from the literal order were required to hold AC2.7/AC2.8
  (see below): Pass1 walks the full motif+postproc material, and the
  fx/deck RNG state is restored from Pass1 before the fx/deck build.
  Builders via `ctx.admits`: pad/lead (entry retained)/drone/poly in
  `planner.py`; t6 kick/snare/hat/bass in `t6_drums.py` (instrument threaded
  through `_hit_frames`/`_audible`); t5 `pluck` in `t5_dejavu.py`; t13 `ks`
  in `t13_pluck.py` (verified in source, not guessed). `_playing_ranges`
  takes `ctx`; `_build_fx_deck_and_replay` threads it. `director.py`
  untouched, `validate.py` untouched.
  Spot (motorik 1042 60 s): admitted build gains 79 hats where T≥550
  (OFF build 0 hats → ON build 79); outro stays sparse. Kosmische 60 s
  build is all but carries no lead (entry retained).

### Why Pass1 includes the motif

Sparse sections carry no pitched lane material, so their pitch/roughness
are the motif's (dub45 outro: lane-only pitch 6000/rough 0 vs full
4600/0; motorik break: lane roughness 0 vs full 10000). Walking raw lane
events moved dub45's outro 522 → 562 and flipped it to all. Pass1
therefore walks the same material the committed walk sees
(`_motif_and_postproc`, factored out byte-identically for OFF).

### Why the deck snapshot

Admitted hats consume extra ghost draws, shifting every later draw
(motif cell, fx, deck). The deck then drew a harmful early `solo_texture`
on dub45/1042 (gate5 0.083 vs composed 0.907). Restoring the Pass1
post-motif state before `_build_fx_deck_and_replay` keeps the admitted
deck to admitted-range filtering alone: dub45 deck is again
`swap @1411200`, motorik 60 s deck identical (3 moves). Fx
(`dub_chain.drift_seed`) is stable too. Motif cell still moves
(motorik `[57,60,62,64]` → `[57,59,60,64]`); it does not drive gate5.

## Falsifier (T9)

Renders via `render_plan` + `master`, `energy_correlation` /
`timbre_measurement` / `tension_correlation`. Commit1 baselines:
dub45 gate5 0.90584 (`docs/handoff/c9b-rederive.md`), kos45 gate6 0.75044;
gate14 baselines from the c10 table (dub45 0.823082, kos45 0.985263,
`docs/handoff/c10-tension-gate.md` corpus b) because the pre-Commit1 PCM
is unchanged by the centroid-only Commit1.

| cell | gate | Commit1 | floor | post-Commit2 | absolute | verdict |
|---|---|---|---|---|---|---|
| dub 1042 45 s | 5 | 0.90584 | 0.8858 (−0.02) | 0.90717 | ≥0.5 | PASS |
| kos 1042 45 s | 6 | 0.75044 | 0.73044 (−0.02) | 0.75044 | ≥0.4 | PASS |
| dub 1042 45 s | 14 | 0.823082 | 0.773 (−0.05) | 0.95749 | T=0.1499 | PASS |
| kos 1042 45 s | 14 | 0.985263 | 0.935 (−0.05) | 0.98526 | T=0.1499 | PASS |

Kos45 is byte-identical ON vs OFF (plateau all is a no-op on a dense
section). Dub45 adds hats in build only; outro stays sparse. No
`validate.py` change.

## Sweep (T10)

PENDING — see final section.

## Goldens (T11)

- `tests/golden/plan_motorik_1042.{json,sha256}`: `b1c99cf6…` →
  `d33ee8c4…` (re-derived, enumerated below). Only golden that moves.
- `pcm_ambient_1042.sha256` `18aa71cd…`: frozen (ambient key absent;
  90 s `test_the_ambient_piece_matches_its_golden` passes).
- S0 `f97584b6…` and `plan_station_1042_s0`: frozen (`test_migration`
  passes). `prng_draws.txt`: frozen (snapshot has no draw effect).

Motorik 1042 60 s diff (HEAD golden → Commit2):

| section | level | tension | delta | centroid_hz | declared_millihz | instrumentation |
|---|---|---|---|---|---|---|
| s0 intro | −12000 → −12000 | 500 → 500 | 0 → 0 | 2198 → 2198 | 440594 → 439534 | same |
| s1 build | −6000 → −6000 | 552 → 549 | 52 → 49 | 5372 → 5372 | 440127 → 439873 | `+hat` |
| s2 break | −10000 → −10000 | 509 → 513 | −43 → −36 | 2018 → 2018 | 440551 → 439873 | same |
| s3 plateau | −5000 → −5000 | 561 → 562 | 52 → 49 | 4875 → 4875 | 440594 → 439492 | same |
| s4 outro | −14000 → −14000 | 510 → 454 | −51 → −108 | 2242 → 2242 | 533236 → 534263 | same |

Deck/log identical (3 moves; `drop_bass`, `swap`, `transpose_up_fourth`).
Events 68 → 68 by kind; hat hits 79 → 157 (`noise_seed` reshuffled),
bass hits re-voiced, pads/deja-vu/motif reshuffled as extra hat draws
cascade down the RNG (see report script). Motif
`[57,60,62,64]` → `[57,59,60,64]`; 5/7 appearances re-note.
Replay identical. No `centroid_hz` moves (Commit1 tables untouched).

## Consumption (T12) and hygiene (T13)

- Dedicated bool-flip test (`tests/test_c9b_tension_layers.py`):
  motorik 60 s ON vs forced-False differs, build gains `hat` where T≥550.
  Parse check: 4 True, ambient False. `test_preset_consumption` mutation
  sweep skips bools (`_mutate` returns None for bool), so its coverage
  test is unchanged.
- `bed ⇔ {pad, drone}` asserted in the new test; no `card.kind` dispatch
  outside `CARD_SPECS` (only `CARD_SPECS.get(card.kind)` for the bed).
  `test_hygiene` green.

## Station comment (T14)

`presets/station.yaml:67-70` now says the planned tension level T
decides the layers where a lane opts in (≥550 whole lane, ≤450 bed,
else density) and admission is per-lane, off by default
(`tension_admission_enabled: false unless a lane declares true`).

## Authority (T15, NOT GATED)

Method (primary): feature-walk on the same composed plan
(kosmische 1042 60 s). All-events vs bed-only (`{drone}`) through
`tension.section_features` + `walk` at the plan's levels.
Max |ΔT| = **24** (intro 0, build 24, plateau 11, break 18, outro 13).
With `{drone, motif}` the walk gives 38 (closest to the parent probe 42;
the gap is the motif-filter definition). Forced-compose all-vs-bed
(`_admission_mode` forced) gives 173, inflated by the outro lead plus
motif-RNG divergence. Reported here, **not gated** (K2 dropped);
the kill condition is AC2.7 gate regression only.

## Sweep and gate14 distribution

Sweep15 (5 lanes × {1042,2000,4002} × 240 s, `pytest tests/test_sweep.py -m sweep`):
**1/15 FAIL — motorik-1042 gate 6** (timbre correlation 0.2485 < 0.4). The
other 14 cells pass (wall 623 s). AC2.8 blocked.

Failure mechanism (verified against `fd9bfef` in a worktree): admission is
keyed on first-pass `tension_permille`, and at 240 s the motorik-1042 walk
puts break T=693 and outro T=640 (both ≥ 550), so `_admission_mode` selects
`all` and densifies them. At 60 s the same seed gives break 509 / outro 510
(< 550 → `density`), which is why the 60 s golden passes. Commit1
(density-only) renders the same cell at corr 0.9978 (break sparse, delivered
2141 vs planned 2018); Commit2 delivers 5420/6743.

Root cause is **not** the admission code: `tension_permille` is a
perceived-tension signal dominated by a roughness spike (β=5 amplification),
anti-correlated with fullness. The 240 s break's motif transposes to 56/68
against the sustained pad at 57 (minor-second/major-seventh, weight 10) →
roughness 10000 → +193 permille step from roughness alone.

Decision (2026-11-09): fix the tension walk's roughness dominance, tracked as
**issue #38** (touches the gated c39/c41 model + gate 14 re-calibration, #10).
c9b Commit2 admission is blocked on #38; do not land as-is.

S0/ambient frozen verified (AC2.9): `test_migration` + ambient golden 5/5.
Gate-14 distribution script: `tools/c9b_gate14_dist.py` (written, not run —
blocked on #38).

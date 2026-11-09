# c38 tension roughness (issue #38)

The tension walk's roughness term dominated the step via beta=5 amplification,
so a quiet break read as the piece's tension *peak* and `tension_permille`
anti-correlated with arrangement fullness. This broke c9b admission (blocked),
which keys layer selection on tension at 550/450.

## Fix

Two changes, both sides of the model (the compose walk and the gate-14
predictor are verbatim twins on `plan.TENSION_WEIGHTS`):

- **beta=5 confined to loudness** — `tension.step()` and
  `validate._measured_step_float()` apply `TENSION_BETA` only when
  `name == "loudness"`; pitch/roughness/onset get beta=1. The memory-window
  amplification is only defensible for the loudness actuator.
- **roughness weight 200 → 0** — `plan.TENSION_WEIGHTS["roughness"] = 0`.
  Roughness is a saturating, bimodal noise feature (0 or 10000 on a single
  dissonant interval; typical ~4 permille, spike ~38). Dropped, not reduced.

### Why beta-only was insufficient

beta-on-loudness-only alone dropped the 240 s break 693 → 550, but 550 is
still `≥ 550 → "all"`. The roughness spike at beta=1 (weight 200) still
contributed +38, cancelling loudness (−22) + onset (−18). The weight had to
go to zero; see the spec amendment
(`sdd-c38-tension-roughness-spec-amendment`).

## Falsifier results (motorik-1042)

| section | 240 s before | 240 s after | 60 s after |
|---|---|---|---|
| build | 551 | 547 | 545 |
| break | **693** | **507** | 510 |
| plateau | 556 | 556 | 571 |
| outro | **640** | **486** | 490 |

Break/outro now sit below 550 → c9b `density` mode (sparse), and below build
(a dip, not a peak). Fullness-shaped.

- **Sweep15** (gates 4,5,6,7,13): 15/15 PASS.
- **S0 PCM `f97584b6`** and **ambient `18aa71cd`**: frozen (levels unchanged).
- **Gate 14 re-calibration**: PROMOTE-ELIGIBLE. Pooled measured
  0.869990 vs null −0.000144, diff 0.870133 (> 0.15 in every corpus a/b/c).
  New `TENSION_CORRELATION_LIMIT` = **0.14985622568500778** (was
  0.1499084456057718). See `c38-tension-roughness.json` for the full corpus.

## Goldens

`plan_motorik_1042.json` re-derived `8f49a273…`; the delta is **tension-only**
(levels, centroids, events, deck unchanged):

| section | tension | delta |
|---|---|---|
| build | 552 → 545 | 52 → 45 |
| break | 509 → 510 | −43 → −35 |
| plateau | 561 → 571 | 52 → 61 |
| outro | 510 → 490 | −51 → −81 |
| intro | same | same |

No other golden moves.

## Housekeeping (pre-existing defect)

c9b Commit1 (`fd9bfef`) re-derived `presets/kosmische.yaml` timbre but never
updated `tests/test_c41.py`'s hardcoded `centroid_hz` assertion, leaving the
committed tree red. Fixed (2-line value update): intro 1658→994, build
1776→1824, break 1569→995, drift 2373→1878, return 2056→1674, outro 1050→862.

## c9b consequence (not a #38 blocker)

Build at 60 s is now T=545 (< 550), so c9b's `all` mode no longer fires on
build — tension now tracks fullness (loud sections are already dense), so
"add layers at high tension" shrinks. Re-scope c9b's admission premise when
it re-lands.

## Tests added

- `test_c39`: `test_a_repeated_material_direction_is_not_amplified`,
  `test_roughness_carries_no_weight`.
- `test_validate`: `test_measured_step_confines_beta_to_loudness`.
- `test_c38_tension_fullness_shape.py`: break/outro dips + < 550 @240 s.

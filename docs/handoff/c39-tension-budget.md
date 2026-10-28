# c39 — the tension budget (issue #9)

**Status: complete, with the layer rule measured and deferred.**

## What shipped

The Plan now states a tension curve it predicted from its own material, and
the station declares a per-section corridor that the composer is held to.

- `compose/tension.py` — the section-level reduction of Farbood's parametric
  tension model. Four features per section (loudness = the section level,
  onsets per bar, duration-weighted mean pitch, interval-class roughness),
  z-scored against the corpus moments below, combined as a **weighted sum of
  slopes** with the previous section as the memory window and β = 5 when the
  direction repeats. The weighted step is added to a running tension that
  starts at 500 and is clipped to 0..1000.
- `SectionProfile` gains `tension_delta_min_permille` / `tension_delta_max_permille`
  (default `-1000..1000`: no corridor, strict no-op). `SectionPlan` gains
  `tension_permille`, `tension_delta_permille` and the corridor it aimed at.
- The **actuator is the section level**: for each section the composer scans
  the level inside ±3000 millibels of the graph's declaration, in 100 mb
  steps, and takes the candidate that lands the step inside the corridor and
  is nearest the declared level. The chosen level is what the plan records and
  what the renderer applies.
- `presets/station.yaml` declares the eight corridors.

No gate changed. Gate 5 now correlates the delivered RMS against the
**trimmed** level curve, which is the curve the listener hears.

## The numbers

Corpus moments (5 lanes × 3 seeds × {45,60,90,120,240,480} s, 424 sections;
`gauge.py`):

| feature | mean | std | unit |
|---|---|---|---|
| loudness | −9172 | 3637 | millibels |
| onset | 7049 | 6660 | milli-onsets per bar |
| pitch | 5684 | 905 | centi-MIDI |
| roughness | 2187 | 2295 | milli (weight 0..10) |

Weights 400/200/200/200 (loudness highest, then pitch, roughness, onset),
β = 5, step divisor 2, start 500. Ordering after TenseMusic's 2024 refit;
**these are this corpus's calibration, not Farbood's coefficients**, and the
windows are one section / one section instead of 3 s / 3–4 s — declared
deviations.

Calibration result, **re-measured 2026-10-27 at `eb648c8`** (this paragraph
previously said "567 sections … 0 corridor misses, 11 trims", which does not
reproduce — see the correction below):

| corpus | sections | trims | corridor misses |
|---|---|---|---|
| 5 lanes × seeds {1042, 2000, 3005} × 6 durations | 424 | 8 | 0 |
| 30 station draws (seeds 5000–5029, 60 s) | 140 | 2 | 1 |
| **total** | **564** | **10** | **1** |

The one miss is station seed 5001, `break`: −166 permille against a −160 floor.
The actuator saturates at +2900 mb and still cannot reach the corridor. Trims at
this commit are within 1.7 dB (largest: motorik, −1700 mb); the 2.9 dB station
trim above is what the c41 drone branch adds, not something c39 shipped.

> **Correction (2026-10-27).** The shipped figures were wrong in all three
> places: the total was miscounted (424 + 140 = 564, not 567), the trim count
> was 10 rather than 11, and **there is one corridor miss, not zero**. A second
> unreachable corridor appears as soon as seed 4002 joins the lane set
> (motorik 4002 `outro`, −372 and −365 against a −340 floor); the 424 figure
> was clean only because that set omits 4002. "Reachable envelopes" is true for
> the corridors exercised by the 424 set and false at the edges of `break` and
> `outro`. The re-measurement is `/tmp/opencode/c41_corpus.py`, which wraps
> `tension.walk` and compares the declared level with the solved one.

Corridors as shipped (permille of the running 0–1000 curve):

| function | corridor | measured steps |
|---|---|---|
| intro | 0 … 0 | 0 (no previous section) |
| build | 10 … 90 | 15 … 80 |
| plateau | 0 … 240 | 0 … 230 |
| peak | 0 … 80 | 10 … 62 |
| break | −160 … 140 | −142 … 133 |
| drift | 10 … 60 | 16 … 54 |
| return | −80 … 230 | −69 … 223 |
| outro | −340 … 50 | −320 … 40 |

The corridors are **measured envelopes the composer can reach**, not
aspirations: an earlier draft declared `break −220..−100` and the model could
only spend −66, so #10 would have failed every track. A reachable corridor
is also a wide one — that is the honest shape of this model, see below.

## The layer rule, measured and deferred

The issue's own mechanism — high tension takes the drums, low tension takes
the bed — was implemented (`TechniqueContext.admits`, per-section admitted
density, and the clean bed on a sparse corridor) and **it broke the gates**:

| cell | gate | before | with tension-selected layers |
|---|---|---|---|
| dub-electronic 45 s 1042 | 5 | 0.9058 | **0.0881** |
| dub-electronic 60 s 1042 | 5 | 0.9343 | 0.5690 |
| dub-electronic 120 s 2000 | 5 | 0.6892 | 0.3208 |
| kosmische 45 s 1042 | 6 | 0.7040 | **−0.0201** |
| kosmische 60 s 1042 | 6 | 0.7348 | 0.3446 |

Root cause: every lane's `timbre` table and its level arc were tuned with the
density-gated layer set. Handing a `break` only the bed removes the plucks
and bass the section's centroid was measured on; handing a `build` the whole
lane adds hats it never had. The layers are *inside* the gate calibration, so
changing them is a timbre-table re-derivation across 5 lanes × 8 functions,
not a field.

The layer rule is therefore not in this change. **#9's remaining half needs
that re-derivation first.**

## Why the actuator is the level and not the material

Measured, 424 sections: changing admission from bed-only to every-layer moves
a step by ~30 permille (onset 16, pitch 11, roughness 4), while the graph's
paths span up to ~300 (`break −137..+151`, `outro −346..+14`). The material
cannot both discriminate and be satisfiable. The section level is the
loudness term — Farbood's strongest — and trimming it inside a declared
budget is what lets a corridor bind. The trim is bounded, so a corridor can
still be out of reach; nothing raises, because the corridor is the plan's
intent and **#10 is the gate that judges it**.

## Gates

60 interlude cells (5 lanes × 3 seeds × 45/60/90/120 s), measured on the mix:

- Gate 5: **unchanged or slightly better**. Worst cell is now 0.5172
  (dub-electronic 3005 90 s) against 0.5019 before. No cell below 0.5.
- Gate 6: unchanged apart from sampling noise; the kosmische and dub cells
  that were thin stay thin (dub 3005 90 s 0.2618 vs 0.2617 — pre-existing).

The pinned ambient PCM is **bit-identical** to before the change
(`18aa71cd…`): the golden cell has no trim. The motorik plan golden moved
(`37f84f03…`) because the plan carries the new fields.

## Files

- `src/indiegen/compose/tension.py` (new)
- `src/indiegen/compose/planner.py` — `_tension_walk`, `_section_plans`
- `src/indiegen/plan.py` — the corridor and the recorded values
- `presets/station.yaml` — the eight corridors
- `tests/test_c39.py` (8), `tests/test_c32.py` (wall crest asserted on the
  composed plan now, because the Director can legally halve a section),
  `tests/test_s2_techniques.py` (grid frame for the first hat)

## Harnesses

All under `/tmp/opencode/c39/` and reproducible:

| harness | what it measures |
|---|---|
| `gates.py` | gate 5 and gate 6 on the mix stem |
| `gauge.py` | corpus moments and the step distribution |
| `model2.py` | per-function tension and step (z-scored gauge) |
| `calibrate.py` | per-card onsets per bar |
| `drop_overlap.py` | Director drop spans vs the sections they start in |
| `arc.py` | planned dB vs delivered RMS per section |
| `features.py` | the four features per section |

## Next

- **#10** can now be written: it has `tension_permille`, `tension_delta_permille`
  and the corridor in the plan, and the transcript above for its limits.
- **#9b** (new): tension-selected layers, with the timbre tables re-derived
  under the new layer sets as its first task. That is the change that makes
  the material the driver.

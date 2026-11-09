# c9b timbre re-derive (issue #9b, Commit1)

Fit ONLY from sweep15 (tests/test_sweep.py:37-40): 5 lanes x seeds (1042, 2000, 4002) x 240 s.
Corpus is 18 cells: sweep15 (15) + falsifier dub-electronic 1042 45 s + kosmische 1042 45 s
+ authority kosmische 1042 60 s (AC1.1). Falsifier/authority are hold-outs, never fit.

Method (AC1.2): gate 6 measurement verbatim - validate.per_second_centroid on the
render_plan pre-master mix (validate.py:476-497), validate._section_means (:804-818) with
start=_first_second, per-function duration-weighted mean (weight = last-first :814-815),
int round, clamp >= 1. section.function -> timbre key; only preset keys are written
(motorik 7 keys, peak excluded, never invented). Zero-section functions keep old + report.
Ambient excluded from fit (flat 560); ambient.yaml byte-identical (AC1.3/AC1.6).

- Fit wall time: 472.0 s
- Fit cells rendered: 15 (sweep15)
- Corpus cells defined: 18 = sweep15 (15) + falsifier (2) + authority (1)

## Old -> new timbre (fit lanes)

| lane | function | old | new | sections | weight (sec) |
|---|---|---|---|---|---|
| motorik | break | 2150 | 2018 | 2 | 70 |
| motorik | build | 4593 | 5372 | 3 | 196 |
| motorik | drift | 4486 | 5961 | 1 | 34 |
| motorik | intro | 1473 | 2198 | 3 | 95 |
| motorik | outro | 1401 | 2242 | 3 | 100 |
| motorik | plateau | 4875 | 4875 | 2 | 128 |
| motorik | return | 4708 | 6569 | 2 | 64 |
| kosmische | break | 1569 | 995 | 2 | 58 |
| kosmische | build | 1776 | 1824 | 3 | 197 |
| kosmische | drift | 2373 | 1878 | 1 | 33 |
| kosmische | intro | 1658 | 994 | 3 | 88 |
| kosmische | outro | 1050 | 862 | 3 | 117 |
| kosmische | peak | 2036 | 2036 | 0 | 0 |
| kosmische | plateau | 1780 | 1621 | 2 | 132 |
| kosmische | return | 2056 | 1674 | 3 | 92 |
| dub-electronic | break | 1687 | 1509 | 2 | 68 |
| dub-electronic | build | 2642 | 5014 | 3 | 216 |
| dub-electronic | drift | 1855 | 1855 | 0 | 0 |
| dub-electronic | intro | 1578 | 2391 | 3 | 104 |
| dub-electronic | outro | 1742 | 2080 | 3 | 112 |
| dub-electronic | peak | 3298 | 3298 | 0 | 0 |
| dub-electronic | plateau | 3014 | 5106 | 3 | 217 |
| dub-electronic | return | 3224 | 3224 | 0 | 0 |
| indie-noise | break | 7318 | 6334 | 1 | 30 |
| indie-noise | build | 7905 | 7061 | 3 | 219 |
| indie-noise | drift | 7229 | 7229 | 0 | 0 |
| indie-noise | intro | 7378 | 6301 | 3 | 102 |
| indie-noise | outro | 7376 | 6317 | 3 | 118 |
| indie-noise | peak | 7506 | 7506 | 0 | 0 |
| indie-noise | plateau | 7736 | 6989 | 3 | 218 |
| indie-noise | return | 7983 | 7461 | 1 | 30 |

## Section counts and kept-old / excluded

- motorik: 16 sections, weight 687 s, kept_old=[], excluded_functions={'peak': 1} (1 observations)
- kosmische: 17 sections, weight 717 s, kept_old=['peak'], excluded_functions={} (0 observations)
- dub-electronic: 14 sections, weight 717 s, kept_old=['drift', 'peak', 'return'], excluded_functions={} (0 observations)
- indie-noise: 14 sections, weight 717 s, kept_old=['drift', 'peak'], excluded_functions={} (0 observations)
- ambient: excluded from fit (flat 560), yaml untouched

## Falsifier (hold-outs, post-patch preset)

| lane | seed | seconds | gate | measured | floor | baseline | pass |
|---|---|---|---|---|---|---|---|
| dub-electronic | 1042 | 45 | 5 | 0.90584 | 0.8858 | 0.90584 | True |
| kosmische | 1042 | 45 | 6 | 0.75044 | 0.6840 | 0.70398 | True |
| kosmische | 1042 | 60 | authority | gate5=0.94373 gate6=0.74689 static=False | - | - | - |

**K1: PASS** - gate5 0.9058436069984273 vs floor 0.8858, gate6 0.7504397244820229 vs floor 0.684.

## Goldens / STD audit (T4)

- Plan diff vs HEAD (motorik 1042 60 s and kosmische 1042 60 s, canonical JSON):
  identical after stripping `sections[].centroid_hz`; levels, tension, events,
  strategy_deck and director_log byte-identical. Only centroid_hz moves.
- Motorik golden sections (before -> after):
  - s0 intro 1473 -> 2198, s1 build 4593 -> 5372, s2 break 2150 -> 2018,
    s3 plateau 4875 -> 4875 (unchanged), s4 outro 1401 -> 2242.
- `tests/golden/plan_motorik_1042.json`/`.sha256` re-derived (and only this golden):
  57a0d668eb1db4c60471d259e55f151d2a0dbbab959ad2f31c547eec5da9f650 ->
  b1c99cf6f895aba2d6298ec44de314ca7c4a51729fd719cd233e047fba5e366f.
- `plan_station_1042_s0.json` and `prng_draws.txt`: unchanged (git diff empty).
- S0 frozen `f97584b6cddf83fb3090ae25afe7d00b23b49bf2617860123f65614afc9307a9`
  and ambient `18aa71cd33393bfd4d246bffcde4a2be7f134dfc0745942145a1f77b0ad00fa3`:
  frozen, verified by `tests/test_migration.py` and
  `test_the_ambient_piece_matches_its_golden` (both pass).
- STD frozen: `git diff src/indiegen/plan.py` empty (plan.py:40-65 tension constants).

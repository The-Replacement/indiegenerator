# c10 tension gate null harness (issue #10, T9)

**Status: threshold harness only (T9).** No gate constant is changed here;
Slice 2 DSP is not attempted, so it is vacuous per spec and promotion
follows AC-3.3 alone when the corpus and promotion conditions are met.

**Amended AC-3.2 (user-approved 2026-11-07, amendment memory id 3639f1ac-727d-5b6e-956d-0957c851cdc7 / topic_key sdd-c10-tension-gate-spec-amendment):** corpus (b) expanded to 90 cells on durations [45, 60, 90, 120, 240, 480] (the full 6-duration / 424-section c39 calibration basis); seeds, lanes, corpus (a) sweep15, and all other ACs unchanged; target stays >=500 sections. This expanded re-run supersedes the v1 351-section run (75 tracks: 73 + 278 sections, verdict AC-3.2 NOT MET); the verdict below governs T10.
**Spec amendment #2 (memory id 94f500a6... / topic_key sdd-c10-tension-gate-spec-amendment2, 2026-11-07):** corpus (c) station draws added — 30 tracks seeds 5000..5029 at 60 s via director(compose(load_preset('station'), seed, 60*44100)) (verified against tests/test_c35.py:21,36 and docs/handoff/c39-tension-budget.md:54-56 / docs/handoff/c41-planned-centroid.md:83: 140 sections); appended AFTER (a) then (b) in corpus order (single rng0 draws consumed (a)->(b)->(c)). Union = (a) sweep15 (73 sections) + (b) 90 cells (424 sections) + (c) station 30 (~140 sections) = ~637 sections, target >=500. This re-run supersedes the amendment-1 expanded 497-section run 37a9117f (verdict AC-3.2 NOT MET) and fully re-renders every cell: the prior JSON holds Pearsons but not PCM, and the M vectors must be re-measured (no cached Pearson is reused as a null substitute).

## Corpus (AC-3.2, as amended)

- Lanes (test_sweep.py:37 order): motorik, kosmische, dub-electronic, indie-noise, ambient
- (a) sweep15: seeds [1042, 2000, 4002] at 240 s via director(compose(load_preset(lane), seed, 240*44100)), rendered through the in-memory test_sweep path (render_plan + master)
- (b) recreated c39: seeds [1042, 2000, 3005] x durations [45, 60, 90, 120, 240, 480] s (90 cells, docs/handoff/c39-tension-budget.md:54,128; amended AC-3.2, memory 3639f1ac-727d-5b6e-956d-0957c851cdc7)
- (c) station draws: preset 'station' via director(compose(load_preset('station'), seed, 60*44100)), seeds 5000..5029 at 60 s (30 tracks; tests/test_c35.py:21,36; docs/handoff/c39-tension-budget.md:54-56; docs/handoff/c41-planned-centroid.md:83)
- Corpus order: (a) lane-then-seed, then (b) lane-then-seed-then-duration, then (c) seed ascending;
  the null rng draws are consumed in that order.
- Null: 1000 within-track permutations of M,
  ``validate.pearson(permuted_M, P)``, single rng ``np.random.default_rng(0)``.
- Wall time: 3151.2 s

## Section counts

| corpus | tracks | total sections | non-exempt sections | non-exempt tracks |
|---|---|---|---|---|
| (a) sweep15 | 15 | 73 | 73 | 15 |
| (b) recreated c39 | 90 | 424 | 424 | 90 |
| (c) station draws | 30 | 140 | 140 | 30 |
| pooled union | 135 | 637 | 637 | 135 |

Corpus target: 500 sections (total).

## Results (AC-3.1 / AC-3.3)

| pool | measured_mean | null_mean | diff (measured-null) | T = null_mean + 0.15 |
|---|---|---|---|---|
| pooled | 0.859703 | -0.000092 | 0.859794 | 0.149908 |
| (a) sweep15 | 0.776756 | -0.002214 | 0.778969 | 0.147786 |
| (b) recreated c39 | 0.865679 | 0.000605 | 0.865074 | 0.150605 |
| (c) station draws | 0.883247 | -0.001120 | 0.884367 | 0.148880 |

Promotion requires diff > 0.15 pooled AND in each corpus (a)/(b)/(c) (AC-3.3).

## Per-track Pearsons (measured, non-exempt in corpus order)

| corpus | lane | seed | seconds | sections | exempt | pearson |
|---|---|---|---|---|---|---|
| a | motorik | 1042 | 240 | 5 | - | 0.992435 |
| a | motorik | 2000 | 240 | 6 | - | 0.724350 |
| a | motorik | 4002 | 240 | 6 | - | 0.990969 |
| a | kosmische | 1042 | 240 | 6 | - | 0.945156 |
| a | kosmische | 2000 | 240 | 6 | - | 0.830697 |
| a | kosmische | 4002 | 240 | 5 | - | -0.349827 |
| a | dub-electronic | 1042 | 240 | 4 | - | 0.599609 |
| a | dub-electronic | 2000 | 240 | 5 | - | 0.997436 |
| a | dub-electronic | 4002 | 240 | 5 | - | 0.905580 |
| a | indie-noise | 1042 | 240 | 4 | - | 0.804351 |
| a | indie-noise | 2000 | 240 | 6 | - | 0.367630 |
| a | indie-noise | 4002 | 240 | 4 | - | 0.893746 |
| a | ambient | 1042 | 240 | 4 | - | 0.973840 |
| a | ambient | 2000 | 240 | 3 | - | 0.999943 |
| a | ambient | 4002 | 240 | 4 | - | 0.975422 |
| b | motorik | 1042 | 45 | 5 | - | 0.946814 |
| b | motorik | 1042 | 60 | 5 | - | 0.924115 |
| b | motorik | 1042 | 90 | 5 | - | 0.984710 |
| b | motorik | 1042 | 120 | 5 | - | 0.977699 |
| b | motorik | 1042 | 240 | 5 | - | 0.992435 |
| b | motorik | 1042 | 480 | 5 | - | 0.951831 |
| b | motorik | 2000 | 45 | 6 | - | 0.987858 |
| b | motorik | 2000 | 60 | 6 | - | 0.998375 |
| b | motorik | 2000 | 90 | 6 | - | 0.990307 |
| b | motorik | 2000 | 120 | 6 | - | 0.999331 |
| b | motorik | 2000 | 240 | 6 | - | 0.724350 |
| b | motorik | 2000 | 480 | 6 | - | 0.960777 |
| b | motorik | 3005 | 45 | 4 | - | 0.977936 |
| b | motorik | 3005 | 60 | 4 | - | 0.950636 |
| b | motorik | 3005 | 90 | 4 | - | 0.472651 |
| b | motorik | 3005 | 120 | 4 | - | 0.714606 |
| b | motorik | 3005 | 240 | 4 | - | 0.831732 |
| b | motorik | 3005 | 480 | 4 | - | 0.906958 |
| b | kosmische | 1042 | 45 | 4 | - | 0.985263 |
| b | kosmische | 1042 | 60 | 5 | - | 0.972342 |
| b | kosmische | 1042 | 90 | 6 | - | 0.935104 |
| b | kosmische | 1042 | 120 | 6 | - | 0.997635 |
| b | kosmische | 1042 | 240 | 6 | - | 0.945156 |
| b | kosmische | 1042 | 480 | 6 | - | 0.998680 |
| b | kosmische | 2000 | 45 | 4 | - | 0.989183 |
| b | kosmische | 2000 | 60 | 4 | - | 0.854573 |
| b | kosmische | 2000 | 90 | 6 | - | 0.999927 |
| b | kosmische | 2000 | 120 | 6 | - | 0.998985 |
| b | kosmische | 2000 | 240 | 6 | - | 0.830697 |
| b | kosmische | 2000 | 480 | 6 | - | 0.997868 |
| b | kosmische | 3005 | 45 | 4 | - | 0.998439 |
| b | kosmische | 3005 | 60 | 4 | - | 0.904351 |
| b | kosmische | 3005 | 90 | 6 | - | 0.994232 |
| b | kosmische | 3005 | 120 | 6 | - | 0.995109 |
| b | kosmische | 3005 | 240 | 6 | - | 0.989701 |
| b | kosmische | 3005 | 480 | 6 | - | 0.988560 |
| b | dub-electronic | 1042 | 45 | 4 | - | 0.823082 |
| b | dub-electronic | 1042 | 60 | 4 | - | 0.852729 |
| b | dub-electronic | 1042 | 90 | 4 | - | 0.907256 |
| b | dub-electronic | 1042 | 120 | 4 | - | 0.092965 |
| b | dub-electronic | 1042 | 240 | 4 | - | 0.599609 |
| b | dub-electronic | 1042 | 480 | 4 | - | 0.992082 |
| b | dub-electronic | 2000 | 45 | 5 | - | 0.860072 |
| b | dub-electronic | 2000 | 60 | 5 | - | 0.850009 |
| b | dub-electronic | 2000 | 90 | 5 | - | 0.974058 |
| b | dub-electronic | 2000 | 120 | 5 | - | 0.999672 |
| b | dub-electronic | 2000 | 240 | 5 | - | 0.997436 |
| b | dub-electronic | 2000 | 480 | 5 | - | 0.938400 |
| b | dub-electronic | 3005 | 45 | 4 | - | 0.816166 |
| b | dub-electronic | 3005 | 60 | 6 | - | 0.334724 |
| b | dub-electronic | 3005 | 90 | 6 | - | 0.900918 |
| b | dub-electronic | 3005 | 120 | 6 | - | 0.854739 |
| b | dub-electronic | 3005 | 240 | 6 | - | 0.986184 |
| b | dub-electronic | 3005 | 480 | 6 | - | 0.975407 |
| b | indie-noise | 1042 | 45 | 4 | - | 0.426362 |
| b | indie-noise | 1042 | 60 | 4 | - | 0.773499 |
| b | indie-noise | 1042 | 90 | 4 | - | 0.996261 |
| b | indie-noise | 1042 | 120 | 4 | - | 0.993354 |
| b | indie-noise | 1042 | 240 | 4 | - | 0.804351 |
| b | indie-noise | 1042 | 480 | 4 | - | 0.099694 |
| b | indie-noise | 2000 | 45 | 5 | - | 0.996894 |
| b | indie-noise | 2000 | 60 | 6 | - | 0.383301 |
| b | indie-noise | 2000 | 90 | 6 | - | 0.874991 |
| b | indie-noise | 2000 | 120 | 6 | - | 0.615956 |
| b | indie-noise | 2000 | 240 | 6 | - | 0.367630 |
| b | indie-noise | 2000 | 480 | 6 | - | 0.961592 |
| b | indie-noise | 3005 | 45 | 4 | - | 0.983990 |
| b | indie-noise | 3005 | 60 | 4 | - | 0.996366 |
| b | indie-noise | 3005 | 90 | 4 | - | 0.962019 |
| b | indie-noise | 3005 | 120 | 4 | - | 0.905671 |
| b | indie-noise | 3005 | 240 | 4 | - | 0.894924 |
| b | indie-noise | 3005 | 480 | 4 | - | 0.997288 |
| b | ambient | 1042 | 45 | 4 | - | 0.472825 |
| b | ambient | 1042 | 60 | 4 | - | 0.910740 |
| b | ambient | 1042 | 90 | 4 | - | 0.358342 |
| b | ambient | 1042 | 120 | 4 | - | 0.435282 |
| b | ambient | 1042 | 240 | 4 | - | 0.973840 |
| b | ambient | 1042 | 480 | 4 | - | 0.982027 |
| b | ambient | 2000 | 45 | 3 | - | 0.991292 |
| b | ambient | 2000 | 60 | 3 | - | 0.995891 |
| b | ambient | 2000 | 90 | 3 | - | 0.999995 |
| b | ambient | 2000 | 120 | 3 | - | 0.993583 |
| b | ambient | 2000 | 240 | 3 | - | 0.999943 |
| b | ambient | 2000 | 480 | 3 | - | 0.999727 |
| b | ambient | 3005 | 45 | 4 | - | 0.989109 |
| b | ambient | 3005 | 60 | 4 | - | 0.959204 |
| b | ambient | 3005 | 90 | 4 | - | 0.462102 |
| b | ambient | 3005 | 120 | 4 | - | 0.958231 |
| b | ambient | 3005 | 240 | 4 | - | 0.992799 |
| b | ambient | 3005 | 480 | 4 | - | 0.977633 |
| c | station | 5000 | 60 | 3 | - | 0.993550 |
| c | station | 5001 | 60 | 6 | - | 0.802510 |
| c | station | 5002 | 60 | 5 | - | 0.963829 |
| c | station | 5003 | 60 | 5 | - | 0.966363 |
| c | station | 5004 | 60 | 3 | - | 0.940896 |
| c | station | 5005 | 60 | 6 | - | 0.991853 |
| c | station | 5006 | 60 | 4 | - | 0.972999 |
| c | station | 5007 | 60 | 4 | - | 0.594764 |
| c | station | 5008 | 60 | 4 | - | 0.823907 |
| c | station | 5009 | 60 | 5 | - | 0.977499 |
| c | station | 5010 | 60 | 4 | - | 0.994021 |
| c | station | 5011 | 60 | 3 | - | 0.999763 |
| c | station | 5012 | 60 | 4 | - | 0.981521 |
| c | station | 5013 | 60 | 4 | - | 0.681602 |
| c | station | 5014 | 60 | 4 | - | 0.773964 |
| c | station | 5015 | 60 | 6 | - | 0.181851 |
| c | station | 5016 | 60 | 6 | - | 0.840989 |
| c | station | 5017 | 60 | 4 | - | 0.942262 |
| c | station | 5018 | 60 | 6 | - | 0.991526 |
| c | station | 5019 | 60 | 6 | - | 0.908104 |
| c | station | 5020 | 60 | 5 | - | 0.905549 |
| c | station | 5021 | 60 | 3 | - | 0.951901 |
| c | station | 5022 | 60 | 6 | - | 0.906222 |
| c | station | 5023 | 60 | 6 | - | 0.897721 |
| c | station | 5024 | 60 | 4 | - | 0.929169 |
| c | station | 5025 | 60 | 4 | - | 0.996659 |
| c | station | 5026 | 60 | 6 | - | 0.998149 |
| c | station | 5027 | 60 | 6 | - | 0.615855 |
| c | station | 5028 | 60 | 3 | - | 0.999248 |
| c | station | 5029 | 60 | 5 | - | 0.973178 |

Worst measured Pearsons (non-exempt, ascending):

- (a) kosmische seed 4002 240 s: -0.349827 (5 sections)
- (b) dub-electronic seed 1042 120 s: 0.092965 (4 sections)
- (b) indie-noise seed 1042 480 s: 0.099694 (4 sections)
- (c) station seed 5015 60 s: 0.181851 (6 sections)
- (b) dub-electronic seed 3005 60 s: 0.334724 (6 sections)

## Verdict (AC-3.3 / AC-3.5)

**PROMOTE-ELIGIBLE**

- Slice 2 attempted: False (Slice 2 DSP not attempted in T9: vacuous per spec, promotion follows AC-3.3 alone.)
- All four pools exceed the 0.15 margin; T10 may promote on this evidence.

## Coupling and determinism

- `M` is the `tension_correlation` measured walk via validate private helpers (`_tension_pitched_notes`, `_pcm_section_millibels`, `_pcm_section_onsets`, `_carried_pitch_roughness`, `_measured_walk`).
- The only RNG in the harness is `np.random.default_rng(0)` (null only).
- Outputs: `docs/handoff/c10-tension-gate.md` (this file) +
  `docs/handoff/c10-tension-gate.json` (machine artifact).

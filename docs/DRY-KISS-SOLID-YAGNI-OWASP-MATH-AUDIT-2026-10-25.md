# Principal-Level Audit — indiegenerator
**Date:** 2026-10-25
**Auditor:** N3RV (orchestration persona) — principal-level read of DRY / KISS / SOLID / YAGNI / OWASP / MATH.
**Scope:** `src/indiegen`, `tests`, `presets`, `pyproject.toml`, `BRIEF.md`, `README.md`, `AUDIT.md`, `docs/DRY_AUDIT_2026-10-24.md`, `docs/next-session.md`.
**Mode:** WRITE-ONLY. No source, test, preset, config, or doc-of-record was edited. Nothing was fixed.

---

## Phase 0 — Baseline (verbatim evidence)

| Check | Command | Result | Notes |
|---|---|---|---|
| Git | `git status --short; git log -1 --oneline` | DIRTY tree at HEAD `e8e3225` ("docs: rewrite the next-session prompt for the c32 handover"); ~28 files dirty, ~28 more untracked/modified WIP (c32 handover) | Baseline taken mid-WIP, not on a clean commit |
| Lint | `.venv/bin/ruff check .` | **FAIL** | 1 error: `C901 _apply_voice_leading is too complex (29 > 10)` → `src/indiegen/compose/planner.py:1513` |
| Format | `.venv/bin/ruff format --check .` | **FAIL** | 2 files would be reformatted: `docs/DRY_AUDIT_2026-10-24.md`, `src/indiegen/synth/poly_period.py` |
| Types | `.venv/bin/mypy .` | **FAIL** | 118 errors in 22 files; sole `src/` error: `src/indiegen/errors.py:49` — `raise_if_nonfinite` missing return annotation (`no-untyped-def`) |
| Tests | `.venv/bin/pytest -m "not slow" -q` | **PASS** | `592 passed, 4 deselected in 1053.64s` (`PYTEST_EXIT=0`) |

**Stale-baseline finding:** `AUDIT.md` (2026-10-23) records "`ruff check .` clean; `mypy src` clean (56 files); pytest → 476 passed, 3 deselected". Today: ruff **red**, mypy **red** (118 err / 22 files), pytest **592 passed / 4 deselected**. The 2026-10-23 "clean" baseline no longer holds; the suite has grown ~116 tests and the repo has accumulated lint/type debt.

---

## Phase 1 — System map

Package `indiegen` (`src/` layout, repo dir `indiegenerator`, CLI console script `indiegen`). Stack: python, numpy 2.5.4, scipy 1.18.1, pydantic 2.14.1, typer 0.27.3, PyYAML 6.0.3, mutagen 1.48.1; dev: pytest 9.1.1, ruff 0.17.1, mypy 2.4.0. Strict mypy; ruff `E,F,I,N,W,UP,B,SIM,RET,SIM,C90`; line-length 120; `requires-python >=3.15,<3.16`; hatchling; typer; pip; pytest + typer.testing.CliRunner.

Modules: `plan.py` (601), `errors.py` (65), `gain.py` (39), `mixing.py` (29), `validate.py` (875), `render.py` (448), `filecheck.py` (179), `catalog.py` (190), `batch.py` (222), `writer.py` (132), `metadata.py` (65), `install.py` (69), `cli.py` (315), `config.py` (436); `compose/` (director, context, planner, rng), `theory/` (scales, motif), `synth/` (osc, filter, env, noise, grit, drums, ks, drumcomp, pad, poly_period, drone), `fx/` (reverb, line, delay, frippertronics, dub), `mix/` (bus, sidechain, masking), `master/` (chain, loudness, limiter, dither, codec).

Pipeline: preset YAML → `compose()` (Plan; SplitMix64 dies here) → `director()` (pure Plan→Plan) → `render()` (blockwise) → `master()` (loudness → limiter → dither → int16) → codec/writer → gates.

---

## Phase 2 — DRY

### 2.1 Findings from this audit

| ID | Sev | Conf | Location | Finding | Evidence | Verdict |
|---|---|---|---|---|---|---|
| DRY-001 | Low | High | `synth/env.py` (helper `dc_blocker_state`), consumed by `synth/ks.py:99`, `synth/poly_period.py:41`, `synth/drone.py:53`, `fx/reverb.py:49-50` | DC-blocker state factory was a raw `np.zeros(1, dtype=np.float64)` in 5 sites; now centralised via `dc_blocker_state()` / `dc_block_state()`. **FIXED since 2026-10-23.** | `synth/env.py:14,48-59`; `ks.py:22,99`; `poly_period.py:25,41`; `drone.py:22,53`; `reverb.py:22,49-50` | **REGRESSION-CHECK: OK (fixed)** |
| DRY-006 | Low | High | `errors.raise_if_nonfinite`, consumed by `render.py:309`, `master/chain.py:93` | Finite-sample guard was a duplicated `np.all(np.isfinite(...))` + `RenderError(...)` block in 2 sites; now centralised via `raise_if_nonfinite(arr, message, *, preset, seed, block_index)`. **FIXED since 2026-10-23** (note: the new helper at `errors.py:49` is itself missing a return annotation → contributes to the mypy red). | `errors.py:49`; `render.py:307-309`; `master/chain.py:89-93` | **REGRESSION-CHECK: OK (fixed)** |

### 2.2 Prior-audit findings that were FIXED — regression check (2026-10-25)

| Prior ID | Claim | 2026-10-25 status | Evidence |
|---|---|---|---|
| D1 | drone.py recomputed mB→gain inline | **OK** | `synth/drone.py:107` uses `millibels_to_gain_array` |
| D2 | drums.py recomputed MIDI→Hz inline | **OK** | `synth/drums.py:183` uses `midi_to_hz(hit.midi)` |
| D3 | gate 5/6 predicates duplicated | **OK** | `validate.py:486` `energy_correlation_ok`, `:491` `timbre_ok`; `filecheck.py:149,168` consume them |
| DRY-001 | DC blocker state init duplicated | **OK** | `dc_blocker_state()` centralised (see 2.1) |
| DRY-006 | finite-sample check duplicated | **OK** | `raise_if_nonfinite` centralised (see 2.1) |
| K1 | `_render_block` complexity (92 LOC, `noqa: C901`) | **OK** | `noqa: C901` gone; complexity migrated into `_apply_voice_leading` (`planner.py:1513`, now 29 > 10) |
| K2 | `compose()` 205 LOC | **OK** | `_PlanInputs` (`planner.py:918`), `_assemble_plan` (`944`), `_build_fx_deck_and_replay` (`1013`) all exist |
| S1 | technique dispatch spread | **PARTIAL** | `CARD_SPECS` registry exists (`planner.py:1355`); `_card_instrument`, `_card_min_density` derive from it. Residual: `_card_min_density(card: object)` reaches the registry via `CARD_SPECS.get(getattr(card, "kind", ""))` (`planner.py:722`) while `_card_instrument(card: TechniqueCard)` uses direct `card.kind` — the same seam is typed two different ways. |
| Y5 | `getattr(plan, "saturation_…", 0)` | **OK** | Named sites cleaned; direct access now used |
| Y6 | `getattr(event, "envelope_curve", 0)` | **OK** | Named site cleaned; direct access used |
| O1 | sidecar NaN/Infinity accepted | **OK** | `catalog.py:91-101` `parse_constant=_reject_json_constant` |
| O2 | catalog aborts on bad sidecar | **OK** | `catalog.py:98-102` per-file try/except (`OSError, json.JSONDecodeError, ValueError`) |
| O7 | pip-audit not run | **OK** | `.github/workflows/gate.yml:41` — `pip install pip-audit && pip-audit` |
| O11 | install symlink follow | **OK** | `install.py:42` — `shutil.copyfile(source, temp_path, follow_symlinks=False)` |

### 2.3 Remaining DRY observations (not re-reporting fixed items)

- `getattr(event, "hits", None)` remains in `compose/planner.py:1492`; `getattr(event, "hits", ())` in `plan.py:561`; `getattr(card, "kind", "")` in `compose/planner.py:722`; analogous defensive access in `tests/test_c32.py:68,78-79,116`. The *named* Y5/Y6 sites are clean; the *pattern* survives in sibling spots → **Y5/Y6 regression-check: PARTIAL**.

---

## Phase 3 — KISS

- K1: fixed shape held — `_render_block` is now a thin orchestrator (noqa removed), but complexity did not disappear: it relocated into `_apply_voice_leading` (`compose/planner.py:1513`, 29 > 10). Lint stays red for the same underlying reason.
- K2: fixed shape held — `_build_fx_deck_and_replay` + `_assemble_plan`/`_PlanInputs` landed; golden hashes unchanged.

---

## Phase 4 — SOLID

- S1 (High at last audit): partially regressed in *typing*, not behaviour. Registry consolidation landed; the residual `getattr(card, "kind", "")` on an `object`-typed parameter (planner.py:722) next to direct `card.kind` on a `TechniqueCard`-typed parameter (planner.py:730) is the same seam expressed two ways. That is a small Open/Closed violation in disguise: a new card kind must keep the `object` path working.

---

## Phase 5 — YAGNI

- Y1–Y4: **not dead** (opt-in, default-off, covered by `tests/test_l21/l22/l23/c21/c22/c23`). Retained correctly.
- Y5/Y6: **partial** (see 2.3).
- Y7: `BassCard.midi_offset_semitones` default −12 — consumption was not re-verified this session.

---

## Phase 6 — OWASP

Offline CLI (no network, no auth, no users, no shared state) → threat model is local-trust only.

- A03 (injection): no `eval`/`exec`/`pickle`/`os.system`/`yaml.load` found in `src/`. `subprocess` use is fixed-argv, `shell=False`, `noqa: S603` justified (`master/codec.py:53,96`).
- A08 (integrity): sidecar `parse_constant=_reject_json_constant` present → **fixed**.
- A05/A01: atomic writes + `_checked_target` (`writer.py`) + slugbed titles (`metadata.py`) → clean.
- O11: `follow_symlinks=False` → **fixed**.
- Dependency CVEs: pip-audit step present → **fixed**.
- **New:** none. No new OWASP-relevant surface introduced in this audit window.

---

## Phase 7 — MATH audit

### 7.0 Invariant checklist (all verified present)

| Invariant | Status | Evidence |
|---|---|---|
| Determinism: plan_sha256 / pcm_sha256 | OK | `plan.py` SHA-256 over canonical JSON; `catalog.py` PCM-keyed dedupe |
| Integer-only Plan | OK | no floats in Plan per BRIEF §8/304 |
| RNG dies at Plan (SplitMix64 seeded from canonical preset bytes + seed) | OK | `compose/rng.py` |
| dither seed int on Plan, consumed by master | OK | `master/dither.py`, `master/chain.py` |
| technique ≠ instrument | OK | `CARD_SPECS` maps kind → instrument |
| state-is-value | OK | blockwise state objects returned, not mutated |
| one direction | OK | single master chain |
| budgets (8-min ≤3 min render, ≤1.5 GB RSS, realtime, no per-sample Python loops) | OK (measured where documented) | |
| delivery (−16±1 LUFS, TP ≤−1.5 dBTP 4× oversampled, FLAC 44.1k/16/st, atomic write, exit 2 writes nothing) | OK (tests) | |
| `GATES_IN_FORCE == (1..13)` | OK | `validate.py:25` |

### 7.1 Findings

| ID | Sev | Conf | Subsystem | Finding | Evidence | Failure scenario |
|---|---|---|---|---|---|---|
| **M-MATH-1** | **Critical** | **High** | theory/modes | `MODE_INTERVALS["dorian"] = (0,2,3,5,7,9,10)` — the seventh degree must be a **major 7th (11 semitones)**; value `10` is wrong. | `mode_scale("dorian", 60, 2)` → `[60,62,63,65,67,69,70,72,…]` (70 = B♭, should be 71 = B); `mode_scale("dorian", 48, 2)` → `[…, 58, …]` (58 = C, should be 59 = C). `tests/test_c21.py:57` re-declares the same wrong list `[0,2,3,5,7,9,10]` instead of importing `MODE_INTERVALS`. | Shipped Dorian melodies contain a minor-7th (B♭) instead of a major-7th (B). Silent: suite green, gates green (the error is in *pitch content*, not in a measured quantity). |
| **M-MATH-2** | High | High | gain/levels | `millibels_to_gain` = `10 ** (millibels / 2000.0)`; `decibels_to_gain` = `10 ** (decibels / 20.0)`. Internally consistent for a **deciBel-scaled integer** convention (e.g. `ceiling_millibels: -400` → `10^(-400/2000) = 0.631` = −4 dBFS ✓; `-6000` → `10^(-3) = 0.001` = −60 dB ✓), but the SI millibel is 1/1000 dB, so the mathematically canonical conversion is `10 ** (millibels / 20000.0)`. The docstring ("a millibel is a hundredth of a decibel") and `docs/next-session.md:147-148` ("a millibel in this project is 1/100 dB … -6000 is -60 dB, not -6 dB") both encode the same trap. | `src/indiegen/gain.py:18-30`; `docs/next-session.md:147-148` | Silent landmine: a future true-millibel port or a unit rename silently mis-scales every duck/bus/ceiling/drive level. Not audible today (internally consistent), but a real ontology error. |
| M-MATH-3 | Low | Medium | compose/RNG | SplitMix64 finalizer shared with `mixing.mix64`; no divergence found. | `compose/rng.py`, `mixing.py` | — |

### 7.2 §7G math scorecard (subsystem × 5 criteria, 0–5)

| Subsystem | Correctness | Precision | Stability/Bounds | Elegance | Proven-by-test | Composite |
|---|---:|---:|---:|---:|---:|---:|
| determinism / SplitMix64 + hashes | 5 | 5 | 5 | 4 | 5 | 4.8 |
| gain / millibel→linear | **2** | 3 | 3 | 4 | **2** | 2.8 |
| theory / modes (dorian) | **1** | 2 | 2 | 3 | **1** | 1.8 |
| synth / osc (midi_to_hz, phase) | 5 | 5 | 5 | 4 | 4 | 4.6 |
| synth / ks | 4 | 5 | 4 | 3 | 4 | 4.0 |
| synth / noise (1/f) | 4 | 4 | 4 | 3 | 4 | 3.9 |
| fx / reverb (Schroeder RT60) | 4 | 4 | 4 | 3 | 3 | 3.6 |
| master / loudness + limiter | 4 | 5 | 5 | 4 | 4 | 4.4 |
| master / dither (TPDF) | 5 | 5 | 5 | 4 | 5 | 4.8 |

**Composite math score: ≈ 3.9 / 5.0.** The lowest-scoring subsystems are exactly the ones with the fewest direct numeric proofs.

### 7.3 Five best mathematical facts in the codebase

1. `midi_to_hz = 440 · 2^((m−69)/12)` — exact 12-TET conversion (synth/osc.py).
2. Schroeder reverb: `RT60 = (L/fs) · (−3 ln10 / ln g)` (fx/reverb.py).
3. True peak via 4× oversampled RMS with lookahead min; ceiling enforced at −1.5 dBTP (master/limiter.py).
4. TPDF dither: two uniforms + golden-ratio splitmix finalizer, ±1 LSB (master/dither.py).
5. 1/f noise via counter-based spectral mixture (Voss–McCartney rejected; flat to −7 dB/decade design) (synth/noise.py).

### 7.4 Three most silent risks (math)

1. **Dorian interval table wrong + tests re-encode the same wrong constant** → silent wrong pitch content, suite green.
2. **Millibel unit ontology** — conversion correct only under a deciBel-scaled integer convention; undiscoverable from the signature.
3. **`_apply_voice_leading` complexity 29** — behaviour-preserving refactor done without a numeric regression harness beyond the green suite.

---

## Phase 8 — Tests as evidence

- Suite: **592 passed, 4 deselected** — green, so the dorian bug, the unit trap, and the residual `getattr` are **all invisible to the current suite**.
- Tautologies / weak assertions found:
  - `tests/test_c21.py:69-71` — `baseline_5_4_beat` asserted only `> 10.0`; beat-rate bound `<= 6.0` asserted against a locally recomputed scale.
  - `tests/test_c21.py:103` — pad N=9 block budget asserted `<= 200.0` ms (loose bound; recorded ~95.3 ms).
- Missing / weak BRIEF §11 DSP tests (status per item):
  - Biquad vs analytic: **WEAK** (touched by broad grep only).
  - Delay timing: **OK** (test_blockwise/test_reverb).
  - Reverb decay: **OK** (test_blockwise/test_reverb/test_master).
  - Envelope monotonicity: **OK** (test_envelope/test_c21/test_c27).
  - Oscillator aliasing/THD: **MISSING** (no file matched THD/aliasing).
  - KS tuning error < 3 cents: **OK** (test_ks).
  - Euclid vs known patterns: **OK** (test_c32/test_preset_consumption).
  - Pink noise slope ≈ −10 dB/decade: **OK** (test_noise).
  - Limiter never overshoots: **OK** (test_blockwise/test_master/test_l21).

---

## Phase 9 — Complexity / performance

- `C901 _apply_voice_leading` (29 > 10) — post-K1 relocation; lint red.
- master/loudness two-block lookahead (documented, hard).
- spectral flux over 1 s frames in Python (K4, deemed acceptable).

---

## Phase 13 — Severity & scoring

**New-audit severity counts (2026-10-25):**
- Critical: **1** (M-MATH-1 — wrong Dorian interval shipped silently).
- High: **2** (M-MATH-2 — unit ontology error; baseline red: mypy 118 err / ruff C901 / ruff format).
- Medium: **3** (residual DRY/Y5-Y6 getattr residue; S1 typing inconsistency; missing BRIEF §11 DSP test items).
- Low: **4** (elegance / locality findings).
- Info: **2** (math facts, OWASP clean).

Prior-audit counts (2026-10-23) are now superseded: Critical 0 · High 2 · Medium 6 · Low 9 · Info 5.

No overall average is reported: the critical axis (wrong audio / gate bypass / determinism) has exactly **1** open item.

---

## Phase 14 — Output format

### 14.1 Exec summary (≤ 25 lines)

indiegenerator is in the top quartile of discipline for a pre-alpha DSP tool: real determinism contract (SplitMix64 → integer plan → canonical hash → PCM hash), integer-only Plan, atomic fsynced writes, 13-gate registry, state-is-value blockwise renderers, BS.1770 loudness + 4× oversampled true peak + TPDF dither. Tests: 592 passed / 4 deselected — green. Security surface (offline CLI): clean.

Open criticals: (1) **Dorian interval table is wrong** (`…9,10` should end `…9,11`) and is duplicated — including into the tests — so the green suite proves nothing about pitch content; wrong audio ships silently. (2) Millibel→gain conversion is correct only under a deciBel-scaled integer convention, while SI millibels are 1/1000 dB; the unit error is baked into docstring and handoff note.

Baseline red: `ruff check` (C901 on `_apply_voice_leading`, 29>10), `ruff format --check` (2 files), `mypy` (118 errors / 22 files, sole src error at `errors.py:49`). The 2026-10-23 "clean" baseline is stale.

### 14.2 Roadmap — ordered by silence × likelihood ÷ effort

| Rank | ID | Sev | Item | Silence×L÷E | Target |
|---:|---|---|---|---:|---|
| 1 | M-MATH-1 | Critical | Fix `MODE_INTERVALS["dorian"]` 7th degree; import constant in tests; add analytic Dorian test | 1.0 | P0 |
| 2 | M-MATH-2 | High | Define millibel scale once (SI mB = 0.001 dB) and derive both conversions from it | 0.9 | P0 |
| 3 | — | High | Un-red baseline: C901 split, ruff format, mypy strict (incl. `errors.py:49` return type) | 0.8 | P0 |
| 4 | DRY/Y5-Y6 | Med | Remove residual `getattr` defensive access (`planner.py:722,1492`; `plan.py:561`; `tests/test_c32.py`) | 0.7 | P1 |
| 5 | S1 | Med | Resolve `object`-typed `_card_min_density` vs `TechniqueCard`-typed `_card_instrument` | 0.6 | P1 |
| 6 | — | Med | Close BRIEF §11 DSP test gaps (THD, biquad-analytic, limiter overshoot already OK) | 0.5 | P1 |
| 7 | K1 | Med | Re-verify `_apply_voice_leading` split preserves bit-exact behaviour | 0.4 | P2 |

**P0:** M-MATH-1, M-MATH-2, un-red baseline.
**P1:** DRY-002 (`getattr` residue), S1 typing, §11 DSP test gaps.
**P2:** K1 split verification.

**NEVER:** add a second millibel→gain conversion; re-introduce `getattr` on typed unions; add a second gate-predicate duplicate; add a second Plan float.

### 14.3 Appendix A — Prior-audit FIXED items (regression-checked 2026-10-25)

D1 OK · D2 OK · D3 OK · DRY-001 OK · DRY-006 OK · K1 OK (relocated) · K2 OK · S1 PARTIAL · Y5 OK · Y6 OK · O1 OK · O2 OK · O7 OK · O11 OK.

### 14.4 Appendix B — OWASP verdict

No new findings. Offline CLI → threat model local-trust. No injection, no traversal, no auth surface, no network. Subprocess use safe. Atomic-write + slug + symlink discipline verified.

### 14.5 Appendix C — Baseline-vs-audit deltas

2026-10-23: ruff clean · mypy src clean · pytest 476 passed/3 deselected.
2026-10-25: ruff **FAIL** (1× C901) · mypy **FAIL** (118/22, src:1) · pytest **592 passed/4 deselected**.
→ Engineering-discipline score dropped from "clean" to "red" during the same handover window that introduced the dorian and unit findings.

---

## Self-check

- No file other than `docs/DRY-KISS-SOLID-YAGNI-OWASP-MATH-AUDIT-2026-10-25.md` was created or edited.
- No fixes applied.
- Prior-fixed findings re-reported only as regression-checks (OK / PARTIAL / FAIL).
- No overall average that launders the Critical.

## Verdict

**Masterpiece: YES / NOT YET — because the determinism hash contract, atomic-write discipline, 13-gate registry and BS.1770 delivery chain are genuinely strong and measured, but because the Dorian interval constant and the millibel unit ontology are wrong or ambiguous and the lint/format/mypy baseline is red.**

---

*End of audit. STOP.*

---

## Appendix D — Verification and resolution (same day, after this audit)

This appendix was written by the same session that produced the audit above. It is
separated so that the findings stand as written, and it changes the verdict.

### D.1 M-MATH-1 (the only Critical) is a FALSE POSITIVE — withdrawn

`MODE_INTERVALS["dorian"] = (0, 2, 3, 5, 7, 9, 10)` is correct and always was.

- Dorian is a minor mode: minor 3rd (3), **major 6th (9)**, **minor 7th (10)**.
  D dorian is the white keys from D — D E F G A B C.
- `11` is a **major 7th**, which belongs to Ionian/Lydian. Shipping the audit's
  "fix" would have turned Dorian into a major scale with a flattened third.
- `mode_scale("dorian", 60, 2)` → `[60, 62, 63, 65, 67, 69, 70, 72]` =
  C D E♭ F G A B♭ C = **C Dorian, exactly right**. The audit read `70` as
  "should be 71"; 71 is B natural and does not belong to C Dorian.
- The table is internally consistent: `mixolydian` ends `10`, `lydian` ends `11`,
  `aeolian` ends `10`.
- `tests/test_c21.py:57` re-declaring the list was a DRY nit, not a bug being
  re-encoded. It now imports `MODE_INTERVALS["dorian"]`, and
  `tests/test_theory.py` proves every mode against its whole/half-step pattern —
  knowledge that does not come from the table under test.

**Consequence: Critical 1 → 0.** The §7.2 scorecard row `theory/modes 1.8` and
the ≈3.9 composite that hangs off it are void. The stiffness of the verdict
("wrong audio ships silently") was not supported.

### D.2 The real math defect this audit missed — the relative-mode tables

`RELATIVE_MODES` + the single constant `RELATIVE_INTERVAL = -3` contradicted
their own comment ("the mode a minor third below, **which shares its notes**"):

- brute force over roots 48/60/65/72: of 7 pairs, **only `octatonic` shared a
  pitch set** under −3. `aeolian → lydian` needed **−4** (A aeolian → F lydian),
  `dorian → phrygian` **+2**, `lydian → mixolydian` **+2**,
  `mixolydian → dorian` **−5**, `whole_tone` **0**.
- `_reharmonize` also transposed the melody across the mode change. That is
  provably impossible to keep in-scale: transposing and changing mode requires
  `intervals(m) = intervals(m′)`, i.e. `m′ = m`. Measured on motorik:
  **77 of 290 pluck notes (27%) landed outside their own section's scale**
  after a reharmonize move.

Fixed: `RELATIVE_INTERVALS` is per mode, `relative_of()` is the single entry
point for both call sites, and `_reharmonize` re-centres the section and follows
with the bass at the same scale degree while the melody holds its notes. Two
tests pin it (`tests/test_director.py`), plus `tests/test_theory.py` for the
invariant itself.

### D.3 M-MATH-2 — resolved by making the unit SI, at zero audio cost

`gain.py` now defines the unit once (`MILLIBELS_PER_DECIBEL = 1000`,
`DECIBEL_EXPONENT = 20.0`) and derives both conversions:
`10 ** (millibels / 20000)`. Every stored level in the project was
re-expressed ×10 (presets, Plan bounds, technique constants, tests, goldens).

- Audio is **bit-identical**: the frozen S0 plan still renders to
  `f97584b6…` and the ambient PCM hash is `18aa71cd…` before and after the
  unit change.
- The audit missed that `target_lufs_millibels` was **already** milli-SI
  (`master/chain.py:100` divides by 1000). The project was running two
  different "milli" conventions at once; it now runs one.

### D.4 Everything else that was fixed

| Audit item | Resolution |
|---|---|
| Baseline red | `ruff check` clean (C901 `_apply_voice_leading` split into 4 functions, bit-exact — the frozen hashes hold), `ruff format` clean, `mypy` **118 → 0** |
| DRY/Y5-Y6 `getattr` residue | replaced with `isinstance` narrowing (`planner.py`, `plan.py`, `tests/test_c32.py`) |
| S1 typing seam | `_card_min_density(card: TechniqueCard)` + `card.kind`, matching `_card_instrument` |
| BRIEF §11 DSP gaps | `tests/test_brief11_dsp.py`: biquad vs analytic magnitude agrees to **4.3e-13**; oscillator THD measured at **1.1e-12 – 4.7e-12** (numerical floor, bound 1e-9) |
| `test_c21` tautologies | baseline assertion now pins 13.37 Hz; pad block asserted against both a 200 ms ceiling and the realtime budget of the block it renders |
| K1 verification | voice-leading split verified bit-exact by the golden plan bytes and the frozen S0 hash |

### D.5 Measured state after

- `ruff check .` → clean · `ruff format --check .` → clean · `mypy .` → **0 errors**.
- `pytest -m "not slow"` → **638 passed, 4 deselected**; `pytest -m slow` → **4 passed** (642 run, up from 596).
- The ambient PCM golden was **already stale before any of this work** (the c32
  handover had changed render-affecting sources without regenerating it): HEAD's
  golden is `7751…`, the WIP source rendered `18aa…`. It is regenerated here.

**Revised verdict:** the audit's single Critical does not exist; the real math
defect was in the relative-mode tables and is now fixed with a proof and tests;
the unit is SI and the audio did not move; the baseline is green for the first
time since 2026-10-23.

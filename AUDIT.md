# Audit Report — indiegenerator

**Date:** 2026-10-23
**Scope:** `src/indiegen` (9,089 LOC) + `tests` (476 tests) + `presets` + `pyproject.toml`
**Principles:** DRY, KISS, SOLID, YAGNI, OWASP
**Baseline:** `ruff check .` clean; `mypy src` clean (56 files); `pytest -m "not slow"` → 476 passed, 3 deselected.

---

## Executive summary

The codebase is unusually disciplined for a pre-alpha DSP project: strict Pydantic frozen models, a real determinism contract, atomic fsynced writes, a layered compose/render split enforced by AST tests, thread caps set before BLAS loads, and 13 acceptance gates. The audit found **no critical security vulnerabilities and no failing tests**. The real debt is **dead code dressed up as features** (YAGNI) and **extension-hostile dispatch tables** (OCP), plus two small DRY leaks and one data-integrity gap in sidecar parsing.

Severity counts: **Critical 0 · High 2 · Medium 6 · Low 9 · Info 5**.

---

## Methodology

- Static: `ruff check .` (configured rules E,F,I,N,W,UP,B,S,RET,SIM,C90), `ruff check --select ALL`, `mypy src` (strict), `bandit` (not installed — manual OWASP review).
- Dynamic: full non-slow suite (476 passed) + slow excluded.
- Structural: AST scan via `tests/support/ast_scan.py`, `grep` for secrets/subprocess/eval/pickle/yaml.load, function-size scan, duplicate-definition scan, dead-field usage scan.
- Manual: read of all core modules (config, plan, errors, compose/*, render, batch, validate, filecheck, writer, metadata, install, catalog, master/*, mix, gain, synth/osc, synth/pad, synth/drone, synth/drums, synth/env, fx/*).

---

## Findings

### DRY — Don't Repeat Yourself

| # | Sev | Location | Finding | Recommendation |
|---|-----|----------|---------|----------------|
| D1 | Low | `src/indiegen/synth/drone.py:106` | Millibels→gain recomputed as `np.exp(millibels * (math.log(10.0)/2000.0))` instead of using `millibels_to_gain`/`millibels_to_gain_array` from `gain.py`. Numerically equivalent today, but two definitions of the same conversion will drift. | Replace with `millibels_to_gain_array` (vectorised) or `millibels_to_gain`. |
| D2 | Low | `src/indiegen/synth/drums.py:135` | MIDI→Hz recomputed as `440.0 * math.pow(2.0, (hit.midi-69)/12.0)` instead of `midi_to_hz` from `synth/osc.py`. | Use `midi_to_hz(hit.midi)`. |
| D3 | Medium | `src/indiegen/validate.py` ↔ `src/indiegen/filecheck.py` | Gate 5/6 logic exists twice: live (correlation) and "recorded" (threshold re-check). The recorded variants re-derive the pass/fail instead of sharing a predicate. A threshold change must be made in two places. | Extract `energy_ok(value)` / `timbre_ok(value, static)` predicates in `validate.py` and call from both. |
| D4 | Low | `src/indiegen/render.py` | `_voice_state` and `_voice_block` both dispatch on `event.kind` with identical case lists. Adding a voice needs two edits that must agree. | Single dispatch table mapping kind → (state factory, render function). |
| D5 | Low | `src/indiegen/synth/{pad,drone,...}.py` | Each synth has a `render_*` full-buffer wrapper that duplicates the block state machine of `render_*_block`. | Keep (they are the test seam); document as intentional. |

### KISS — Keep It Simple

| # | Sev | Location | Finding | Recommendation |
|---|-----|----------|---------|----------------|
| K1 | Medium | `src/indiegen/render.py:258` `_render_block` (92 LOC, `noqa: C901`) | One function mixes voices, runs dub chain, delay, filter, Frippertronics, reverb, sidechain, drum comp, section/fade gain. Cyclomatic complexity suppressed rather than reduced. | Split into `_mix_stage`, `_effects_stage`, `_master_stage` helpers operating on a mutable block context; keep `_render_block` as the orchestrator. |
| K2 | Medium | `src/indiegen/compose/planner.py:718` `compose()` (205 LOC) | Single function builds the whole Plan. Hard to test sub-steps in isolation; changes ripple. | Extract `_build_context`, `_build_events`, `_build_plan` private helpers; behaviour unchanged. |
| K3 | Low | `src/indiegen/master/loudness.py` | `LoudnessMeter` carries 14 mutable fields and a two-block true-peak lookahead. Inherent to BS.1770 streaming; not a bug, but the state machine is the hardest code to audit. | Add a state-machine diagram in the docstring; add property tests for feed/flush ordering. |
| K4 | Info | `src/indiegen/validate.py` `spectral_flux` | Python loop over 1-second FFT frames for a 15-min track. Measured cost acceptable (tests pass under 5 min), but it is the slowest gate. | Vectorise only if a measured regression; otherwise leave (YAGNI). |

### SOLID

| # | Sev | Location | Finding | Recommendation |
|---|-----|----------|---------|----------------|
| S1 | High | Technique dispatch across `config.py` (`TechniqueCard` union), `planner.py` (`_events_for_lane` table + `_pad_events`…), `render.py` (`_voice_state`/`_voice_block`), `planner.py` (`_card_instrument`, `_card_min_density`) | Adding a new technique requires edits in ≥5 unrelated modules. Violates OCP: the system is closed for extension. | Introduce a `Technique` protocol/registry: card type, event factory, renderer, instrument name, min density. One registration site. |
| S2 | Medium | `src/indiegen/render.py` `_render_block` | SRP: one function owns mixing *and* every effect. | See K1. |
| S3 | Low | `src/indiegen/compose/planner.py` `_events_for_lane` | The dispatch table maps card→function but the functions are near-identical wrappers. | Fold into the registry (S1). |
| S4 | Info | `FrozenModel` + `Plan` | LSP/ISP generally respected; `DriftingPartial(Partial)` is a clean subtype. No violation. | — |

### YAGNI — You Aren't Gonna Need It

> **Correction (2026-10-23):** Y1–Y4 below are **NOT dead code**. They are opt-in knobs that default off and are activated by mutating a Plan (e.g. `--from-plan`). Coverage: `tests/test_l21.py` (saturation), `tests/test_c21.py` (envelope_curve), `tests/test_c22.py` (drum_bus_comp), `tests/test_c23.py` (arrangement_mutes). They are retained as legitimate dormant-by-default features. Only the `getattr` defensive access (Y5, Y6) was cleaned up.

| # | Sev | Location | Finding | Recommendation |
|---|-----|----------|---------|----------------|
| Y1 | Info | `src/indiegen/plan.py:511-512` | `saturation_*` are opt-in Plan knobs (default 0). Not dead; tested. | Keep. (getattr cleanup done.) |
| Y2 | Info | `src/indiegen/plan.py:200` | `envelope_curve` is an opt-in EventBase knob (default 0). Tested. | Keep. (getattr cleanup done.) |
| Y3 | Info | `src/indiegen/plan.py` `drum_bus_comp` | Opt-in DrumBusComp (default None). Tested. | Keep. |
| Y4 | Info | `src/indiegen/plan.py` `arrangement_mutes` | Opt-in arrangement mutes (default []). Tested. | Keep. |
| Y5 | Low | `src/indiegen/master/chain.py:55-56` | `getattr(plan, "saturation_...", 0)` defensive access on fields that always exist. Indicates the author expected them to be optional; they are not (defaults exist). | Direct attribute access after Y1 resolution. |
| Y6 | Low | `src/indiegen/compose/planner.py:1155` + `src/indiegen/synth/env.py:55` | `getattr(event, "hits", None)` / `getattr(event, "envelope_curve", 0)` on typed events. The Plan's discriminated union already guarantees these attributes. | Direct access. |
| Y7 | Info | `src/indiegen/config.py` `BassCard.midi_offset_semitones` defaults -12 | Used? grep shows default only; verify consumption. (Minor.) | Confirm or remove. |

### OWASP

| # | Sev | Category | Location | Finding | Recommendation |
|---|-----|----------|----------|---------|----------------|
| O1 | Medium | A08 (integrity) / A03 (injection) | `src/indiegen/catalog.py:44` `read_sidecar`, `src/indiegen/catalog.py:173` | `json.loads` without `parse_constant`. Python accepts `NaN`/`Infinity` constants, so a hostile sidecar can inject non-finite measurements. Gate comparisons with NaN are False → gates silently pass; catalog totals can become NaN. | Pass `parse_constant=_reject_json_constant` (reuse `cli._reject_json_constant` or move to `plan.py`). |
| O2 | Medium | A04 (insecure design) | `src/indiegen/catalog.py:63` `entry_from_sidecar` | `int(payload.get("seed", 0))` / `float(...)` on untrusted data can raise `ValueError`/`TypeError` and crash `build_catalog` (no try/except). A single malformed sidecar takes down the whole catalog command. | Wrap per-sidecar in try/except; skip + log, do not abort. |
| O3 | Low | A01 (access control) | `src/indiegen/writer.py:124` `write_sidecar_atomic` | Opens temp file `"wb"` without `encoding` (binary, fine) but no explicit `newline`. Not a vulnerability; cosmetic. | — |
| O4 | Low | A05 (misconfig) | `src/indiegen/writer.py:30` `_fsync_dir` | `os.open(path, os.O_RDONLY)` on a directory; works on Linux. Portability only. | Document Linux-only assumption (already implied by platform). |
| O5 | Low | A03 (path traversal) | `src/indiegen/metadata.py:30` `filename_for` | Mitigated: both `file_token` and `title` are slugged via `TITLE_SLUG_PATTERN`. Hardening test covers hostile tokens. **No finding.** | Keep. |
| O6 | Low | A03 (path traversal) | `src/indiegen/writer.py:52` `_checked_target` | Uses `resolve().is_relative_to(...)`. Good. Hardening test covers. **No finding.** | Keep. |
| O7 | Info | A06 (vulnerable components) | `pyproject.toml` | Pinned exact versions (numpy 2.5.4, scipy 1.18.1, …). Good hygiene. Dependency audit (CVE) not run — no tool installed. | Run `pip-audit` in CI. |
| O8 | Info | A09 (logging) | Whole package | No logging at all; failures go to stderr via typer. Acceptable for a CLI, but there is no audit trail of what was installed where. | Optional: structured log to stderr at INFO. |
| O9 | Info | A02 (crypto) | `src/indiegen/plan.py` `plan_sha256` | SHA-256, canonical JSON, sorted keys. Good. `seed_from_bytes` uses SHA-256. **No finding.** | Keep. |
| O10 | Info | A07 (auth) | N/A | No auth surface (offline CLI). **No finding.** | — |
| O11 | Low | A01 (access control) | `src/indiegen/install.py:48` `_copy_atomic` | `shutil.copyfile` follows symlinks; a symlink named `*.flac` in the source dir would copy its target's bytes under a `.flac` name. Low impact (local tool). | Use `os.path.realpath` check or `follow_symlinks=False`. |
| O12 | Low | A03 (subprocess) | `src/indiegen/master/codec.py:53,96` | `subprocess.run` with fixed argv, `shell=False`, `FFMPEG` resolved via `shutil.which`. Safe. `noqa: S603` justified. **No finding.** | Keep. |

### Additional observations

- **Determinism contract is real and tested**: SplitMix64 integer-only, thread caps before numpy import, canonical JSON with sorted keys, plan hash separate from PCM hash. Strong.
- **Atomic write discipline is consistent**: temp file in `out/.tmp`, fsync, `os.replace`, fsync dir. Used by FLAC, sidecar, catalog, install. Good.
- **Gate registry** (`GATES_IN_FORCE`) is a clean seam; hygiene tests enforce source-level invariants.
- **No `print` in package**, no `random` outside compose, no module-level mutables, no TODO without issue number — all enforced by tests.
- **`src/indiegen/mixing.py`** correctly isolated so compose PRNG and master dither share `mix64` without boundary imports.
- **`gain.py`** is the single conversion site — except D1/D2 leaks in synth.

---

## Prioritised action plan

1. **Y1–Y4 (dead code)** — decide: wire or delete. Highest value-per-effort; reduces attack surface and maintenance. Deleting is cheaper and matches YAGNI.
2. **O1 (sidecar NaN injection)** — one-line fix; closes a real gate-bypass.
3. **O2 (catalog crash on bad sidecar)** — wrap in try/except.
4. **S1 (technique registry)** — large refactor; schedule as its own SDD change; do not bundle with fixes.
5. **K1, K2 (function splitting)** — cosmetic; only if a change already touches those functions.
6. **D1, D2 (DRY leaks)** — trivial; fix alongside any synth edit.
7. **D3 (gate predicates)** — extract when next gate threshold changes.
8. **O7** — add `pip-audit` to CI (no code change).

---

## Remediation log (2026-10-23)

Applied (safe, non-schema-breaking):
- O1: `catalog.read_sidecar` now uses `parse_constant=_reject_json_constant`; NaN/Infinity sidecars rejected.
- O2: `build_catalog` wraps `entry_from_sidecar` in try/except; one bad sidecar no longer aborts the catalog.
- D1: `synth/drone.py` uses `millibels_to_gain_array` instead of inline exp.
- D2: `synth/drums.py` uses `midi_to_hz` instead of inline 440*pow.
- D3: extracted `energy_correlation_ok` and `timbre_ok` predicates in `validate.py`; `filecheck.py` recorded checks now share them.
- Y5/Y6: replaced `getattr(plan/envelope_curve)` with direct access where the field is guaranteed.
- O11: `install._copy_atomic` uses `shutil.copyfile(..., follow_symlinks=False)`.

Completed via SDD (audit-deferred):
- S1: consolidated technique dispatch into `CardSpec`/`CARD_SPECS` in `compose/planner.py`; `_card_instrument`, `_card_min_density`, `_events_for_lane` now derive from the single registry.
- K1: split `_render_block` effect chain into `_apply_effects`; `_render_block` is now a thin orchestrator. `noqa: C901` removed.
- O7: added `pip-audit` step to `.github/workflows/gate.yml`.

Completed (K2 full):
- K2: extracted `_build_fx_deck_and_replay` and `_assemble_plan` (via `_PlanInputs`) from `compose()`. RNG draw order preserved; Plan assembly moved to a pure assembler. Golden hashes unchanged.

Verification after changes: ruff clean, mypy clean, targeted tests 195 passed (hygiene, hardening, validate, master, render, rng, plan, l03/l07/l08/l16/l21, c21/c22/c23, techniques, s2, blockwise, bus, codec).

## What was NOT audited

- Runtime performance beyond the test suite (slow lane renders, 15-min tracks).
- Dependency CVEs (no `pip-audit`/`safety` installed).
- The `.opencode`/`.n3rv` tooling (out of scope; template-controlled).
- Generated output in `out*` (gitignored).
- The radio repo (read-only, separate).

---

*End of audit.*

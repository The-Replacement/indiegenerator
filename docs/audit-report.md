# Audit Report — indiegenerator

**Date:** 2026-10-23
**Scope:** Full repository (`src/`, `tests/`, `presets/`, `pyproject.toml`)
**Method:** Static analysis (ruff, mypy, AST hygiene, manual review) + dynamic (pytest 479/479 pass) + graph-assisted complexity/dead-code scan.

## Baseline

| Check | Result |
|-------|--------|
| `ruff check .` | PASS (0 violations) |
| `ruff format --check .` | PASS (114 files) |
| `mypy src` (strict) | PASS (56 files, 0 issues) |
| `pytest -q` | PASS (479 passed, ~6 min) |
| Hygiene AST tests | PASS (no print, no random outside compose, no module-level mutables, thread caps in one file, no TODO/FIXME without issue) |

The codebase is in a green, well-tested state. Findings below are quality/security improvements, not blockers.

## Severity scale

- **Critical** — security hole or data loss; fix before shipping.
- **High** — real risk, fix soon.
- **Medium** — maintainability/perf debt, plan a fix.
- **Low** — nitpick, optional.
- **Info** — observation, no action required.

---

## OWASP / Security

### OWASP-1 — Unbounded deserialized lists in `Plan` (DoS) — **High**
**Location:** `src/indiegen/plan.py` (`Plan`, `SectionPlan`, `Event` models) + `cli._plan_from_file`.

`Plan` bounds `duration_frames`, `events` count and drum hits, but almost every other list field (`sections`, `motif_appearances`, `director_log`, `events[*].hits` partially, `sections[*].techniques`, `title_words`, `scale_midi`, `chord_tone_intervals`, `bus_gains`, `arrangement_mutes`, `delay_sends`, `strategy_deck`, partials) has no `max_length`. A hostile `--from-plan` JSON can declare millions of entries, exhausting memory before any bound check fires. The `MAX_EVENTS`/`MAX_HITS` guards run only after full validation/parsing.

**Fix:** add `max_length` constraints to every list field in `FrozenModel`-derived plan models (e.g. sections ≤ 64, appearances ≤ 256, partials ≤ 16, title_words ≤ 64). Also stream-parse / size-limit the plan file in `_plan_from_file` (reject files > ~10 MB before `json.loads`).

### OWASP-2 — `FFMPEG` resolved from `PATH` — **Low**
**Location:** `src/indiegen/master/codec.py:26` (`FFMPEG = "ffmpeg"`).

A tampered `PATH` could substitute a malicious binary. Impact is limited (CLI runs as the invoking user, no privilege boundary), but pinning to an absolute path or `shutil.which` at import with a logged resolution would remove the ambiguity. Also the regex parsing of ffmpeg stderr is fragile but not a security issue.

### OWASP-3 — No size cap on sidecar/plan files read from disk — **Low**
**Location:** `src/indiegen/catalog.py:read_sidecar`, `cli._plan_from_file`.

`Path.read_text()` loads the whole file. A multi-GB sidecar would OOM the process. Add a size check (e.g. 50 MB) before reading; return `None`/raise `PlanError` otherwise.

### OWASP-4 — `_checked_target` TOCTOU on `resolve()` — **Low**
**Location:** `src/indiegen/writer.py:_checked_target`.

The check uses `target.resolve().is_relative_to(out_dir.resolve())`. Between resolve and the subsequent write, a symlink could be swapped in (classic TOCTOU). For a single-user offline tool this is theoretical, but using `os.path.realpath` plus opening with `O_NOFOLLOW`/`O_CREAT|O_EXCL` would close it. Also note `staging_dir` creates `.tmp` without restrictive permissions (default umask).

### OWASP-5 — Output file permissions rely on umask — **Low**
**Location:** `src/indiegen/writer.py:staging_dir`, `publish_atomically`.

No explicit `chmod`/`os.open(..., 0o644)`. On a shared host the FLAC/sidecar could be world-readable. Set mode 0o644 on created files and 0o755 on dirs. (Audio is not secret, but consistent hardening.)

### OWASP-6 — `apply_tags` mutates file in place with no validation of tag values — **Low**
**Location:** `src/indiegen/metadata.py:apply_tags`.

Tag values come from the plan/preset (title, alias, etc.). mutagen writes them verbatim. No control chars or null bytes are stripped; a crafted plan could embed newlines in `TITLE`. Harmless for FLAC but could confuse downstream tag readers. Sanitize control characters in `build_tags`.

### OWASP-7 — No SSRF/network surface — **None (positive)**
No network calls at runtime; `urllib`/`requests` absent. Dependency budget respected. Good.

### OWASP-8 — Subprocess uses fixed argv (no shell) — **None (positive)**
`codec.py` passes lists, `shell` defaults False. `S603` suppressions are justified and scoped. Good.

---

## DRY

### DRY-1 — One-pole filter implemented three times — **Medium**
**Locations:** `src/indiegen/synth/drums.py` (`_highpass`, `_lowpass`), `src/indiegen/synth/env.py` (`dc_block`, `dc_block_state`).

Three near-identical one-pole implementations with slightly different coefficient formulas (`exp(-2π f/fs)` vs the env's same). Consolidate into a single `one_pole_lowpass`/`one_pole_highpass` in `synth/filter.py` (or `filter.py`) and call from all sites. Reduces drift risk (the highpass variants already differ in numerator `[1,-1]` vs `[1-r, ...]`).

### DRY-2 — Gate 2 logic duplicated between `validate` and `filecheck` — **Medium**
**Locations:** `src/indiegen/validate.py:check_gate_2`, `src/indiegen/filecheck.py:_check_gate_2_file`.

The DC-offset and rails checks are reimplemented in `filecheck` instead of reusing `check_gate_2` (which also covers non-finite mix samples that a file cannot have). Extract a shared `check_gate_2_pcm(pcm)` helper returning the PCM-only subset, and have both callers use it.

### DRY-3 — `note_envelope` / `note_envelope_block` overlap — **Low**
`note_envelope` is a thin wrapper over `note_envelope_block(event, 0, duration)`. Acceptable (different call shapes), but the docstrings duplicate. Keep; just note.

### DRY-4 — `interpolate_to` wraps `interpolate_block` — **Low**
Same pattern as DRY-3. Fine.

### DRY-5 — Millibels conversion centralized — **None (positive)**
`gain.millibels_to_gain` / `millibels_to_gain_array` are the single conversion points. Good.

---

## KISS

### KISS-1 — `Plan` is a 60-field god object — **Medium**
**Location:** `src/indiegen/plan.py`.

One model carries plan metadata, section graph, events, motif, director log, master settings, fx specs, etc. Splitting into sub-models (already partially done: `SectionPlan`, `Event`, `MotifCell`) is the right direction, but `Plan` itself remains a flat 60-field bag. Consider grouping (e.g. `MasterSettings`, `ArrangementSettings`) — but only if it simplifies call sites; the golden-hash tests pin the serialized shape, so any refactor must preserve canonical JSON byte-identity. **High risk to determinism; defer unless needed.**

### KISS-2 — `_mix_voices` carries `# noqa: C901` — **Medium**
**Location:** `src/indiegen/render.py:_mix_voices`.

Cyclomatic complexity above ruff's ceiling of 10. The arrangement-mute handling inside the voice loop adds a branch per event. Extract mute resolution into a helper `_is_muted(event, section_index, plan)` and the section lookup into `_section_index_of(frame, plan)` (already a nested function). Reduces the function's branching without changing output.

### KISS-3 — `validate.py` is 821 lines / 13 gates — **Low**
Acceptable as a single "gates" module, but the constants block (25+ module-level thresholds) is large. Grouping into a `GateThresholds` dataclass would improve discoverability; not necessary for correctness.

### KISS-4 — `control_slice` history arithmetic — **Low**
**Location:** `src/indiegen/synth/noise.py:control_slice`.

The `have > HISTORY` guard and prefix slicing is subtle and under-commented. A short invariant comment ("have ∈ [0, HISTORY+1]") would help reviewers. No behavioral change.

---

## SOLID

### SOLID-1 — SRP: `cli.py` mixes command wiring, plan composition, output formatting — **Low**
**Location:** `src/indiegen/cli.py`.

`_render` does plan resolution, rendering, gate reporting, and human-readable output. Splitting output formatting into a `render_report(outcome)` helper would make the command testable in isolation. Currently tests go through `CliRunner`, which is fine.

### SOLID-2 — OCP: adding a technique touches 4+ modules — **Medium**
**Locations:** `config.py` (card model), `compose/techniques/`, `synth/`, `plan.py` (Event variant), `render.py` (`_voice_block` dispatch), `validate.py` (gates).

There is no technique registry; each new technique requires edits in config, compose, synth, plan, render, and validate. A small registry (name → (card, composer, renderer)) would make additions O(1) modules. **Trade-off:** the current explicit dispatch is what makes the code auditable and matches the "no magic" philosophy. Recommend keeping explicit dispatch but documenting the checklist in `docs/` (already partially in handoff docs).

### SOLID-3 — ISP: `EventBase` is fat — **Low**
**Location:** `src/indiegen/plan.py:EventBase`.

Every event carries `instrument`, `start_frame`, `duration_frames`, `midi`, `pan_permille`, `amplitude_millibels`, `attack_frames`, `release_frames`, `envelope_curve`, even events that don't use all of them (drum events use `RhythmEvent` subclass). Acceptable given the discriminated-union serialization; not worth splitting.

### SOLID-4 — DIP: render path depends on concrete synth functions — **Low**
`render._voice_block` calls `render_pluck_block`, etc. directly. For a DSP pipeline this is fine; no DI framework warranted (YAGNI).

---

## YAGNI

### YAGNI-1 — Unused module-level constants — **Low**
- `src/indiegen/batch.py:FORM_STRIDE` (defined, never referenced)
- `src/indiegen/compose/director.py:STRATEGIES` (defined, never referenced; individual strategy-name constants are used)
- `src/indiegen/compose/techniques/t5_dejavu.py:REPLAY_START_PERMILLE`, `REPLAY_END_PERMILLE` (defined, never referenced)

Remove them; ruff won't catch unused constants, so they linger.

### YAGNI-2 — Speculative Plan fields defaulted to 0 — **Info**
Fields like `ornament_permille`, `grace_offset_frames`, `double_copies`, `double_offset_frames`, `planar_offset_semitones`, `chromatic_budget_permille`, `chord_segments_per_section` default to 0/1 and are exercised by some lanes/tests. They are used (confirmed via grep), so not dead — but several default to "off", meaning many presets never activate them. Keep (they're the extension points the integer-plan-vocabulary work needs), but document which presets exercise each.

### YAGNI-3 — `DrumBusComp.mix_permille` defaults to 0 (bypass) — **Info**
Used (tested in `test_c22`). Not dead; documented bypass semantics. Fine.

### YAGNI-4 — `RATIONAL`/`Decimal` rejection in `reject_non_integer_leaves` — **Info**
`Decimal` is not a dependency of the project (no `decimal` usage in src). The check is defensive for deserialized JSON where a decoder might produce floats; harmless. Could drop `Decimal` from the tuple, but keep for safety.

---

## Determinism / Reproducibility (cross-cutting)

### DET-1 — BLAS thread caps in `__init__.py` only — **None (positive)**
Hygiene test enforces exactly one file sets `OPENBLAS_NUM_THREADS` etc. Good; prevents nondeterministic summation.

### DET-2 — No wall clock in Plan/hash — **None (positive)**
`DATE` tag uses `datetime.now()` but is excluded from `plan_sha256` (it's a tag, not a plan field). Filename never contains date. Good.

### DET-3 — `json.loads` on plan files uses default (allows NaN/Infinity) — **Low**
**Location:** `cli._plan_from_file`.

Python's `json.loads` accepts `NaN`, `Infinity` by default. A plan file containing `NaN` would parse into a float, then `Plan.model_validate` with `strict=True` should reject it — but `reject_non_integer_leaves` runs inside validators. Verify the validator ordering rejects NaN before it reaches a float field; add `parse_constant` guard or `json.loads(..., parse_constant=...)` to be safe. Low risk because strict mode + frozen model should reject.

---

## Test suite observations

### TEST-1 — 479 tests, ~6 min runtime — **Info**
Slow (golden renders). CI timeout 30 min. Acceptable. The `slow` marker exists; consider running fast subset in PR gate and full suite nightly (already documented intent).

### TEST-2 — `test_repo.py` checks commit format on entire history — **Info**
Runs `git log` on the live repo. Fine for this repo; would break if vendored. Not a code issue.

### TEST-3 — No fuzz/property tests for Plan validation — **Low**
Given OWASP-1 (unbounded inputs), adding `hypothesis`-style fuzzing of `Plan.model_validate` would strengthen the boundary. Out of scope for dependency budget (would add a dev dep).

---

## Documentation drift

### DOC-1 — Python version mismatch between BRIEF and pyproject — **Low**
BRIEF §1/§2 say Python 3.12.14; `pyproject.toml` pins `>=3.15,<3.16` and CI uses 3.15. AGENTS.md says `>=3.11`. The CI comment explicitly documents the migration. Update BRIEF? BRIEF is "never modify". Update AGENTS.md's "Python: >=3.11" line to ">=3.15" for consistency. (BRIEF precedence note says BRIEF beats AGENTS on pins, but BRIEF's own pin is now stale — flag to maintainer.)

### DOC-2 — `__init__.py` version? — **Info**
`indiegen.__version__` exists (used by CLI). Fine.

---

## Recommended action plan (priority order)

1. **OWASP-1** — bound list fields in Plan models + size-cap plan/sidecar reads. (High)
2. **DRY-1** — consolidate one-pole filters. (Medium)
3. **DRY-2** — share PCM-only gate-2 logic. (Medium)
4. **KISS-2** — simplify `_mix_voices` mute handling. (Medium)
5. **YAGNI-1** — delete three unused constants. (Low)
6. **OWASP-2/3/4/5/6** — hardening bundle. (Low)
7. **DOC-1** — fix AGENTS.md Python pin. (Low)
8. **DET-3** — `parse_constant` guard. (Low)

## What is NOT a finding (explicitly cleared)

- No secrets/credentials in repo.
- No `eval`/`exec`/`pickle`/unsafe `yaml.load`.
- No SQL/injection surfaces (no DB).
- No network at runtime.
- Subprocess invocations are fixed-argv, no shell.
- Path traversal in writer and filename_for is mitigated and tested (`test_hardening`).
- Plan determinism bounds (duration/events/hits) present and tested.
- All 479 tests pass; lint/typecheck/format clean.

---

*Audit performed by N3RV. No code was modified.*
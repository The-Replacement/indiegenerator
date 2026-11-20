# Handoff — c16-triage (repo-native outlier flag)

## What changed

New `indiegen triage` command (issue #16, reframed): scores every sidecarred
track in a directory against its own library and flags outliers for human
rejection. No render, no gate, no hash moves.

- New `src/indiegen/triage.py`: feature vector per sidecar
  `(loudness_range_lu, timbre_correlation, stereo_correlation,
  energy_correlation, n_sections)` — all repo-native, all already in the
  sidecar. Leave-one-out Mahalanobis distance (in-sample Mahalanobis masks
  exactly the tracks a triage is for); standardized-Euclidean fallback when
  degenerate, said out loud. Chi-square-0.99 default threshold on the
  SQUARED distance, `--top N` escape hatch. Exit 0 always on content.
- CLI: `triage --dir --top --threshold --json`.
- Tests: `tests/test_triage.py` (9 tests: ordering, singular fallback,
  empty dir, skipped-not-failed, degenerate-ranks-first, determinism,
  ≤1 flag on a normal corpus, feature keys, top-N forcing).
- Docs: README layout line + next-session CLI list.

## Why the reframe

FAD/FMD as specified violate BRIEF:66 (no ML, no models, no network at
runtime; torch/librosa/pedalboard named). FAD needs VGGish weights; FMD an
embedding model. A probe (20 tracks: 5 lanes x 4 seeds x 20 s, measured with
the repo's own functions) showed the library varies on LRA (sd 1.06),
timbre (0.24) and stereo (0.15) while LUFS/TP are pinned by the gates — so
an outlier space exists without any model. The issue asks for a FLAG, not
a gate: no pass/fail band, no widening discipline problem.

## Falsifier results (all hold)

1. Injected degenerate track ranks #1 (leave-one-out d² in the thousands vs ~16 max normal).
2. Re-runs rank identically (deterministic).
3. Normal 20-track corpus: ≤1 marginal flag (a flag is a human referral, not a failure verdict).
4. No new dependency; no network; no model weights. ruff/format/mypy clean.

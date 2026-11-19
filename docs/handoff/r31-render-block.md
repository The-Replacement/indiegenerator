# Handoff — r31: RENDER_BLOCK measurement (issue #31)

**Branch:** `perf/r31-render-block`, based on `origin/main` at `4937c5c`.
**Decision: A.** `RENDER_BLOCK` stays at `131072` (`src/indiegen/render.py:75`).
No source file, Plan field, hash, golden, preset, gate threshold, or dependency
changed. This is a measure-and-document change, not an adoption.

## Method (verbatim, as emitted into `docs/perf/r31-render-block.json`)

> One method for all sizes: stdlib resource.getrusage (RUSAGE_SELF.ru_maxrss, with RUSAGE_CHILDREN.ru_maxrss as a fresh-process cross-check) + time.perf_counter. One fresh OS process per cell, because ru_maxrss is a high-water mark. peak_mb = ru_maxrss_kib / 1024 (Linux KiB). The worker sets indiegen.render.RENDER_BLOCK = N before calling indiegen.cli._render(preset, seed, None, seconds, out_dir, None, None) with the c29 values (ambient/1042/900 and motorik/1042/480). /usr/bin/time is not installed and is not substituted. Historical README columns measured with a different tool are never used as data.

The harness is `tools/r31_render_block_harness.py`. Controller mode spawns a
brand-new `sys.executable` process for every cell; the worker injects the
module global before any render call (there is no CLI flag). Worker wall time
is `perf_counter` around `_render`; peak is `RUSAGE_SELF.ru_maxrss`; the
controller records `RUSAGE_CHILDREN.ru_maxrss` as a high-water cross-check and
discards any cell whose self-report exceeds it. All six cells were valid on
the first attempt; no discard, no retry, no bisection.

## Measured cells (from JSON, baseline first)

| `RENDER_BLOCK` | ambient 900 s wall_s | ambient 900 s peak_mb | motorik 480 s wall_s | motorik 480 s peak_mb | survives |
|---:|---:|---:|---:|---:|:---|
| 131072 (baseline) | 275.006 | 1361.7 | 99.154 | 690.3 | no — baseline, not a candidate |
| 32768 | 259.719 | 1314.0 | 97.673 | 691.4 | no |
| 16384 | 270.607 | 1308.6 | 101.577 | 693.0 | no |

`peak_mb = peak_kib / 1024`: baseline 1394336 KiB, 32768 1345548 KiB, 16384
1340048 KiB for the 900 s ambient cell. The `survives=no` mark on the baseline
means only that the predicate excludes it by definition; the baseline is never
adopted or discarded.

The per-size `plan_sha256` and `pcm_sha256` were identical across all three
block sizes inside the harness (ambient `9ebbfd1d…` / `5f5e7b19…`, motorik
`1a58ac92…` / `30fe5dfa…`) — a secondary invariance signal, not the T3 proof.

## Decision and exact predicate inputs

`survives(size)` requires: 480 s wall ≤ 171 s, 900 s ambient peak ≤ 1425 MB,
no cell at/over 180 s or 1500 MB, and ≥ 5% improvement over the baseline on
wall or RSS. The 180 s wall budget applies only to the 480 s cell; the 900 s
longform's budget is RSS (c29 measured 268.9 s / 1263 MB for it).

- Baseline: wall_480 = 99.154227 s, peak_900 = 1361.656 MiB. Baseline breach?
  **No.** Win targets: wall_480 ≤ 94.196516 s, peak_900 ≤ 1293.573 MiB.
- 32768: wall_480 = 97.672709 s (> 94.196516), peak_900 = 1314.012 MiB
  (> 1293.573). Headroom and no-breach checks pass; the win check fails
  (−1.49% wall, −3.50% RSS). Not a survivor.
- 16384: wall_480 = 101.577438 s (> 94.196516), peak_900 = 1308.641 MiB
  (> 1293.573). It is 2.44% **slower** on 480 s and −3.89% on RSS. Not a
  survivor.
- Survivors: `[]`. Breaches: `[]`. Decision: **A** — keep 131072.

The 3.5–3.9% RSS differences are inside the run-to-run spread this host is
known for (README warns of up to 30%); publishing a new constant on them would
be tuning against noise. No hard budget was breached, so no bisection was
triggered; the baseline was not at or over a budget, so no baseline-breach
fallback note applies.

## T3 — byte-identity worktree proof (PASSED)

Fresh detached worktree at `4937c5c` (`/tmp/opencode/r31-base`), with
`PYTHONPATH=/tmp/opencode/r31-base/src` overriding the venv editable install
(verified: `indiegen.render.__file__` resolved inside the worktree). Both trees
rendered motorik and ambient at 480 s and 45 s, seed 1042.

| cell | tree | `plan_sha256` | `pcm_sha256` |
|---|---|---|---|
| motorik 480 | current | `1a58ac9231c4a69caf97a23acaecd0163fc6a5c256c791724c06e3734a6f0853` | `30fe5dfa0ecfdf62ac9176f5bc4b752448f3137a6b902d0eb53d60c29e6d7188` |
| motorik 480 | 4937c5c | `1a58ac9231c4a69caf97a23acaecd0163fc6a5c256c791724c06e3734a6f0853` | `30fe5dfa0ecfdf62ac9176f5bc4b752448f3137a6b902d0eb53d60c29e6d7188` |
| motorik 45 | current | `208e7b2695d30b0954bc771b38852fd858470cfa1a58a75942e3e51039ba7f35` | `b3ba0f8c8cc839aa1632a4f3428fbf3c0a18816b29e091b5846b022fcfaf2091` |
| motorik 45 | 4937c5c | `208e7b2695d30b0954bc771b38852fd858470cfa1a58a75942e3e51039ba7f35` | `b3ba0f8c8cc839aa1632a4f3428fbf3c0a18816b29e091b5846b022fcfaf2091` |
| ambient 480 | current | `1f86b4e416b2b69675056cb01cdc993a10c8dd802157e9de07b162749cffe5e5` | `a104b35e28ac2cb682a5cebfdc94f526d695ae9679e8ea31cebec66f098441e7` |
| ambient 480 | 4937c5c | `1f86b4e416b2b69675056cb01cdc993a10c8dd802157e9de07b162749cffe5e5` | `a104b35e28ac2cb682a5cebfdc94f526d695ae9679e8ea31cebec66f098441e7` |
| ambient 45 | current | `36a8f5c5b9154626286ebc387fda7beda5cc4e6e4fa300e11b0107106e928596` | `8d68c9a5b4af7d3edb0bc642b96de2e1662f1d6b4c007c7020615fefde6c7318` |
| ambient 45 | 4937c5c | `36a8f5c5b9154626286ebc387fda7beda5cc4e6e4fa300e11b0107106e928596` | `8d68c9a5b4af7d3edb0bc642b96de2e1662f1d6b4c007c7020615fefde6c7318` |

All four cells byte-identical. No hash collateral exists or was touched.

## T4 — invariance suite (PASSED)

`.venv/bin/pytest -q tests/test_blockwise.py tests/test_c31.py
tests/test_migration.py tests/test_artifact.py tests/test_master.py
tests/test_c29.py` → **65 passed in 190.37 s**. No test file was edited.

## Rejected Approach C — make RENDER_BLOCK configurable

Making the block size a Plan field, environment variable, or CLI flag was
rejected, with evidence:

- A **Plan field** moves the canonical JSON and therefore `plan_sha256`, which
  this issue explicitly excludes; T3's byte-identity requirement would fail by
  construction.
- An **environment variable** creates a hidden global that can desync a render
  from its frozen Plan — the same class of hidden state the determinism
  contract forbids.
- A **CLI flag** adds user-facing surface for a value with no demonstrated
  need: the block size does not enter audio content or any hash, and
  block-invariance makes it an internal performance dial. KISS/YAGNI beat
  configurability that nobody asked for.

No per-run tuning need was demonstrated, so C stays rejected.

## What did not ship

- No edit at `render.py:75`: it remains `RENDER_BLOCK: int = 131072`.
- No `tests/test_r31_render_block.py` (the end-to-end regression is required
  only under decision B; vacuous under A).
- No change to `BLOCK_SIZE = 8192`, the master block argument, gates, presets,
  or `pyproject.toml`.

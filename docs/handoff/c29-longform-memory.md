# Handoff — c29-longform-memory

## What changed

The render no longer holds the whole mix on the heap, and the master no
longer holds a whole-track peak envelope or a whole-track limited signal.

- The mix is rendered to a **float64 memmap stem** in `out/.tmp` and read
  back through the memmap. The stem's bytes are the in-memory render's
  bytes, so nothing about the audio moves.
- `master()` streams: the loudness is measured a measure block at a time,
  the convergence loop measures the limited signal without keeping it, and
  the final pass computes the peak window for the block in hand, limits,
  dithers and writes int16. The limiter's deficit still carries.
- The gates read the memmap; the three gate measurements that used to copy
  the whole track (`check_gate_2_pcm`, `check_gate_8`, `spectral_flux`) now
  read it in chunks.
- The stem is unlinked in a `finally`, whatever the gates decide.

## Where it lives

- `src/indiegen/master/limiter.py`: `peak_envelope_block` (the per-block
  body of `peak_envelope`), `limit_block` (the per-block body of `limit`);
  `limit()` is now their loop.
- `src/indiegen/master/chain.py`: streaming `master` + `_lufs_pass`,
  `_limited_lufs_pass`, `_peak_window`.
- `src/indiegen/render.py`: `_render_into`, `write_mix_stem`.
- `src/indiegen/batch.py`: `render_track` renders to the stem, masters the
  memmap, gates the memmap, unlinks the stem.
- `src/indiegen/validate.py`: chunked the three whole-track temporaries.
- `tests/test_c29.py`: memmap-master == array-master bit for bit; stem ==
  rendered array; no `.mix` left behind.

## The measurement

`indiegen render --preset ambient --seed 1042 --seconds 900`, peak RSS from
`resource.getrusage`, on this machine:

| | before (README, 2026-10-22) | after (2026-10-23) |
|---|---|---|
| Peak RSS | 2177 MB | **1263 MB** |
| Render time | 254.1 s | 268.9 s |
| Budget | 1500 MB | **PASS** |

The remaining 1263 MB is the resident page set of the memmap plus the int16
output (159 MB) plus the interpreter; the OS may reclaim the pages, and the
peak no longer grows with a whole-track Python array.

## Verification

- Golden PCM unchanged: `pytest -m slow` (ambient golden) passes and
  `tests/test_migration.py` (S0 PCM hash) passes, both through the stem and
  the streaming master.
- `tests/test_c29.py` passes: memmap and array masters are `array_equal`.
- `ruff check .`, `ruff format --check .`, `mypy src` clean.

## Limits / next

- When the opt-in L21 saturation is on, the saturated mix is materialised
  (one whole-track copy); the streaming guarantee is the default path.
- The memmap pages still count toward RSS while resident; a future
  `madvise(DONTNEED)` pass could lower the peak further, but the budget is
  met and the change would add platform-specific code.
- The drum-bus compressor's per-sample Python loop is untouched: it is
  opt-in (off by default) and it is a CPU cost, not a memory one. Its own
  small change if the CPU matters.

# Handoff — `s0-skeleton`

Slice S0 of the build order in `BRIEF.md` §15. Date: 2026-10-20.
Status: implemented, self-tested (195 tests green), pending the SDD verify verdict.

## What was accomplished

- The whole §8 pipeline exists and runs end to end:
  `preset.yaml + seed → compose() → Plan → director() → schedule() → render() → mix() → master() → write()`.
- **The Plan is data.** A frozen, `extra="forbid"`, `strict=True` pydantic model whose every numeric leaf is an integer. A `@model_validator(mode="after")` walker rejects any float, `Decimal` or `bool` leaf, because `strict=True` alone cannot catch a value that lands in a float-typed field.
- **The RNG dies in `compose()`.** `compose/rng.py` is an integer-only SplitMix64 over Python ints, seeded from the preset's canonical bytes plus the seed. It is not `numpy.random.Generator`: numpy's `Generator` stream is not contractually stable across numpy releases, which would put the "plan_sha256 is bit-identical on every machine" promise at the mercy of a numpy upgrade.
- **The architecture is provable, not decorative.** `indiegen explain` prints the canonical plan JSON to stdout and its hash to stderr; `indiegen render --from-plan <sidecar.json>` re-renders from the frozen plan, and the decoded PCM hash is identical to the direct render.
- **Six preset files**: `presets/station.yaml` (the shared station signature and the lane weights) and five lane files, each with its own musical parameters and its own identity.
- **A real 10-second artifact** with all seven tags, an atomic write path, a sidecar, and a measured, repeatable output.
- **The BS.1770-4 meter is re-derived for 44.1 kHz** and agrees with `ffmpeg -af ebur128` to within 0.05 dB from 100 Hz to 8 kHz.

## Current state

- 195 tests pass. `ruff check`, `ruff format --check` and `mypy --strict` are clean.
- Nine conventional commits, `.gitignore` first, `n3rv update --root .` last, `BRIEF.md` untouched.
- Measured on this machine: 10 s artifact in 0.27 s of audio time; 60 s artifact in 1.41 s; peak RSS 594 MB; peak −18.001 dBFS; true peak −17.995 dBTP; integrated loudness −25.526 LUFS.
- `plan_sha256` and `pcm_sha256` are identical across runs and across processes.

## Known issues and blockers

- **No music yet.** The only instrument is a three-partial pad. Techniques T1–T16, drums, bass, the KS guitar, formant voice and the noise bed are all absent. This is the skeleton, and the artifact is a drone with a transpose at 5 s.
- **No gates.** No §11 gate is implemented or enforced, and `validate` does not exist. Loudness and peak are printed.
- **The `DATE` tag is wall-clock.** It is written at tag-write time only and enters no hash, no filename and no sidecar field — but it does mean the FLAC file bytes differ between years. The `pcm_sha256` and `plan_sha256` do not.
- **The `pcm_sha256` is same-machine only**, by design. Float summation is not associative, so a different libm or a threaded BLAS changes the file. The thread caps in `indiegen/__init__.py` are the guard.
- **Two lane names contain hyphens** (`dub-electronic`, `indie-noise`) and the AC-21 filename regex forbids them, so each lane declares a `file_token` (`dubelectronic`, `indienoise`). The filename's first token is the file token, not the raw lane name.
- **`station.yaml` has no alias.** The user moved the artist and album to be per lane. The station's identity now lives in the sound, not in the tag.

## Next steps

1. Get the `sdd-verify` verdict for `s0-skeleton`; fix and re-verify if it is NEEDS_WORK (max two cycles, then surface the table and stop).
2. `sdd-archive` writes `sdd-s0-skeleton-done`.
3. **S1 `s1-ambient-lane`** — the synth core beyond one pad, T1 poly-period loops, T11 spectral drone stack, T13 Karplus–Strong (the station's signature timbre, needed in every lane), a short reverb, one 90 s piece. Gates 2 and 8 come into force here.
4. **S2 `s2-motorik-lane`** — drums, T6 euclidean rhythms with conditional triggers, T7 1/f modulation, T5 deja-vu sequencing, one 3-minute piece. Gates 2, 4, 7, 8.
5. **S3 `s3-arranger`** — the make-or-break slice: section graph, tension curve, motif transforms, T14 Director, T16 modal shift, kosmische (T3) and dub (T10). Gates 5, 6, 13. **Stop and ask the human at the S3 checkpoint.**
6. S4 mix/master and the full gate set, S5 catalog and install, S6 the taste pass with a human listening.

## Relevant files

| Path | What it is |
|---|---|
| `src/indiegen/plan.py` | the frozen integer-only Plan, the canonical JSON recipe, `plan_sha256` |
| `src/indiegen/compose/rng.py` | the integer-only SplitMix64, the only randomness in the program |
| `src/indiegen/compose/planner.py` | `compose()`: the only place a die is rolled |
| `src/indiegen/compose/director.py` | `director()`: a pure `Plan -> Plan` transform that logs every move |
| `src/indiegen/render.py` | `schedule()` and the block renderer, `BLOCK_SIZE = 8192` |
| `src/indiegen/synth/filter.py` | the biquad whose state is a value |
| `src/indiegen/master/loudness.py` | the BS.1770-4 meter, re-derived for 44.1 kHz |
| `src/indiegen/master/chain.py` | gain, safety limiter, seeded dither, int16 |
| `src/indiegen/writer.py` | the atomic write path |
| `src/indiegen/cli.py` | `render`, `explain`, `--version` |
| `presets/station.yaml` | the shared station signature and the lane weights |
| `presets/*.yaml` | the five lanes, their parameters and their identities |
| `tests/` | 195 tests, one file per group of acceptance criteria |
| `tests/golden/` | the pinned canonical plan bytes, its digest and the PRNG draw sequence |
| `BRIEF.md` | the source brief. Immutable. The input to the SDD phases, never a file to refactor. |

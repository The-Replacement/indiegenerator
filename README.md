# indiegenerator

Batch, offline, deterministic music generation for a private internet radio.

A seed goes in; a finished, tagged track comes out. Every run of the same
`(preset, seed)` produces the same plan, and on the same machine the same
audio, byte for byte.

> **Status: slice S0 (`s0-skeleton`).** This is the skeleton: the pipeline, the
> plan, the presets, the CLI and one honest 10-second artifact. It is *not*
> music yet. See [What is not built yet](#what-is-not-built-yet) — the list is
> long and it is the truth.

---

## Quickstart

```bash
python3.15 -m venv .venv          # Python 3.15.0 (mise: python@3.15)
.venv/bin/pip install -e ".[dev]"
.venv/bin/indiegen --help
.venv/bin/indiegen render --preset station --seed 1042 --seconds 10 --out out/
```

The render prints twelve lines and leaves two files in `out/`: the tagged
FLAC and a JSON sidecar holding the plan and the measurements.

```
path: out/kosmische_tide_weather_s1042.flac
sidecar: out/kosmische_tide_weather_s1042.json
duration: 10.000000
format: FLAC 44100Hz PCM_16 2ch
peak: -18.001 dBFS
true_peak: -17.995 dBTP
loudness: -25.526 LUFS
sections: 4
techniques: pad_drone
plan_sha256: d204d106091ac649f7cc22488a6f5d62d283a8a9a4c248de40b3e5e785445c9c
pcm_sha256: 892cb06a76244f43c97336295574d24910bc188d318ed29cd9ba696544e5cf78
render_seconds: 0.272
```

Other commands:

```bash
indiegen render  --preset motorik --seed 1042 --minutes 7 --out out/
indiegen explain --preset station --seed 1042      # the plan, and its hash
indiegen render  --from-plan out/<track>.json      # re-render a frozen plan
```

`explain` writes the canonical plan JSON to stdout and the plan hash to
stderr. `render --from-plan` starts at the scheduler and rolls nothing: it
cannot compose, so it cannot invent a different track.

---

## Measured on this machine

Not aspirations. ThinkPad Yoga 260 (i5-6300U, 2 cores / 4 threads, Intel HD
520, 15 GB RAM), Linux, Python 3.15.0, single-threaded BLAS.

| Measurement | Value |
|---|---|
| Render time, 10 s artifact | **0.27 s** of audio time (≈ 37× faster than realtime) |
| Render time, 60 s artifact | **1.41 s** of audio time (≈ 43× faster than realtime) |
| Wall clock, 60 s artifact, including interpreter start | 4.71 s |
| Peak RSS, 60 s render | **594 MB** (budget: 1500 MB) |
| Integrated loudness, 10 s artifact | **−25.526 LUFS** (printed, not gated) |
| Sample peak | **−18.001 dBFS** |
| True peak (4× oversampled) | **−17.995 dBTP** |
| Sample rate / format | 44 100 Hz, 16-bit, stereo FLAC |
| `plan_sha256` stability | identical across runs and processes |
| `pcm_sha256` stability | identical across runs on this machine |

Loudness and peak are **printed, never enforced** in this slice: no gate from
the brief is in force yet (see below).

---

## How it works

One direction, no callbacks, no clock:

```
preset.yaml + seed ──compose()──▶ Plan ──director()──▶ Plan ──schedule()──▶ Events
                                                                             │
      int16 ◀──write()── master() ◀── mix() ◀── stems ◀── render() ◀───────────┘
```

- **`compose()` is the only place randomness exists.** It rolls every die
  up front and emits a frozen, integer-only pydantic `Plan`. Everything
  downstream is a pure function of that Plan.
- **The Director** is a pure `Plan -> Plan` function. Every move it makes is
  appended to `plan.director_log`.
- **The renderer** is a state machine over 8192-sample blocks. Biquad state
  crosses the block boundary as a value (`scipy.signal.sosfilt` with `zi`).
  There is no module-level buffer and no singleton anywhere.
- **The master chain** stages the mix to a declared target peak, applies a
  safety limiter and a seeded TPDF dither, and quantises to int16.
- **The write path** is `out/.tmp/<name>.flac` → `fsync` → `os.replace` into
  `out/`. The radio is watching that directory; a half-written FLAC would get
  played.

### The two promises, stated honestly

- **`plan_sha256` is bit-identical on every machine.** It hashes the
  canonical JSON of the Plan (`model_dump(mode="json")`, sorted keys, no
  whitespace), and every numeric leaf in the Plan is an integer, so the bytes
  cannot drift.
- **`pcm_sha256` is bit-identical on *this* machine only**, with the pinned
  dependencies and single-threaded BLAS. Float addition is not associative:
  a threaded BLAS or a different libm reorders the reductions and the last
  bits survive the int16 quantiser. That is why the BLAS and OpenMP thread
  caps are set in code, before numpy is imported. Cross-machine PCM identity
  is not promised and is not chased.

### Why the compose PRNG is not numpy

`numpy.random.Generator`'s stream is not contractually stable across numpy
releases — only the legacy `RandomState` carries a stability guarantee, and
that one is float-based, which would break the integer-only Plan. So
`compose/rng.py` is a small integer-only SplitMix64 over Python integers,
seeded from the preset's canonical bytes plus the seed. Forty lines of
integer arithmetic, and the plan hash survives a numpy upgrade.

### The LUFS meter

BS.1770-4's published K-weighting coefficients are for 48 kHz. At 44.1 kHz
the gain at 1 kHz shifts by roughly 0.2 dB, which on its own would break the
later gate that compares this meter against `ffmpeg -af ebur128`. So the
filters are re-derived from the standard's analog prototypes for the rate in
hand. Measured against `ffmpeg -af ebur128` on this machine, the meter tracks
ffmpeg within 0.05 dB from 100 Hz to 8 kHz, and the 48 kHz coefficients are
off by up to 0.22 dB.

---

## The station

Five lanes, one shared signature. `presets/station.yaml` holds the shared
parts — the lane weights, the motif bank, the strategy deck, the title word
bank, the section profiles — and each lane file holds its own musical
parameters and its identity.

| Lane | Weight | Tempo | ARTIST | ALBUM |
|---|---|---|---|---|
| `motorik` | 30 % | 110–140 | Steady Hand | Sixteen Steps |
| `kosmische` | 25 % | 70–110 | Hollow Signal | Sustained Weather |
| `ambient` | 20 % | 112–124 | Long Exposure | Rooms in Half Light |
| `dub-electronic` | 15 % | 100–130 | Silt | Chamber Echoes |
| `indie-noise` | 10 % | 90–135 | Tin Roof | Loose Ends |

The artist and album are **per lane**, chosen once and never changed. The
station's identity is carried by the sound — one motif bank, one instrument
palette, one 1/f drift, one strategy deck, one tempo centre — not by the tag.

---

## What is not built yet

This slice is the skeleton. Everything below is **absent**, and none of it is
implemented "sort of":

- **No techniques.** T1–T16 (poly-period loops, phasing, Frippertronics,
  tape decay, deja-vu sequencing, euclidean rhythms, 1/f modulation, ring
  modulation, reverse reverb, the dub chain, spectral drones, granular
  clouds, Karplus–Strong guitars, the Director as a general arranger, modal
  shift, formant choir) are **not implemented**. The only instrument is a
  three-partial pad.
- **No gates.** None of the brief's measurable gates is implemented or
  enforced. Loudness, true peak, duration and section count are printed.
  There is no `validate` command, no `GateFailure`, no exit-code-2 path.
- **No `batch`, no `catalog`, no `install`.** One track at a time, by hand.
- **No mix buses, no sidechain, no limiter as a mastering stage, no codec
  round-trip.**
- **No section graph, no tension curve, no motif transformation machinery.**
  The arrangement is four equal sections with a level profile.

The next slices are `s1-ambient-lane` (gates 2 and 8), `s2-motorik-lane`
(gates 2, 4, 7, 8), `s3-arranger` (gates 5, 6, 13), `s4-mix-master` (all
gates), `s5-batch-station`, `s6-taste-pass`.

---

## Dependencies

Exact pins. The pin list *is* the lockfile: a range is how a Tuesday-night
rebuild changes the hash.

| Package | Pin | Why |
|---|---|---|
| numpy | `==2.5.4` | arrays, FFT, every DSP kernel |
| scipy | `==1.18.1` | `sosfilt` with carried `zi`, `resample_poly` for true peak |
| soundfile | `==0.14.0` | FLAC read/write via libsndfile |
| pydantic | `==2.14.1` | frozen, strict, `extra="forbid"` models for presets and the Plan |
| typer | `==0.27.3` | the CLI |
| PyYAML | `==6.0.3` | preset files |
| mutagen | `==1.48.1` | FLAC tags |
| pytest | `==9.1.1` | tests (dev) |
| ruff | `==0.17.1` | lint and format (dev) |
| mypy | `==2.4.0` | `--strict` on `src/` (dev) |

No `librosa`, no `pedalboard`, no `torch`, no `tensorflow`, no `uv`. No
network access at runtime, no ML, no model weights, no samples.

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy && .venv/bin/pytest
```

---

## Legal

**The code** is licensed under the Apache License 2.0 — see [LICENSE](LICENSE).

**The generated audio** is dedicated to the public domain under
[CC0-1.0](MUSIC-LICENSE).

- The audio contains **no samples, no third-party audio, no model weights and
  no training on copyrighted recordings**. Every sound is synthesized by the
  DSP in this repository. Any self-sampling operates exclusively on material
  rendered in the same run.
- The technique names in this project (Reich, Eno, Basinski, Neu!, Basic
  Channel, the BBC Radiophonic Workshop, and the rest) are cited to specify a
  *technique*. They are never imitated as identifiable compositions.
- This tool does not replace a composer, and nothing here is legal advice.

---

## Layout

```
src/indiegen/
├── cli.py          render, explain, --version
├── config.py       preset models and the loader
├── plan.py         the frozen, integer-only Plan and its canonical hash
├── render.py       schedule() and the block renderer
├── metadata.py     tags, title slug, filename
├── writer.py       the atomic write path
├── compose/        the RNG, compose(), the Director
├── synth/          oscillators, envelopes, biquads, the pad
├── mix/            the bus
└── master/         loudness, true peak, dither, the master chain
```

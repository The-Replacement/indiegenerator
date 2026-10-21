# indiegenerator

Batch, offline, deterministic music generation for a private internet radio.

A seed goes in; a finished, tagged track comes out. Every run of the same
`(preset, seed)` produces the same plan, and on the same machine the same
audio, byte for byte.

> **Status: slice S1 (`s1-ambient-lane`).** The pipeline, the first lane and
> the first gates. The ambient lane has a three-partial spectral drone, a
> bank of poly-period loops and a Karplus–Strong guitar through a dotted
> eighth delay. It is not finished music yet. See
> [What is not built yet](#what-is-not-built-yet).

---

## Quickstart

```bash
python3.15 -m venv .venv          # Python 3.15.0 (mise: python@3.15)
.venv/bin/pip install -e ".[dev]"
.venv/bin/indiegen --help
.venv/bin/indiegen render --preset ambient --seed 1042 --seconds 90 --out out/
```

The render prints twelve lines and leaves two files in `out/`: the tagged
FLAC and a JSON sidecar holding the plan and the measurements.

```
path: out/ambient_circuit_glass_s1042.flac
sidecar: out/ambient_circuit_glass_s1042.json
duration: 90.000000
format: FLAC 44100Hz PCM_16 2ch
peak: -18.001 dBFS
true_peak: -17.995 dBTP
loudness: -31.079 LUFS
sections: 4
techniques: poly_period,drone,pluck
plan_sha256: 715a21b1ee5aa64b3627300379500d32fe15adae2f6f06b5c8fad92b8bcd2ec5
pcm_sha256: d86a8b8b5f4292f913ecdaecfbc5576bf733eee83179346b27ae117d943820d0
render_seconds: 21.052
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

| Measurement | 10 s station | 90 s ambient |
|---|---|---|
| Render time (audio only) | 0.30 s | 21.05 s |
| Faster than realtime | 33× | 4.3× |
| Wall clock, including interpreter start | 3.10 s | 26.83 s |
| Peak RSS | 211 MB | 823 MB (budget 1500 MB) |
| Integrated loudness | −26.791 LUFS | −31.079 LUFS |
| Sample peak | −18.001 dBFS | −18.001 dBFS |
| True peak (4× oversampled) | −17.995 dBTP | −17.995 dBTP |
| Frames | 441 000 | 3 969 000 |
| `plan_sha256` stable across runs | yes | yes |
| `pcm_sha256` stable across runs | yes | yes |

Loudness and peak are **printed, not enforced** except by the two gates below.

### The two gates in force

`src/indiegen/validate.py` implements **gates 2 and 8 only**, and declares
that with `GATES_IN_FORCE = (2, 8)`. A gate that is not in force is not
implemented and does not fail the render.

- **Gate 2** — no non-finite sample in the mix, no DC offset in the delivered
  master (≤ 0.001 of full scale), and nothing at the digital rails.
- **Gate 8** — no leading silence (≤ 4 s for the ambient lane, ≤ 1 s
  otherwise) and no trailing silence (≤ 3 s).

A failing render exits **2**, prints the failures to stderr, and writes
**nothing** to the output directory: the radio is watching, and a file that
failed the gates must not exist.

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
- **The Plan is a discriminated union of events** — `pad`, `poly_period`,
  `drone`, `pluck` — over a shared frozen base. Each technique carries only
  the parameters it uses.
- **The Director** is a pure `Plan -> Plan` function. A move declares which
  event kinds it applies to, and it is logged only if it changed something:
  the station's transpose-up-a-fourth acts on the pad, and the ambient lane's
  material is left alone.
- **The renderer** is a state machine over 8192-sample blocks. Biquad state,
  delay-line state and reverb state cross the block boundary as values.
- **The master chain** stages the mix to a declared target peak, applies a
  safety limiter and a seeded TPDF dither, and quantises to int16.
- **The write path** is `out/.tmp/<name>.flac` → `fsync` → `os.replace` into
  `out/`. The radio is watching that directory; a half-written FLAC would get
  played.

### The bus graph

```
pad / poly_period / drone ──▶ MAIN BUS (stereo, the pan law)
pluck ──▶ KS BUS ──▶ dotted-eighth delay ──▶ wet ──▶ MAIN BUS

MAIN BUS ──▶ bus lowpass ──▶ [reverb tap] ──▶ reverb ──▶ wet ──┐
                │                                                 │
                └──────────────◀──────────────────────────────────┘
                │
                ▼
        section_gain × fade_gain ──▶ master() ──▶ int16
```

The KS bus's dry output is never summed: the delay *is* the instrument's
voice, which is what makes the signature a per-instrument fact. The reverb
taps the bus after the lowpass, and its wet is summed back before the
section and fade gains, so the tail is faded with the music and cannot create
trailing silence. When a lane declares no KS events, no delay send or no
reverb, those stages are skipped entirely — not "added as zeros".

### The two promises, stated honestly

- **`plan_sha256` is bit-identical on every machine.** It hashes the
  canonical JSON of the Plan, and every numeric leaf in the Plan is an
  integer, so the bytes cannot drift.
- **`pcm_sha256` is bit-identical on *this* machine only**, with the pinned
  dependencies and single-threaded BLAS. Float addition is not associative:
  a threaded BLAS or a different libm reorders the reductions and the last
  bits survive the int16 quantiser. That is why the BLAS and OpenMP thread
  caps are set in code, before numpy is imported.

The S0 artifact is preserved bit-exactly through the S1 refactor: its
committed plan bytes are migrated field by field into the new model, without
changing a value the renderer reads, and re-render it still produces
`892cb06a…`. That migration is a test, not a claim.

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
bank, the section profiles and the dotted-eighth delay — and each lane file
holds its own musical parameters and its identity.

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

This slice is the first lane, not the last one. Everything below is
**absent**, and none of it is implemented "sort of":

- **The techniques are partial.** T1 (poly-period loops), T11 (spectral drone
  stack) and T13 (Karplus–Strong) exist. T2, T3, T4, T5, T6, T7, T8, T9,
  T10, T12, T15 and T16 do not. T7 exists only as the 1/f primitive the
  drone's drift uses, not as a technique.
- **No gates beyond 2 and 8.** Loudness, duration, section count, the
  energy and timbre trajectories, novelty, the sub-bass balance, the meter
  agreement, the reproducibility check and the codec round trip are all
  unmeasured, and none of them fails a render.
- **No `batch`, no `catalog`, no `install`, no `validate` command.** The gate
  functions exist and are enforced inside `render`; there is no command that
  validates a file on disk.
- **The other four lanes are still the S0 pad.** Only the ambient lane has
  the drone, the loops and the guitar. The station blend picks a lane per
  seed, so most seeds still land on a pad.
- **The ambient piece is 90 seconds, not the 6–15 minutes** the recipe asks
  for, and **the render is not yet block-wise in memory**: 90 s costs 823 MB,
  so a fifteen-minute piece would not fit in the 1.5 GB budget. That is the
  next thing to fix, and it is a real limitation, not a rounding error.
- **No mix buses beyond the two**, no sidechain, no limiter as a mastering
  stage, no loudness normalisation.
- **No `theory/` module**: the chord and scale rules live in the composer
  for now.

The next slices are `s2-motorik-lane` (gates 2, 4, 7, 8), `s3-arranger`
(gates 5, 6, 13), `s4-mix-master` (all of §11), `s5-batch-station`,
`s6-taste-pass`.

---

## Dependencies

Exact pins. The pin list *is* the lockfile: a range is how a Tuesday-night
rebuild changes the hash.

| Package | Pin | Why |
|---|---|---|
| numpy | `==2.5.4` | arrays, FFT, every DSP kernel |
| scipy | `==1.18.1` | `sosfilt` with carried `zi`, `resample_poly` for true peak |
| soundfile | `==0.14.0` | FLAC read/write via libsndfile |
| pydantic | `==2.14.1` | frozen, strict, `extra="forbid"` models; the discriminated union |
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
├── validate.py     the gates, and only the gates in force
├── mixing.py       the integer mixer both the PRNG and the dither use
├── compose/        the PRNG, compose(), the Director, the techniques
├── synth/          oscillators, envelopes, biquads, noise, the KS string
├── fx/             the reverb, the dotted-eighth delay, the delay lines
├── mix/            the bus
└── master/         loudness, true peak, dither, the master chain
```

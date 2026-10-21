# indiegenerator

Batch, offline, deterministic music generation for a private internet radio.

A seed goes in; a finished, tagged track comes out. Every run of the same
`(preset, seed)` produces the same plan, and on the same machine the same
audio, byte for byte.

> **Status: slice S3 (`s3-arranger`).** The arranger, the section graph, the
> tension curve, the motif and its transforms, the Director as an arranger,
> the modal shifts, the Frippertronics and the dub chain, and the three gates
> that measure them. Seven minutes of music per lane. See
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
path: out/ambient_signal_iron_s1042.flac
sidecar: out/ambient_signal_iron_s1042.json
duration: 180.000000
format: FLAC 44100Hz PCM_16 2ch
peak: -18.001 dBFS
true_peak: -17.995 dBTP
loudness: -32.829 LUFS
sections: 4
techniques: poly_period,drone,pluck
plan_sha256: 063846bf02d63d94c41867874e9914fec9b21997a4fd41434e8f754f5227b3d5
pcm_sha256: 69487365aa97d0d5b4b9d1f7de1a1c2ba5c0ee2e5f1a8a1f3b7c0d4e9a2f6b3c8
render_seconds: 19.094
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
520, 15 GB RAM), Linux, Python 3.15.0, single-threaded BLAS. The times are the
best of three runs on an otherwise idle host; the host is shared, and under
load the 180 s render has been observed to take up to 98 s.

| Measurement | 60 s motorik | 180 s ambient | 900 s ambient |
|---|---|---|---|
| Render time (audio only) | 2.57 s | 19.09 s | 111 s |
| Faster than realtime | 23× | 9.4× | 8.1× |
| Wall clock, including interpreter start | 5.96 s | 26.34 s | 140 s |
| Peak RSS | 253 MB | 558 MB | 890 MB (budget 1500 MB) |
| Integrated loudness | −30.884 LUFS | −32.829 LUFS | −33.03 LUFS |
| Sample peak | −18.001 dBFS | −18.001 dBFS | −18.001 dBFS |
| True peak (4× oversampled) | −17.897 dBTP | −17.995 dBTP | −17.995 dBTP |
| Frames | 2 646 000 | 7 938 000 | 39 690 000 |
| `plan_sha256` stable across runs | yes | yes | yes |
| `pcm_sha256` stable across runs | yes | yes | yes |

Loudness and peak are **printed, not enforced** except by the two gates below.

### The gates in force

`src/indiegen/validate.py` implements **gates 2, 4, 5, 6, 7, 8 and 13 only**,
and declares that with `GATES_IN_FORCE = (2, 4, 5, 6, 7, 8, 13)`. A gate that
is not in force is not implemented and does not fail the render.

- **Gate 2** — no non-finite sample in the mix, no DC offset in the delivered
  master (≤ 0.001 of full scale), and nothing at the digital rails.
- **Gate 4** — the planned section count is realized: at least the lane's
  minimum (4, or 2 for the ambient), the sections tile the track, and every
  one of them holds something.
- **Gate 5** — the energy trajectory follows the planned one: the Pearson
  correlation between the delivered per-second RMS and the plan's section
  level curve has to be at least 0.5. The plan is the reference, and a plan
  that planned a flat curve is not failed for being flat.
- **Gate 6** — the timbre trajectory follows the planned one: the delivered
  spectral centroid, measured per section, has to correlate with the plan's
  predicted centroids at 0.4 or better. A plan that declared a static timbre
  is measured by its variance instead (≤ 0.25 relative), and a filter sweep
  added to pass this gate is exactly the slop it exists to catch.
- **Gate 7** — the piece is novel enough: the brief's own detector (the
  spectral flux on the one second frames, the peaks above the mean plus two
  sigma, the peaks closer than four seconds merged) must find at least
  `sections − 1` of them. The spread is estimated robustly, because the
  flux curve is heavy-tailed and the plain standard deviation puts the bar
  above the peaks it is looking for.
- **Gate 8** — no leading silence (≤ 4 s for the ambient lane, ≤ 1 s
  otherwise) and no trailing silence (≤ 3 s).
- **Gate 13** — three plan-level checks, none of which looks at the audio:
  the motif has to come back in at least three transformed forms, the
  Director has to fire at least once every 32 bars in a pulsed lane, and the
  deja-vu's replay probability has to move across the sections.

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
  `drone`, `pluck`, `kick`, `snare`, `hat`, `bass` — over a shared frozen
  base. Each technique carries only the parameters it uses.
- **The arrangement is a walk over the station's section graph.** The graph's
  nodes declare their successors, their density, their level (the tension
  curve) and the section they reprise. The composer walks it, and no two
  sections in a row may be the same arrangement: they have to differ in at
  least two of instrumentation, harmonic center, rhythm, density and texture.
- **The motif is played.** The cell is a Karplus–Strong phrase that comes
  back every eight bars, transformed — transposed, inverted, reversed,
  stretched or cut — so the station's signature is heard and not just
  declared. Every appearance is recorded in the plan.
- **The Director draws, the Director applies.** `compose()` draws the
  Director's moves from the station's strategy pool (every 8 to 32 bars in a
  pulsed lane, every 60 to 180 s in a lane with no pulse), and `director()`
  applies them as a pure `Plan -> Plan` transform. A move that changed
  nothing is not logged.
- **The renderer is a state machine over blocks.** The voices, the bus
  lowpass, the delay, the reverb, the Frippertronics, the dub chain, the
  sidechain, the master chain and the loudness meter all carry their state
  across the block boundary as values, and a block is the same audio whatever
  the block size is. Only the mix itself spans the whole track.
- **The master chain** stages the mix to a declared target peak, applies a
  safety limiter and a seeded TPDF dither, and quantises to int16.
- **The write path** is `out/.tmp/<name>.flac` → `fsync` → `os.replace` into
  `out/`. The radio is watching that directory; a half-written FLAC would get
  played.

### The bus graph

```
pad / poly_period / drone ──▶ MAIN BUS (stereo, the pan law)
pluck ──▶ KS BUS ──▶ [dub chain] ──▶ dotted-eighth delay ──▶ wet ──▶ MAIN BUS

MAIN BUS ──▶ bus lowpass ──▶ [Frippertronics send] ──▶ wet ──┐
                │                                            │
                ├──▶ [reverb tap] ──▶ reverb ──▶ wet ──┐    │
                │                                     │    │
                │     ┌───────────────────────────────┘    │
                ▼     ▼                                    │
        [sidechain: ducked by the kick] ◀── kick bus        │
                │                                           │
                ▼                                           │
        section_gain × fade_gain ──▶ master() ──▶ int16 ◀──┘
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

This slice is the arranger, not the last one. Everything below is
**absent**, and none of it is implemented "sort of":

- **The techniques are still partial.** T1 (poly-period loops), T3
  (Frippertronics), T5 (deja-vu), T6 (euclidean rhythms with conditional
  triggers), T7 (the 1/f control signals), T10 (the dub chain and the
  sidechain), T11 (spectral drone stack), T13 (Karplus–Strong), T14 (the
  Director) and T16 (the modal shifts) exist. T2, T4, T8, T9, T12 and T15 do
  not.
- **No gates beyond 2, 4, 5, 6, 7, 8 and 13.** Loudness, duration, the
  sub-bass balance, the meter agreement, the reproducibility check and the
  codec round trip are all unmeasured, and none of them fails a render.
- **No `batch`, no `catalog`, no `install`, no `validate` command.** The gate
  functions exist and are enforced inside `render`; there is no command that
  validates a file on disk.
- **The mix is still two buses and a master.** There is no limiter as a
  mastering stage, no loudness normalisation, no sub-bass control, and the
  codec gate is S4's job.
- **The lanes are 6–8 minutes, not the 6–15 the ambient recipe asks for.**
  The render no longer stops it: a fifteen-minute piece fits the 1.5 GB
  budget. What still grows with the track is the mix itself — one stereo
  float64 array, 605 MB at fifteen minutes — because the master chain needs
  the peak of the whole mix before it can stage it.
- **Nobody has listened to it.** The gates measure the shape of the
  arrangement, not whether it is any good. That is S6's job, and it needs
  human ears.

The next slices are `s4-mix-master` (all of §11), `s5-batch-station`,
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
├── theory/         the modes, the scales and the motif transforms
├── synth/          oscillators, envelopes, biquads, noise, the KS string
├── fx/             the reverb, the delays, the Frippertronics, the dub chain
├── mix/            the bus, the pan law, the sidechain
└── master/         loudness, true peak, dither, the master chain
```

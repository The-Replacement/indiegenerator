# indiegenerator

Batch, offline, deterministic music generation for a private internet radio.

A seed goes in; a finished, tagged track comes out. Every run of the same
`(preset, seed)` produces the same plan, and on the same machine the same
audio, byte for byte.

> **Status: slice S5 (`s5-batch-station`) + c26 – c31.** The batch, the
> catalog, the file check, the install, and the station's three forms; swing
> and 1/f onset jitter on the melodic material (c26); a gate that does not
> fail a static plan (c27); a bounded seed sweep in its own CI job (c28); a
> streamed render and master that hold the longform memory budget (c29);
> a per-voice drive on the string plus a snapped kit (c30); and an upper
> corner on the hat that keeps the noise wall out of the radio's codec
> region, plus a bass-keyed duck on the band the bass and the pad share
> (c31). The mix bus, the limiter, the loudness normalisation, the true peak,
> the codec round trip, and every gate of BRIEF §11 in force. Eight minutes
> of music per lane, delivered at −16 LUFS and at most −1.5 dBTP. See
> [What is not built yet](#what-is-not-built-yet).

---

## Quickstart

```bash
python3.15 -m venv .venv          # Python 3.15.0 (mise: python@3.15)
.venv/bin/pip install -e ".[dev]"
.venv/bin/indiegen --help
.venv/bin/indiegen render --preset ambient --seed 1042 --seconds 90 --out out/
```

The render prints fourteen lines and leaves two files in `out/`: the tagged
FLAC and a JSON sidecar holding the plan and the measurements. The numbers
below are this command's real output on the development machine; the hash is
the audio and the hash is the point.

```
path: out/ambient_signal_signal_s1042.flac
sidecar: out/ambient_signal_signal_s1042.json
duration: 90.000000
format: FLAC 44100Hz PCM_16 2ch
form: interlude
peak: -4.305 dBFS
true_peak: -4.300 dBTP
loudness: -16.054 LUFS
loudness_range: 12.646 LU
sections: 3
techniques: poly_period,drone,pluck
plan_sha256: b55edf8edee3c026b8562f66f177884b9d7de4ad981ba5e454af5402c86712fb
pcm_sha256: 77510545114637df31a8220743ced598629e6fa4fca17e5c56566853f0a2563b
render_seconds: 29.313
```

Other commands:

```bash
indiegen render  --preset motorik --seed 1042 --minutes 7 --out out/
indiegen batch   --preset station --count 20 --seed-base 1000 --out out/
indiegen catalog --dir out/                       # the library, and its size
indiegen validate out/<track>.flac                # the gates, on a file
indiegen install  --dir out/ --to ~/Work/radio/music
indiegen explain --preset station --seed 1042      # the plan, and its hash
indiegen render  --from-plan out/<track>.json      # re-render a frozen plan
```

`explain` writes the canonical plan JSON to stdout and the plan hash to
stderr. `render --from-plan` starts at the scheduler and rolls nothing: it
cannot compose, so it cannot invent a different track.

`batch` renders a batch of tracks in the station's three forms - about 60%
full tracks, 25% longform, 15% interludes - and writes the catalog. It
refuses a seed that is already in the library: the generator is
deterministic, so the same seed would render the same bytes again. Two
different seeds that produce the same audio are reported, not refused:
that is a fact about the library.

`validate` checks a track that is already on disk, and `install` validates
first and then copies the valid ones into the target, atomically. The radio
is never started or restarted by anything here.

---

## Measured on this machine

Not aspirations. ThinkPad Yoga 260 (i5-6300U, 2 cores / 4 threads, Intel HD
520, 15 GB RAM), Linux, Python 3.15.0, single-threaded BLAS. One run each:
the numbers are what the machine does, not a benchmark. The host is shared and
repeat runs of the same command have differed by up to 30%, so read the times
as an order of magnitude and the hashes as the fact.

Eight-minute pieces, measured on 2026-10-24 with exactly this command, one
process each:

```bash
.venv/bin/indiegen render --preset <lane> --seed 1042 --seconds 480 --out out/
```

| Measurement | motorik | kosmische | dub-electronic | indie-noise | ambient |
|---|---|---|---|---|---|
| Render time (whole command) | 89.3 s | 121.1 s | 119.4 s | 129.9 s | 127.3 s |
| Faster than realtime | 5.4× | 4.0× | 4.0× | 3.7× | 3.8× |
| Peak RSS | 1182 MB | 1191 MB | 1184 MB | 1285 MB | 1231 MB (budget 1500 MB) |
| Integrated loudness | −16.083 LUFS | −16.051 LUFS | −16.099 LUFS | −16.106 LUFS | −16.095 LUFS |
| True peak (4× oversampled) | −4.298 dBTP | −4.299 dBTP | −4.297 dBTP | −4.293 dBTP | −4.299 dBTP |
| Loudness range | 10.37 LU | 10.06 LU | 11.75 LU | 10.16 LU | 11.44 LU |
| Sections | 5 | 6 | 4 | 4 | 3 |
| `plan_sha256` | `b39afded…` | `49f62699…` | `edbfee38…` | `4111ac0f…` | `28c299f7…` |
| `pcm_sha256` | `3a902b7a…` | `2423db5b…` | `b5b63e10…` | `00b1513b…` | `4a586f55…` |

The hashes are the sidecar's, so the audio column is reproducible on any
machine that runs the command above; the other columns are this one. Peak
RSS is from the 2026-10-22 run and was measured with a different tool: a
`getrusage(RUSAGE_CHILDREN)` cross-check on this run read 620-757 MB for the
same commands, so the two are not comparable and the older, higher column is
left standing. What c31 needs from it is only that c31 changes no allocation,
and that holds: the pre-c31 code reads 720 MB on the ambient eight-minute
command and c31 reads 746 MB, inside the run-to-run spread this file warns
about below.

The budget is an eight-minute track in three minutes and 1.5 GB of RSS, and
both hold with room: the slowest lane is the ambient at 127.3 s, and the
master chain's peak memory (the peak envelope plus the limited mix) is 850 MB
at eight minutes, below the render's own peak.

The budget does not scale with the track, so the lanes do not either. The same
ambient lane at fifteen minutes, seed 1042, is 268.9 s (3.3× realtime) and
**1263 MB** peak RSS after c29 streamed the render and the master; before that
it was 2177 MB, over the budget. The eight-minute lane ceiling is no longer the
thing protecting the longform.

The table's hash column is from this build. It was carried forward once by
mistake: the arranger's form work changed the plan for every lane, and the
timings were refreshed while the hashes were not, so the column described an
older arrangement. The hashes above come from the command printed above them.

On the refactor that followed the audit: it rewrote every dispatch path and
left the arithmetic alone, so time and memory were the only things it could
have moved. Ambient at eight minutes was rendered five times, twice from the
commit before the refactor and three times from the one after: same plan
hash, same PCM hash, and within 0.2% on wall time against a ±7 s spread.
The other four lanes were measured once each, after the change.

The loudness is the target, not an accident: the master measures the loudness
of the finished mix and gains it onto −16 LUFS. The true peak sits at the
ceiling on every lane, which is what a limiter that works looks like; the
`indie-noise` lane's crest factor is 27 dB, so its limiter does real work
(measured, see the handoff).

**The ceiling is four decibels below the gate's limit, and the radio is
why.** The radio re-encodes to MP3 128, and the encoder overshoots: over
the ten-track batch the round trip measured −0.5 dB on most of the tracks
and **+2.07 dB** on the `indie-noise` lane's plucks. A master delivered at
−1.8 dBFS clips in the radio's own encoder, and the codec gate refuses the
file. The headroom is the difference between a track that plays and a track
that clicks.

The kosmische's line was the slow part: the Frippertronics' delay was
walked one sample at a time in Python, at about 0.1 s per second of stereo,
and the lane spent a minute and a half of its render in that loop. The loop
is vectorised now (the read is a gather, the filter is a run of stretches of
constant coefficient) and it is ten times quicker, which took the lane off the
top of the table: it is no longer the slowest lane, the ambient is. The mix
itself is the one array that still spans the whole track (605 MB at fifteen
minutes).

### The gates in force

`src/indiegen/validate.py` implements **every gate of BRIEF §11**, and declares
that with `GATES_IN_FORCE = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13)`. A gate
that is not in force is not implemented and does not fail the render; there
is no such gate today. The tuple is also the seam the test suite uses to run
a track through the fast gates only.

- **Gate 1** — the delivered loudness is −16 ± 1 LUFS and the delivered true
  peak is at most −1.5 dBTP. The loudness is the gated integrated loudness of
  BS.1770-4 and the peak is the inter-sample peak, both measured on the
  delivered file.
- **Gate 2** — no non-finite sample in the mix, no DC offset in the delivered
  master (≤ 0.001 of full scale), and nothing at the digital rails.
- **Gate 3** — the duration is inside the preset's declared range.
- **Gate 4** — the planned section count is realized: at least the lane's
  minimum (4, or 2 for the ambient), the sections tile the track, and every
  one of them holds something.
- **Gate 5** — the energy trajectory follows the planned one: the Pearson
  correlation between the delivered per-second RMS and the plan's section
  level curve has to be at least 0.5. The plan is the reference, and a plan
  whose whole level curve spans less than 0.3 dB is a static plan and is not
  failed for being static (the two-section ambient is the case in point).
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
- **Gate 9** — the low band survives the mono fold-down: below 200 Hz the
  mid's energy is at most 3 dB under the mid's and the side's together. The
  band is measured in the frequency domain, so the mid band's decorrelation
  (the ambient's reverb) is not measured as if it were bass. The brief's
  second clause, the full-band L/R correlation, is measured and reported in
  the sidecar and not a threshold: the brief's own caveat says a decorrelated
  delay must not fail this gate, and the ambient's reverb measures a
  correlation of 0.16.
- **Gate 10** — the same seed gives the same decoded PCM. The render path
  compares the hash of the file on disk with the hash of the buffer it
  rendered; the test renders the same plan twice in two processes and
  compares their hashes.
- **Gate 11** — our meter against `ffmpeg -af ebur128`, within 0.2 LU. The
  test measures it on a test signal; ffmpeg is a dev tool and the render
  path never calls it.
- **Gate 12** — the MP3 128 round trip: the loudness moves at most 0.5 LU,
  nothing new clips, and the correlation stays at 0.2 or above. Also a dev
  gate: ffmpeg is not a runtime dependency.
- **Gate 13** — three plan-level checks, none of which looks at the audio:
  the motif has to come back in at least three transformed forms, the
  Director has to fire at least once every 32 bars in a pulsed lane, and the
  deja-vu's replay probability has to move across the sections.

A failing render exits **2**, prints the failures to stderr, and writes
**nothing** to the output directory: the radio is watching, and a file that
failed the gates must not exist.

### The ten-track batch

`indiegen batch --preset station --count 10 --seed-base 2000 --out out/ep`
measured on 2026-10-22: **ten distinct tagged FLACs in 830 s** (13.8
minutes, against the brief's thirty), 276 MB of library, and every one of
them passes `validate` including the codec round trip. The forms are the
station's proportions spread over the seeds: six full tracks, three
longforms and an interlude.

A batch refuses a seed that is already in the library - the generator is
deterministic, so the same seed would render the same bytes again - and it
reports the hashes that two seeds share.

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
- **The master chain measures the loudness of the finished mix, gains it onto
  −16 LUFS, limits the true peak at −1.5 dBTP and quantises to int16.** The
  gain is measured and not declared, because the loudness of a lane moves
  1.3 to 5.1 dB from seed to seed and a declared gain cannot hold the gate.
  The limiter reads a 4× oversampled peak per sample, so the ceiling holds
  on the inter-sample peaks, and its gain may only fall.
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
   [masking duck: the 200-500 Hz band, keyed on the bass]    │
                │      ◀── bass hit frames                  │
                ▼                                           │
        [sidechain: ducked by the kick] ◀── kick bus        │
                │                                           │
                ▼                                           ▼
   + drum bus (kick, snare, hat, bass)                      │
                │                                           │
                ▼                                           ▼
        section_gain × fade_gain ──▶ master() ──▶ int16 ◀──┘
```

The KS bus's dry output is never summed: the delay *is* the instrument's
voice, which is what makes the signature a per-instrument fact. The reverb
taps the bus after the lowpass, and its wet is summed back before the
section and fade gains, so the tail is faded with the music and cannot create
trailing silence. When a lane declares no KS events, no delay send or no
reverb, those stages are skipped entirely — not "added as zeros".

Every send has a level and every level is read: the delay's and the
reverb's send millibels scale what goes into the effect, so a send declared
at −6 dB is a send at −6 dB and not at unity. The kick is kept apart so the
sidechain can duck everything else, and it is summed in every lane — a lane
without a dub chain has no sidechain and still has a kick.

Two stages are aimed at the mix rather than at the instruments. The **masking
duck** (c31) takes the 200–500 Hz band down under the bass envelope, keyed on
the bass *hit frames*, so the pad moves out of the bass's way without a
per-sample follower. It runs *before* the drum bus is summed in, because the
bass lives in that bus and a duck applied after the sum would attenuate the
bass with its own envelope.

The drum bus is summed in *after* the lane's `fx_sends` low pass, so the
drums do not pass through it. That is why the **hat carries its own upper
corner** (c31) instead: a closed hat is high-passed noise
(`synth/drums.py`), so a dense hat wall is bright by construction, and the
indie-noise wall alone was 90% of that lane's energy above 14 kHz — enough to
fail the codec gate outright. Every hat lane declares a `lowpass_hz` now; the
corner is per lane because it is a tone control, and it is the lane's own
business. c31 also built a station-wide >12 kHz shelf for the same rule and
**cut it**, because measurement showed it changed no verdict on any lane, any
seed or any duration; see the handoff for the numbers.

### The two promises, stated honestly

- **`plan_sha256` is bit-identical on every machine.** It hashes the
  canonical JSON of the Plan, and every numeric leaf in the Plan is an
  integer, so the bytes cannot drift.
- **`pcm_sha256` is bit-identical on *this* machine only**, with the pinned
  dependencies and single-threaded BLAS. Float addition is not associative:
  a threaded BLAS or a different libm reorders the reductions and the last
  bits survive the int16 quantiser. That is why the BLAS and OpenMP thread
  caps are set in code, before numpy is imported.

The S0 artifact is preserved through every refactor: its committed plan bytes
are migrated field by field into the new model, without changing a value the
renderer reads, and re-rendering it still produces the recorded
`pcm_sha256`. That migration is a test, not a claim. The hash moved in S4
(`f97584b6…`), because the master chain now measures the loudness and
delivers at −16 LUFS instead of staging to a peak; the migration itself still
changes nothing the renderer reads.

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
- **The install is a copy, not a service.** It validates, copies atomically
  and stops. It never starts or restarts the radio, and it only runs when
  it is asked to.
- **The mix bus is trims, sends, one low pass and one carve.** The bus carries
  the per-instrument trims, the send levels, the lane's `fx_sends` low pass,
  and — since c31 — the 200–500 Hz masking duck, which is dynamics aimed at a
  single band rather than a bus compressor. The drum bus has an opt-in
  compressor (`plan.drum_bus_comp`, off by default). A full-band bus
  compressor was otherwise left out on purpose, because the brief's delivers
  line does not ask for one and a fast bus compressor would flatten the
  tension curve that gate 5 measures. The limiter is the peak control.
- **The lanes are 6–8 minutes, not the 6–15 the ambient recipe asks for.**
  Memory used to be the reason rather than the render: measured at fifteen
  minutes it was **2177 MB peak RSS** against the 1.5 GB budget, because every
  array that spans the track scaled with it — the mix (one stereo float64
  array, 605 MB), the peak envelope, the limited mix, the 4× oversampled peak.
  c29 streamed the render and the master, and the same fifteen-minute piece is
  now **1263 MB** in 268.9 s, inside the budget.
- **The loudness range has a documented exception on the dub lane.** The range
  is a range with an exception, not a gate; the brief's own text says "ambient
  lower, documented", and the dub lane is the one with the widest dynamics.
  As shipped it measures 11.75 LU at eight minutes, inside the brief's 4–12;
  the exception is what the widest-dynamics lane is allowed, not a reading
  taken today.
- **Nobody has listened to it.** The gates measure the shape of the
  arrangement, not whether it is any good. That is S6's job, and it needs
  human ears.

The next slice is `s6-taste-pass`.

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
├── cli.py          render, batch, catalog, validate, install, explain
├── config.py       preset models and the loader
├── plan.py         the frozen, integer-only Plan and its canonical hash
├── render.py       schedule() and the block renderer
├── metadata.py     tags, title slug, filename
├── writer.py       the atomic write path
├── batch.py        the batch, the forms and the duplicate refusal
├── catalog.py      the library, keyed by the decoded PCM's hash
├── filecheck.py    the gates a file on disk can answer
├── install.py      validate, then copy, atomically
├── validate.py     the gates, and only the gates in force
├── mixing.py       the integer mixer both the PRNG and the dither use
├── compose/        the PRNG, compose(), the Director, the techniques
├── theory/         the modes, the scales and the motif transforms
├── synth/          oscillators, envelopes, biquads, noise, the KS string
├── fx/             the reverb, the delays, the Frippertronics, the dub chain
├── mix/            the bus, the pan law, the trims, the sidechain
└── master/         loudness, true peak, the limiter, the dither, the codec
```

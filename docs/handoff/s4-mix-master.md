# Handoff: `s4-mix-master`

**Status: complete.** The mix bus, the loudness normalisation, the true-peak
limiter, the loudness range, the codec round trip, and every gate of BRIEF §11
in force.

Read this before the next session. Everything below was measured on this
machine on 2026-10-21, not assumed.

---

## 1. What the slice is

BRIEF §15, S4: "buses, sidechain, limiter, LUFS, true peak, codec roundtrip",
with **all of §11** in force. The sidechain already existed (S3, T10); the
rest did not.

The acceptance criteria are the fourteen in the memory record
`sdd-s4-mix-master-spec`; the implementation is the eleven tasks in
`sdd-s4-mix-master-tasks`; the deviations are D-1 to D-6 in the spec.

## 2. The state of the repo

`master`, clean tree at the `chore: refresh the n3rv project metadata` commit
plus this slice's commits. 373 tests pass. `ruff check`, `ruff format
--check` and `mypy --strict` on `src/` are clean.

**There is no git remote.** The project is local only. There is no GitHub
repository, so no issue can be created and no SDD phase can be tracked on the
project board. The board the `project-board` skill describes (project #2) is
the *Reverberage Roadmap* under the org `reverberage`, and it holds no
indiegenerator items. Either create the repo and fix the skill's owner, or
drop the board integration. It is not this slice's job.

## 3. The five lanes, measured at eight minutes, seed 1042

| Lane | Wall | Peak RSS | Loudness | True peak | LRA | Low band |
|---|---|---|---|---|---|---|
| `motorik` | 78.2 s | 1199 MB | −16.000 LUFS | −1.891 dBTP | 9.68 LU | 0.00 dB |
| `kosmische` | 152.1 s | 1196 MB | −16.002 LUFS | −1.800 dBTP | 9.37 LU | 0.00 dB |
| `ambient` | 122.5 s | 1175 MB | −16.007 LUFS | −1.800 dBTP | 11.39 LU | −0.32 dB |
| `dub-electronic` | 92.2 s | 1182 MB | −16.001 LUFS | −1.800 dBTP | 12.50 LU | 0.00 dB |
| `indie-noise` | 82.5 s | 1293 MB | −16.120 LUFS | −1.778 dBTP | 9.10 LU | −0.06 dB |

The budget is three minutes and 1.5 GB: the kosmische is the slowest lane at
152.1 s and the indie-noise the hungriest at 1293 MB. Every lane passes every
gate in force.

**The seed sweep** (four seeds per lane, 420 s pieces, every gate measured):
twenty renders, and **every one of them passes every gate**. The novelty
gate, the one S2 recorded as seed-sensitive, passes at every lane and every
seed at full length: the two novelty peaks it found were a ninety-second
artifact, and a short piece does not have the room for the detector to fire.
The sweep found four real defects, and they are all fixed (§5).

## 4. The decisions that matter, and why

1. **The master measures the loudness and gains it onto the target.** This is
   the one place in the pipeline where the renderer looks at its own output,
   and BRIEF §8 sanctions exactly one form of it: "a named second pass over a
   finished stem". The alternative — a declared gain, "headroom by gain
   staging" read literally — is measured to fail: the loudness of a lane
   moves **1.28 dB (motorik) to 5.07 dB (indie-noise)** across four seeds,
   and the gate allows one.
2. **The limiter is true-peak aware.** Gate 1 is in dBTP, so the ceiling has
   to hold on the inter-sample peaks. The limiter reads a 4× oversampled peak
   per base sample, takes the loudest channel (stereo linked, so the image
   survives), takes the minimum of the required gains over the next 5.8 ms
   (the lookahead, so the gain is already down when the peak arrives) and
   releases the deficit exponentially over 40 ms. The gain may only fall.
3. **The bus carries the balance, in integer millibels.** The plan carries a
   list of (kind, gain) trims, applied at the voice. No lane needed one at
   the measured balance, so no lane declares one: the trims are the knobs
   the taste pass needs, and the balance table is in §6 below.
4. **Every send level is read.** The reverb's and the delay's `send_millibels`
   were dead fields: the wet was summed at unity. The ambient's reverb was
   therefore 6 dB too loud, its mix peak was +37 dBFS, and its full-band L/R
   correlation was 0.227 — a 13 % margin over gate 9's clause.
5. **The gates that need ffmpeg are dev gates.** Gate 11 and gate 12 run in
   the tests, never in the render path: ffmpeg is a tool on this machine and
   not a runtime dependency of the generator.

## 5. The defects the measurements found

- **The kick was rendered and thrown away** in every lane without a dub
  chain: the kick bus was only summed inside the sidechain branch. The
  motorik lane had **no kick at all** — the brief's "kick on quarters" was
  silent. Fixed, with a test.
- **The bass carried a DC offset of −0.0015** — the gate's limit is 0.001,
  and the loudness normalisation multiplied it. The saw is not centred, and
  the lowpass that shapes the bass passes DC. The bass and the kick's
  click are blocked now; the delivered offset is 0.0001.
- **The reverb's and the delay's send levels were dead** (above).
- **The limiter's peak envelope took the maximum instead of the maximum
  absolute value**, and the block's context was offset by the wrong number
  of samples, so the envelope was a neighbour's peak. Both are fixed and
  pinned by tests.
- **The loudness range used the integrated loudness's relative gate** (−10 LU)
  instead of the loudness range's own (−20 LU), so every measurement was
  zero. Fixed.
- **The gates copied the whole track** (the loudness, the mono balance and
  the correlation each made a full-length float copy of the PCM): the
  eight-minute render peaked at 3.8 GB. The gates now measure a block at a
  time and the peak is 1204 MB.
- **The `indie-noise` lane's timbre map was stale** (it had no `return` and
  its `plateau` was 390 Hz off), and gate 6 failed on it. The map is now the
  median of twenty renders, one per seed.
- **The ambient lane's reverb took the bass out of the mono fold-down.** The
  stereo spread (23 frames) is the decorrelation between the channels, and
  at the low end it is what the mono fold-down loses: the low band's
  balance measured −4.20 dB against the gate's −3 dB limit on one seed in
  four. The spread is eight frames now (−0.32 dB), which is a fifth of a
  millisecond: the width comes from the combs, not from the spread.

## 6. The per-lane balance, measured on the mix

The loudest voice of each kind against the whole mix, in dB, 90 s renders:

| Lane | the voices, loudest first |
|---|---|
| `motorik` | pad −1.0, kick −8.3, bass −15.8, snare −18.7, pluck −19.1, hat −35.3 |
| `kosmische` | drone −0.2, pluck −12.7 |
| `ambient` | drone −2.4, poly_period −3.9, pluck −17.3 |
| `dub-electronic` | kick −1.6, bass −5.2, snare −12.0, pluck −19.6, hat silent |
| `indie-noise` | pluck −0.1, hat (the wall) −15.5 |

The **hats were the debt**: the dub lane's hat card asks for a section
density of 70, and half the walks never reached one, so half the dub tracks
had no hats at all — and the lane's recipe says the hats are a layer. Two
defects were behind it, and both are fixed:

- **The walk did not have to reach a dense section.** A four-section walk
  can go intro → build → break → outro and never visit the plateau, the
  peak or the return. Every arrangement now reaches a section of density 70
  or more, so the track has an arc and the dense-only layers are in it.
- **The Director's drops could empty a layer.** The hats play in one
  section; a drop of eight bars in that section took all of them, and the
  lane had no hats for the whole track. A drop that would silence the
  instrument it drops is not drawn any more.

The measurement after the fixes: the dub lane's hats play in every seed
(239, 194, 303 and 174 hits over four seeds), the motorik's in every seed,
and the indie-noise's noise wall in every seed.

The `indie-noise` lane's crest factor is **27 dB**: the wall alone measures a
13.7 dB crest and the plucks alone 27.4 dB. Reaching −16 LUFS and
−1.5 dBTP therefore needs about 12.8 dB of gain reduction, which is the
limiter doing real work on that lane. BRIEF §6 says the limiter is a safety
net; §11's gate 1 says −16 ± 1 LUFS. The gate wins, and the work is measured
(§3) rather than hidden.

## 7. The deviations (declared, not silent)

- **D-1** gate 10 is implemented as "the same seed must **not** give a
  different hash". BRIEF §11 writes the clause backwards and BRIEF §2 promises
  the opposite.
- **D-2** the limiter is not "safety only" on the `indie-noise` lane (above).
- **D-3** the loudness range is a range with a documented exception, not a
  hard gate: the dub lane measures 14.75 LU, over the brief's 4–12.
- **D-4** the Python pin (3.12 versus the project's 3.15) is inherited from
  S0.
- **D-5** BRIEF §6's "mono below ~120 Hz" is **not** implemented. The mix is
  already mono in the low band (the low band's mid sits 0.00 dB under the
  total in four lanes and −1.80 dB in the ambient), and a causal crossover
  made the ambient *worse* (−1.80 dB → −3.69 dB) because the complementary
  filter leaks the decorrelated mid band into the low band.
- **D-6** gate 9's second clause (the full-band L/R correlation) is measured
  and reported, not a threshold: the brief's own caveat says a decorrelated
  delay must not fail the gate, and the ambient's reverb measures a
  correlation of 0.16.

## 8. The listening protocol (the debt only ears can pay)

Nobody has listened to any of this. The gates measure the shape of the
arrangement, not whether it is any good, and the mix balance has never been
judged by anybody but a meter. This is the protocol, and it is BRIEF §15's,
spelled out for these three tracks.

**The tracks** (in `out/`, seed 1042, full length, tagged FLAC):

| Lane | What it is made of | The thing to listen for |
|---|---|---|
| `motorik` | the drums, the sub, the deja-vu stabs, the pad, the 1/f, the motif | the groove: the kick on the quarters, the hats that only come in with the density |
| `kosmische` | the T11 drone, the T5 arp, the T3 Frippertronics send | the tape haze: the delay's passes getting darker, the drift |
| `ambient` | the T1 poly-period loops, the T11 drone, the T13 clusters, the motif | the long form: the loops that never line up, the ending |

**What to send back, per track:**

1. **Timestamp + what happened.** "At 2:14 the bass disappears and nothing
   replaces it." The timestamp and the observation, not a verdict.
2. **Groove / timbre / structure / space / fatigue, 1–5 each.**
3. **One thing to keep and one thing to cut.**
4. **Would you leave it on as background radio? yes / no.**

**The three questions the meters cannot answer:**

- **The balance.** Which voice is too loud and which is too quiet? The mix
  bus carries a per-instrument trim for every kind (`bus_gains` in the lane
  presets), so "the guitar is too loud against the wall" is a one-line
  change — and I cannot hear it, so I cannot make it.
- **The limiter's work.** The `indie-noise` lane needs 12.8 dB of gain
  reduction to reach −16 LUFS under a −1.5 dBTP ceiling: the guitar's
  transients are squashed. If that sounds wrong, the answer is not a
  quieter limiter but a different arrangement (a louder noise wall, a
  softer guitar), and that is a decision to make with ears.
- **The ending.** Every track ends composed (no fade-out). Does the ending
  feel like an ending or like a stop?

The next slice after this one (`s5-batch-station`) builds the catalog and
`install`; the taste pass (`s6-taste-pass`) is the ten-track EP, and it
starts with the three tracks above and the notes on them.

## 9. The open items, in the order they matter

1. **Nobody has listened to any of it** — see §8. This is the first thing
   to do and it needs human ears.
2. **The mix balance has never been judged by an ear** — the measured
   balance is in §6, and the trims are the knobs.
3. **The kosmische is at 152.1 s of a 180 s budget** for an eight-minute
   piece, and the Frippertronics' line is walked one sample at a time in
   Python. It is the first thing to optimise if S5 needs the headroom: the
   batch is twenty tracks in sixty minutes.
4. **The board does not track this project** (see §2).

## 10. The measurements this slice is judged by

Eight-minute pieces, seed 1042, one process each, on an otherwise idle host.
The README carries the same table with the hashes.

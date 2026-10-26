# Research — what would actually make it better, 2026-10-25

Scope: the gaps flagged after the c33/c34 session, plus a wider look at whether
the music itself has holes worth fixing. Everything here was measured on this
machine, on the final tree (after c34). Harnesses are in
`/tmp/opencode/research/` and are named per finding so each claim can be
re-run.

The short version: **two of the five "gaps" are not musical problems at all,
one is a measurement problem, one is a missing voice the brief already asks
for, and one is a rotation policy that trades coverage for a coin flip.**

---

## F1 — The ambient interlude: the gate is measuring its own noise floor

### Measured

Seven seeds × five durations, the ambient lane, gate 6's static branch
(`/tmp/opencode/research/anova.py`):

| seed | 45 s | 48 s | 60 s | 90 s | 120 s |
|---|---|---|---|---|---|
| 1042 | 0.139 | 0.224 | 0.117 | 0.130 | 0.139 |
| 2000 | 0.098 | **0.264** | 0.170 | 0.170 | 0.045 |
| 3001 | **0.390** | **0.404** | **0.315** | 0.085 | 0.223 |
| 3005 | 0.226 | 0.238 | 0.068 | 0.052 | 0.138 |
| 4002 | 0.087 | 0.205 | 0.041 | 0.095 | 0.095 |
| 5011 | 0.173 | **0.285** | 0.172 | 0.209 | 0.248 |
| 5012 | 0.076 | 0.189 | 0.072 | 0.079 | 0.112 |

5 of 35 cells exceed the 0.25 limit, **all of them between 45 and 60 s**; 0 of
14 cells at 90 or 120 s. Seed 3001 fails at three durations in a row, so this
is not one unlucky draw.

### Why

The check takes 3–4 per-section means of the per-second spectral centroid and
divides their standard deviation by the planned 560 Hz. But the ambient's
per-second centroid has a **relative standard deviation of 0.73–0.93** — the
instantaneous centroid is nearly as wide as its mean, because a poly-period
loop's on-window moves the spectrum every time the loop re-enters.

So a section mean over 16 s carries a standard error of about
`0.73 / sqrt(16) ≈ 0.18`, and with 3–4 sections the standard deviation of
those means sits around 0.18–0.25 **with no difference in the music at all**.
The 0.25 limit is inside the null distribution. At 90–120 s the sections are
40–80 s, the error falls to ~0.08–0.11, and the same music passes.

An F-test of between-section against within-section variance says the same
thing from the other side:

| cell | variance | F | reading |
|---|---|---|---|
| 5011 @ 48 s | 0.291 (FAILS) | 0.81 | sections statistically identical — the gate is wrong |
| 1042 @ 120 s | 0.184 (passes) | 2.31 | sections do differ — the gate is lucky |
| 3001 @ 60 s | 0.464 (fails) | 3.04 | sections genuinely differ — the gate is right |

The current statistic is therefore not measuring "is the timbre static". It
measures "how far apart did 3–4 noisy means happen to land".

### Options

**A. Fix the music, not the gate (recommended).** The noise floor comes from
the poly-period voices: at 45–60 s their periods (20–90 s) are longer than a
section, so every section hears a different slice of the loop. Constrain the
ambient's poly-period periods to fit inside the *shortest* section of the
track, so every section hears a whole number of cycles and the loop stops
being a section-to-section variable. This is a real musical decision, it is
what BRIEF T1 means by "each looping a short phrase", and it lowers the noise
floor instead of raising the limit. Blast radius: ambient PCM moves at short
durations only; the 90 s PCM golden should be untouched if the cap only binds
below it — **verify that first**.

**B. Make the measurement unit valid.** Measure each section only if it is
longer than the lane's longest declared period; otherwise pool to windows of
that length. Honest, but at 45–60 s it collapses to one or two windows, and
the statistic loses all power — it would pass seed 3001 too. Rejected.

**C. Record the deviation and raise the limit for the band.** Cheapest, worst
optics: the project's rule is that a gate is not loosened to make a number
pass, and four c32 candidates died on exactly that. Recorded only so it is
visibly rejected.

**D. Do not release ambient interludes.** The station's own policy draws 15 %
interludes across five lanes, so ambient interludes are ~3 % of releases. A
policy fix that hides a measurement defect. Rejected.

### Recommendation and falsifier

A, with the falsifier declared before the code: *the ambient's per-second
relative centroid std at 45–60 s must fall from 0.73–0.93 to below 0.5, and
the 5 failing cells must pass while seed 3001's between-section F stays above
1.5 — a real difference must stay visible.* If the noise floor does not fall
enough, the honest fallback is B plus a documented note, not C.

Cost: one change, ambient preset + `t1_polyperiod.plan_poly_period`, plus a
gate-6 grid test pinned at the failing cells. The precedent for scoping is
c27-C's phase fix, which was one line and one bound.

---

## F2 — kosmische has no lead, and BRIEF says it should

### Measured

A 480 s kosmische track contains exactly two event kinds — `drone` and
`pluck` — and every one of its six sections declares the same instrumentation:

```
intro/build/break/drift/return/outro -> instr=['drone','pluck']  (constant)
event kinds: ['drone', 'pluck']
instruments: ['drone', 'motif', 'pluck']
```

BRIEF §5 says kosmische is "two-oscillator detuned lead enters at section
3+" and §4's T16 harmony rule assumes a melodic voice above the drone. There
is no sustained melodic voice in the lane at all: the 13 technique cards are
pad, poly_period, drone, frippertronics, dub_chain, pluck, kick, snare, hat,
bass, pink, deja_vu, lane. **No lead voice exists anywhere in the composer**,
so the brief's named feature cannot fire.

This is 25 % of the catalogue by weight, and it is the lane the audit calls the
"cosmic" one. A track that is drone plus arpeggios for eleven minutes has no
payoff; the lead entering at section 3 is the payoff.

### Options

**A. A `lead` card on the pad's synth (recommended).** The pad already renders
a detuned partial stack with slow attack — which is literally "two-oscillator
detuned". A lead is a second pad-like voice with a brighter, narrower partial
set (quartal + add9, 2–3 partials, ±4–8 cents detune), a slower LFO on pitch,
and a filter. It enters by *instrumentation* at a drawn section index (3+),
which makes it plan data and lets the section differ on the instrumentation
dimension for the first time. No new DSP primitives.

**B. A new KS-based lead.** Reuses the plucked string with a long decay and a
detuned pair. Cheaper to justify musically (it is a string), but a plucked
voice cannot sustain, and the brief says *lead*, not *guitar*. It also flirts
with the "one instrument, two cues" confusion already present in the station's
chorus pair.

**C. Let the motif pluck louder.** No new voice, no instrumentation change, no
payoff. Rejected: it is the "tune it against the gate" failure mode.

### Recommendation and falsifier

A. Declared falsifier: *kosmische sections 3+ must carry a distinct
instrumentation state, the lead must be measurable in the 200 Hz–2 kHz band
as sustained energy (not onsets), and gates 5/6/7 plus LRA must hold at 480 s
and 900 s.* Cost: ~200 lines, one preset key for every lane that wants it,
gates re-measured on two lanes (kosmische and, if used, dub's stabs).

The risk to watch is LRA: a sustained voice that sits at one level can *lower*
the range, and a voice that swells can break the 4–12 band. Measure before
choosing the swell depth.

**SHIPPED as c37** (issue #36). Spiked first: LRA 10.553 → 10.449 and every gate
green before a line of the card was written. Acceptance matrix, 480 s and 900 s
over three seeds: LRA 9.906–11.325, gates 1–13 PASS in all six cells. Two things
would have shipped broken and are pinned by tests: the deck's
`transpose_up_fourth` covered `[pad, drone]` and would have left the lead in the
old key under a transposed bed (18 of 30 seeds draw that move), and a subclass
cannot narrow a `Literal`, so the lead is a sibling event with a
`SustainedEvent` union rather than a PadEvent subclass. Audio outside kosmische
is bit-identical (motorik `29158df2`, dub `b079db6a`, ambient `b727794a`).

---

## F3 — The rotation: weights are a mix policy, coverage is a coin flip

### Measured

`pick_lane` draws each track independently from the station's weights
(motorik 30, kosmische 25, ambient 20, dub 15, indie-noise 10). Simulated over
thousands of batches (`pick_lane` only — no rendering):

| batch size | motorik missing | kosmische | ambient | dub | indie-noise |
|---|---|---|---|---|---|
| 7 | 7.7 % | 14.2 % | 20.3 % | 31.3 % | **51.0 %** |
| 11 | 1.6 % | 6.0 % | 6.3 % | 17.0 % | **34.9 %** |
| 12 | 1.2 % | 3.9 % | 6.0 % | 14.4 % | **31.7 %** |
| 20 | 0.0 % | 0.0 % | 0.5 % | 5.0 % | **16.5 %** |

The real 2026-10-25 batch (seeds 5000–5010) drew ambient, motorik ×5,
kosmische ×2, dub ×1, indie-noise 0 — a 31.7 %-likely outcome, not bad luck
worth blaming on the seeds.

Note that forms *are* stratified already: `batch_forms` spreads 60/25/15 over
the batch deterministically. Lanes are the only dimension left to chance.

### Options

**A. Stratify the lanes the way forms already are (recommended).** Allocate
lanes by largest-remainder on the weights — for 12 tracks: motorik 4,
kosmische 3, ambient 2, dub 2, indie-noise 1 — then spread them across the
seeds so they do not clump. Every batch then has every colour and the
proportions still hold. **Cost: a semantic change.** The lane would stop being
a function of the seed alone and become a function of (seed, batch), so seed
5005 means dub in one batch and ambient in another. That breaks the property
that a seed names a track.

**B. Keep the draw, choose the seed window (recommended instead).** The batch
searches for a `seed_base` whose draw covers every lane, starting at the
requested base and stopping at the first hit. `pick_lane` needs only the
preset and the seed, so the search costs microseconds — no rendering. The
seed→track property survives, and the batch reports the base it used. The
distribution of lanes is then the weighted draw *conditioned on coverage*,
which is exactly the policy we want and is honest about what it did.

**C. A `--lane` override per track.** Manual, and it puts the curator's taste
in a flag. Useful as an escape hatch, not as the policy.

### Recommendation and falsifier

B, with C as an escape hatch. Falsifier: *a batch of 12 at any requested base
must cover all five lanes, the drawn proportions must stay within one track of
the weights, and a batch must still refuse to duplicate seeds already in the
library.* Cost: small — `batch.py` seed selection plus a test over 200 derived
bases.

**SHIPPED as c35.** `covering_seed_base` searches the window; `lane_for` reads
the lane without composing (the composer's first draw, mirrored and pinned by a
test); the search is blind to the library so the duplicate refusal survives. The
2026-10-25 request (seeds 5000 × 12) now resolves to base 5002, which does carry
indie-noise. Measured: 12 of 12 tests, and the draw still follows the weights to
within 4 points over 120 windows.

---

## F4 — `install` copies no sidecar, so the catalog is a silent zero

### Measured

`install()` copies only the `.flac`
(`install.py:60`, `_copy_atomic(flac, target_dir)`). `catalog` reads
`*.json` sidecars, so on a freshly installed directory it reported
`tracks: 0` — a *success* message over an empty index. The previous rotation
had sidecars only because someone copied them by hand.

### Options

**A. `install` copies the sidecar next to the file (recommended).** It is part
of the track: the catalog, the dupe check and every future query depend on it.
Atomic for both files, and a missing sidecar becomes a refused track rather
than a silent gap.

**B. Make `catalog` refuse to write when flacs have no sidecar.** A guard, not
a fix: it turns a silent lie into a loud error. Worth doing *as well*.

### Recommendation

A + B, one small change each. No musical impact; it is the difference between
a library you can query and one you cannot.

---

## F5 — What is NOT a gap (measured, so nobody spends a week on it)

These were candidates for "make the music greater" and they are already right:

- **Harmony colour.** Per section, motorik/kosmische/indie-noise/dub use a
  median of 7–9 distinct pitch classes with the root present, and interval
  content is **quartal/quintal** (P4+P5 outnumber thirds in all four lanes:
  59 vs 46, 61 vs 38, 58 vs 43, 56 vs 42). That is BRIEF §6's "no chords, use
  quartal stacks and add9". Adding chord progressions would fight the brief,
  which explicitly forbids I–V–vi–IV and pop cadences.
- **Harmonic rhythm.** BRIEF T16 says shifts happen at section boundaries,
  never mid-bar, every 16–64 bars. Measured: 3–4.3 distinct (mode, root)
  centres per 480 s track, one per section — inside the brief. Motorik holds
  50–64 bars, which is the slow end of the band, but it is *inside* it.
- **Evolution.** 480 s tracks carry 16–22 Director moves (motorik, dub), 8–12
  (kosmische, indie-noise), 3–5 (ambient), 4–6 distinct textures and densities
  per track. The arrangement does evolve; T14 is doing its job.
- **Motif discipline.** 116–174 motif events and 22–40 recorded appearances per
  track, with only 3–5 of 47–54 sections marked as a reprise — repetition is
  rare, as BRIEF demands.

Two things flagged earlier are also not worth a change now:

- **The duck keyed on grid frames** leads the bass by ≤ 12 frames (0.27 ms).
  Below audibility; the measured cost of re-keying it (9.4e-2 in the 200–500 Hz
  band) buys nothing a listener can hear.
- **`RENDER_BLOCK`** is a memory dial, not a musical one. Safe now, measure
  later when memory is the binding constraint.

---

## Order, by musical impact per unit of risk

| # | change | why now | risk |
|---|---|---|---|
| 1 | F3-B, seed-window coverage | every future batch is better; no audio moves | low |
| 2 | F2-A, the lead | 25 % of the catalogue gains its payoff; the brief already asks for it | high — new voice, gates |
| 3 | F1-A, the ambient noise floor | unblocks the interlude band; fixes the music rather than the gate | medium — ambient PCM at short durations |
| 4 | F4, sidecars | library hygiene | nil |

F1 is deliberately *after* F2: if the lead ships for kosmische and dub, the
ambient's loop-constraint fix will be measured against a tree that already
moved, and the gate grids should be re-derived once rather than twice.

## The one thing to do first

Start F3-B, because it is small, it touches no audio, and it makes the *next*
batch demonstrably better — including the demo batches used to judge F2. The
pre-declared falsifier for it is above, and the property it must not break is
that a seed names a track.

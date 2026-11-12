# c17 — chord selection by measured consonance (issue #17)

## What this slice is

Issue #17 asks for chord choices to be **scored against the spectra the
synth will produce**, not only scale-filtered. This slice builds the
measurement, wires it into the composer and **turns it on**: the harmonic
centre of every track now stands on a root whose chord the lane's own
spectrum can voice cleanly.

The scorer is `src/indiegen/theory/consonance.py`: Sethares' critical-band
roughness curve, evaluated on the spectrum a chord would actually sound, in
integer permille.

## The four decisions that make the number mean something

**Register-fair.** The comparison happens at one reference pitch (MIDI 36),
so the score says which chord *shape* is cleanest, not which octave it sits
in. Sethares' bandwidth is in absolute Hz, so a shape scored at its own
register reads rougher the lower it sits; without the reference pitch the
scorer would simply pick the top of the scale, which is the opposite of what
a consonance test is for. The register is the arranger's business — the CP
progression and the voice-leading walk both choose it.

**Per-pair, not per-sum.** The roughness is averaged over the pairs of tones
that belong to *different* tones of the chord, so a chord is not scored worse
merely for having more notes. A note's own partials are consonant by
construction: what a chord is judged on is the beating *between* its notes.

**Per-voice, weighted by the pairs.** A lane's chord is sounded by every
additive voice it has, and a voice with nine partials beats against itself
and against the other voices far more than a voice with one. The chord's
score is the weighted mean of the voices' scores, weighted by the number of
partial pairs each voice contributes.

**A fragment is not a chord.** A root whose chord falls below three tones is
not a candidate: it has fewer pairs to beat, and would therefore look
cleanest of all. The scorer would then prefer the root that voices least of
the chord — measured, not guessed: without the floor the candidate root 72
in a C-major scale scores 0 and wins every time.

## What the lane declares

Each lane declares the sonority its harmony is built on, as semitone offsets
from the root (`chord_intervals`, 3–5 pitch classes). The declarations come
from the BRIEF, not from taste:

| lane | declaration | where it comes from |
|---|---|---|
| ambient | *(the poly-period card's own chord, `[0, 3, 5, 7, 10]`)* | the card already declared it |
| motorik | `[0, 7, 2]` | BRIEF 5: "one chord for 32–64 bars" over a bass with "fifth passes at phrase ends", plus BRIEF 6's "quintal stacks and add9 colour" — root, fifth, ninth. In all three of the lane's modes. |
| kosmische | `[0, 7, 2]` | the lead's palette, BRIEF 5 / c37: "detuned pair, fifth and add9" — root, fifth, ninth. In both of the lane's modes. |
| dub-electronic | `[0, 3, 7, 10]` | BRIEF 5: "minor/minor-9 chord stabs pitched down" — the minor ninth's voicing without its ninth: root, minor third, fifth, minor seventh. Diatonic to both of the lane's modes. |
| indie-noise | *(none, on purpose)* | BRIEF 6 makes this lane's dissonance deliberate ("indie-noise clusters"). A consonance score would be fighting the brief, so the lane declares no chord and the scorer has nothing to say about it. |

## The calibration, measured

The score of each lane's declared sonority against that lane's own voices,
at the reference pitch:

| lane | roots that can carry it | score (permille) | the roots the scale truncates |
|---|---|---|---|
| ambient | 5 of 8 | 32 | 42 (four tones), 48 (three tones) |
| motorik | 7 of 16 | 11 | — |
| kosmische | 6 of 16 | 31 | — |
| dub-electronic | 4 of 16 | 31 | 42 (three tones) |

Two things fall out of the measurement.

**The fuller chord is usually the cleaner one.** ambient's five-tone chord
scores 32 where its four-tone truncation scores 42 and its three-tone
truncation 48: the tones the scale drops are the ones the spectrum beats
against. That is why the scorer can rank a truncated chord below a whole
one, and why the floor above is a floor and not a filter.

**The BRIEF's harmonic vocabulary is measurably cleaner than a triad.** The
same shapes measured against the same drone spectrum: a quartal stack
`[0, 5, 10]` scores 16–18, a minor triad `[0, 3, 7]` scores 35–42. The
research doc measured this from the other side — "P4+P5 outnumber thirds in
all four lanes" — and the spectral measurement agrees: the drone's just
ratios (9/8, 5/4, 4/3) beat against the minor third and not against the
fourth. The lanes were already singing what the score says.

## The activation

The switch is **on by default** (`StationPreset.consonance_scoring_enabled`,
code-only, the c12 precedent). The harmonic centre is drawn from the roots
whose chord the lane's spectrum can voice cleanly instead of from the whole
scale. The draw is the same RNG draw the legacy path makes, so the switch
changes the root and nothing else — the rest of the track is untouched. The
measured effect, 45 s, seed 1042:

| lane | the legacy pool | the scored pool | the harmonic centre moved |
|---|---|---|---|
| ambient | 8 | 5 | 57 → 50 |
| motorik | 16 | 7 | 57 → 53 |
| kosmische | 16 | 6 | 50 → 55 |
| dub-electronic | 16 | 4 | 39 → 43 |
| indie-noise | 16 | 16 | unchanged (no sonority) |

The gates hold: the sweep over five lanes × three seeds × 240 s (gates 4, 5,
6, 7, 13) is 15/15 green with the switch on. The lane's timbre tables were
measured against the old harmony and they still hold — gate 6 asks for a
correlation of 0.4 between the delivered per-section centroid and the
planned curve, and moving the harmonic centre did not move the delivered
curve away from the plan.

### The tolerance, measured

`consonance_tolerance_permille` is how much rougher than the cheapest
candidate the arranger accepts. The worry was that a tolerance of 0 makes
the harmonic centre deterministic per lane, because the scores differ
wherever the scale truncates the chord. Measured over five seeds:

| lane | eligible at 0 | distinct centres over 5 seeds |
|---|---|---|
| ambient | 5 roots | 3 |
| motorik | 7 roots | 3 |
| kosmische | 6 roots | 4 |
| dub-electronic | 4 roots | 4 |

So 0 is enough: the eligible pool is four to seven roots wide, the draw
still varies, and the tracks of a lane do not all start on the same note.
The tolerance stays at 0 — the strict reading, "the harmonic centre stands
on a root where the lane's chord sounds whole".

### The CP progression, measured and left alone

The scorer governs the harmonic centre; the progression's later roots are
still drawn from the whole scale, so a section can land on a root that
cannot carry the lane's sonority (measured: two or three of the four to six
section roots, per lane and seed). Three things say that is right rather
than a hole:

- **The BRIEF asks for neighbouring roots, not palette roots.** T16: the
  harmonic centre moves "among related modes … on the same or neighboring
  roots", and the seven-semitone voice-leading limit already enforces it.
- **The truncation is the designed rule.** Where a root cannot carry the
  whole chord, the chord is the prefix the scale admits — the same rule the
  poly-period voice has always applied, and the reason the chroma budget
  exists.
- **Narrowing the domain would cost the variety.** The solver is not
  starved over the palette (475–2048 solutions per lane), but the ambient's
  CP already has only three to six solutions over its own domain; narrowing
  it to the five roots that carry the chord whole would leave the ambient's
  tracks sharing nearly the same progression.

So the CP's domain stays the whole scale, and the coherence is bought where
it is audible: the track's harmonic centre stands on a root that carries
the lane's chord, and in the ambient the poly-period's chord is whole at
the centre instead of truncated.

## What is still open

1. **The harmonic centre is the only thing the scorer governs.** The
   progression's roots, the chord segments inside a section and the
   director's transposes are all still free. Whether the sonority should
   follow the progression is the next question, and it is bigger than the
   activation.
2. **The tolerance is a tolerance, not a shape choice.** The lane declares
   one sonority. A lane that offered two (a quintal stack and a quartal
   one) would let the score pick the shape per track, which is the bigger
   prize the issue is aiming at.
3. **The score is blind to the voices that have no partial list.** The
   plucked string and the bass are not in the lane's spectrum: their
   spectrum is not a list of partials, and inventing one would put a number
   in the plan that nothing measured. The dub lane's chord stabs are
   exactly that case.

Issue #17 stays open.

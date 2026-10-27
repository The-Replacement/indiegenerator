# c38 — gate 7 is two-sided

Issue #32 asked for a gate 7 that does not count a sustained build cluster as a
section change. The first attempt (e1582bf) restricted peaks to a window around
planned boundaries and was reverted (3055593): it failed motorik and kosmische
at 45 s and did not fix indie-noise. The measurement that followed found a
different defect.

## The defect: the flux only looked up

`spectral_flux` summed `max(mag_t - mag_{t-1}, 0)` in decibels — the half-wave
rectified flux, an onset detector. A section that gets **quieter** produced no
flux at all. indie-noise's outro is documented as "a cut to near silence", so
the lane's clearest novelty event was invisible.

Measured at 45 s, seed 1042, on the mastered PCM (gate 7 reads the master, not
the mix), sections at 0 / 9.6 / 22.5 / 35.4 s:

| boundary | flux | threshold | clears |
|---|---:|---:|---|
| 9.6 s (wall enters) | 222836 | 107505 | yes |
| 22.5 s (denser wall) | 92171 max ±3 s | 107505 | no |
| 35.4 s (the cut) | 28681 | 107505 | no |

Two peaks against a limit of three.

## What was measured and rejected

**Plain absolute difference** (`sum(|diff|)`, one threshold on its own curve).
It fixes the fade and puts motorik's four peaks exactly on its four boundaries
at 45 s — but over 5 lanes × {45, 60, 90, 120, 480} s × 3 seeds it turned two
green cells red, because the absolute curve's higher median raises the
threshold:

| cell | rectified | absolute | limit |
|---|---:|---:|---:|
| kosmische 60 s, seed 1042 | 6 | 2 | 4 |
| dub-electronic 60 s, seed 3005 | 5 | 4 | 5 |

The pre-declared falsifier fired; the variant was dropped.

**Absolute curve, rectified threshold.** Degenerate: the absolute curve sits
above the one-sided threshold almost everywhere, so the whole curve is one
cluster and the count collapses to 1 on every cell measured.

**Boundary filtering of all peaks** (the reverted e1582bf). Fails motorik and
kosmische; fixes nothing.

## What shipped

`spectral_flux_pair` returns the rises and the falls in one FFT pass.
`check_gate_7` counts:

- every rise peak, exactly as before (no green cell can turn red: the count is
  the rise count plus a non-negative term), and
- a fall peak only when it lands within the 4 s merge window of a planned
  section boundary and is not already within that window of a rise.

A fall inside a section — the track's own fade-out, a drum decay — is not a
section change. A fall at a boundary is.

The threshold is still the median + 2·1.4826·MAD of the **rises** curve, so
the sensitivity does not move; only the events that can count change.

## Measured after

Twelve cells, seed and duration chosen to cover every pre-existing red cell and
both cells the absolute variant broke:

| cell | rise peaks | + boundary falls | limit | verdict |
|---|---:|---:|---:|---|
| indie-noise 45 s, seed 1042 | 2 | 1 | 3 | pass (was FAIL) |
| indie-noise 45 s, seed 2000 | 2 | 3 | 4 | pass (was FAIL) |
| indie-noise 45 s, seed 3005 | 2 | 2 | 3 | pass (was FAIL) |
| indie-noise 60 s, seed 3005 | 2 | 2 | 3 | pass (was FAIL) |
| kosmische 45 s, seed 2000 | 2 | 2 | 3 | pass (was FAIL) |
| kosmische 90 s, seed 2000 | 3 | 2 | 5 | pass (was FAIL) |
| motorik 45 s, seed 2000 | 4 | 1 | 5 | pass (was FAIL) |
| motorik 60 s, seed 2000 | 3 | 1 | 5 | **FAIL** (unchanged) |
| kosmische 60 s, seed 1042 | 6 | 0 | 4 | pass (regression avoided) |
| dub-electronic 60 s, seed 3005 | 5 | 0 | 5 | pass (regression avoided) |
| ambient 45 s, seed 1042 | 6 | 0 | 3 | pass |
| motorik 45 s, seed 1042 | 4 | 2 | 4 | pass |

Seven of the eight pre-existing red cells in the 75-cell corpus now pass; one
still fails, so the gate still bites. Every added fall was within 4 s of a
planned boundary by construction; the added times were checked against the
plans (e.g. indie-noise 2000 45 s: 21/25/37 s against boundaries 18/27/36 s).

## Tests

`tests/test_validate.py`:

- `test_a_piece_that_falls_to_silence_is_novel` — tone, silence, quieter tone,
  silence. The rectified detector finds 1 peak (limit 3); the two-sided one
  finds 3.
- `test_a_fall_that_is_not_a_section_boundary_is_not_novelty` — a drop 2 s into
  a 10 s section does not count.

## What did not change

No Plan field, no preset key, no plan hash, no PCM golden. Gate 7 reads the
mastered PCM; nothing is written.

## Left open

- motorik 60 s, seed 2000 still fails (4 against 5). It is a real cell, not a
  detector artefact: the plan draws six sections at 60 s and the piece does not
  produce five boundary events.
- The corpus red cells are recorded in this change's sweep; they predate it.
- Issue #7 (ambient gate 6 at 48 s) is re-opened: its fix (d8c057d) was
  reverted in 22be56b because the period cap cannot satisfy BRIEF T1's 15–90 s
  distinct-period rule at interlude durations, and it shipped a failing test.

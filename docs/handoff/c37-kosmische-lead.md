# Handoff — c37: kosmische gets its lead

## What changed

BRIEF §5 gives kosmische "two-oscillator detuned lead enters at section 3+".
The voice did not exist: the lane's six sections all carried `['drone','pluck']`
and the composer had no lead card at all, so 25 % of the catalogue ran six to
eleven minutes of drone and arpeggios with no third act (issue #36).

- `plan.py`: `LeadEvent` — the pad's field set with `kind: Literal["lead"]` —
  and `SustainedEvent = PadEvent | LeadEvent`, which the additive synth now
  accepts. `Event` gains `LeadEvent`.
- `config.py`: `LeadCard` (partials, detune range, LFO, amplitude, min_density,
  entry_section, pan, attack/release seconds). It joins the `TechniqueCard`
  union and `CARD_SPECS` as `("lead", "lead", _min_density_card)`.
- `planner.py`: `_lead_events` — one lead per entered section, over the whole
  section rather than per chord segment, from `LEAD_RATIOS` (the detuned pair,
  a fifth, an add9, an octave), with both fades bounded by a quarter of the
  section.
- `render.py`: `case "pad" | "lead"` in the two dispatches. **No new DSP**: the
  lead is the pad's additive synth.
- `presets/kosmische.yaml`: the lead, `entry_section: 3`, `min_density: 40`,
  −14 dB, pan −120, 2 s attack, 3 s release.
- `presets/station.yaml`: `transpose_up_fourth` applies to `[pad, drone, lead]`.

## The two things that would have shipped broken

**The deck transposes the bed and would have left the lead behind.**
`transpose_up_fourth` splits `[pad, drone]` at the move and transposes the tail
up a fourth. A lead that is not in that list stays in the old key over a
transposed drone — two keys at once. Measured: **18 of 30 kosmische seeds draw
that move**, so it is the common case, not a corner. The fix is one token in
`station.yaml`, and `test_the_lead_moves_with_the_bed_it_sits_on` walks 30 seeds
and fails if none of them moves.

**A subclass cannot narrow a `Literal`.** `LeadEvent(PadEvent)` with
`kind: Literal["lead"]` is rejected by mypy (`Incompatible types in
assignment`). The voice is a sibling with the same fields, and the synth takes
the `SustainedEvent` union instead.

## Why the lead leaves for the outro

Entry is `section >= 3` **and** `density >= min_density`. Kosmische's outro is
density 25, so the line exits with the return section instead of playing under
the fade. That is a musical decision, not a gate: the brief asks for it to
*enter*, and a lead that outlasts the piece is a different arrangement.

## Verification

The spike came first, with the falsifier declared before the code: *if LRA
leaves 4–12, the lead needs a level curve before it ships.*

| kosmische, seed 1042, 480 s | loudness | LRA | true peak |
|---|---|---|---|
| before (no lead) | −16.058 LUFS | 10.553 LU | −4.298 dBTP |
| spike voice over 3 sections | −16.073 LUFS | 10.449 LU | −4.299 dBTP |

Acceptance matrix, 480 s and 900 s, three seeds (`/tmp/opencode/research/c37_matrix.py`):

| seed | 480 s LRA | 900 s LRA | gates |
|---|---|---|---|
| 1042 | 10.277 | 11.325 | PASS |
| 2000 | 9.906 | 10.777 | PASS |
| 3005 | 11.266 | 10.628 | PASS |

Every cell inside 4–12 LU and every gate 1–13 green.

**Audio outside kosmische did not move.** The station deck's `applies_to` is
plan data, so adding `lead` to it moves the plan bytes of every track, but not
their sound: the pre-c37 mix hashes are unchanged — motorik 20 s
`29158df2`, dub-electronic `b079db6a`, ambient `b727794a`. The plan golden
`plan_motorik_1042` is re-derived (`16c9d549`) for that reason alone.

Tests: 10 in `tests/test_c37.py` (entry by section, exit by density, the
detuned pair and its quieter colour tones, one line per section, fades bounded,
no lead in short forms, opt-in per lane, the deck moves it, the pad synth
renders it, and a slow gate/LRA test). Suite: 673 fast / 6 slow.

## Open, and deliberately not done

- The lead is **not** added to the other lanes. It exists as a card; a lane that
  wants one declares it.
- `_playing_ranges` still lists the lead from its density floor rather than its
  entry section, so a Director strategy that named `lead` would be allowed to
  draw before section 3. No strategy names it today; the day one does, that
  function needs the entry section.
- The lead's own timbre is not in the lane's `timbre` table, so gate 6's
  predicted curve ignores it. That is why gate 6 stays green; a lead that
  brightened the lane's centroid by design would need a row there and a
  measured curve.

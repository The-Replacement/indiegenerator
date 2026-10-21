# Handoff: `s3-arranger`

**Status: complete.** The arranger, the section graph, the tension curve, the
motif and its transforms, the Director as an arranger, the modal shifts, the
Frippertronics, the dub chain, and gates 5, 6 and 13.

Read this before the next session. Everything below was measured on this
machine on 2026-10-21, not assumed.

**The verdict: APPROVED, with one criterion open (AC-19, the dub lane's
novelty over four seeds, which was open when the slice started).** The
independent review is in `sdd-s3-arranger-judgment`; the criteria table is in
`sdd-s3-arranger-verify`.

---

## 1. What the slice is

BRIEF §15, S3: "section graph, tension curve, motif transforms, T14, T16,
kosmische + dub (T3, T10), 6–8 min pieces", with gates **+5, 6, 13** in
force. BRIEF §15 also says, in one line: **"S3. The arranger. Make-or-break.
Stop and ask."** That is the checkpoint this handoff ends at.

The acceptance criteria are the twenty in the memory record
`sdd-s3-arranger-spec`; the implementation is the eleven tasks in
`sdd-s3-arranger-tasks`; the deviations are D-1 to D-4 in the spec.

## 2. The state of the repo

`master`, clean tree at the `chore: refresh the n3rv project metadata` commit
(the n3rv refresh ran and changed nothing, so the commit is empty). 343 tests
pass. `ruff check`, `ruff format --check` and `mypy --strict` on `src/` are
clean.

**There is no git remote.** The project is local only. There is no GitHub
repository, so no issue can be created and no SDD phase can be tracked on the
project board. The board the `project-board` skill describes (project #2) is
the *Reverberage Roadmap* under the org `reverberage`, and it holds no
indiegenerator items. Either create the repo and fix the skill's owner, or
drop the board integration. It is not this slice's job.

## 3. The five lanes, and what they are now

| Lane | Piece | What it is made of |
|---|---|---|
| `motorik` | 7 min | the drums (T6), the sub, the deja-vu stabs (T5), the pad, the 1/f (T7), the motif |
| `kosmische` | 7 min | the T11 drone, the T5 arp, the **T3 Frippertronics** send |
| `ambient` | 7–8 min | the T1 poly-period loops, the T11 drone, the T13 clusters, the motif |
| `dub-electronic` | 7 min | the T6 drums, the sub, the minor-9 stabs through the **T10 dub chain**, the **sidechain to the kick** |
| `indie-noise` | 7 min | the T13 clusters, the noise wall, the motif |

The lane presets declare a duration range of 360–480 s and a section count of
4–6 (2–4 for the ambient).

## 4. The decisions that matter, and why

1. **The section graph is a graph.** `presets/station.yaml` holds eight
   nodes — intro, build, plateau, peak, break, drift, return, outro — each
   with its successors, its density, its level (the tension curve), its
   length in bars and the section it reprises. The composer *walks* it: the
   walk starts at the intro, follows the declared successors and ends at the
   outro. A list of profiles could not express a reprise, and a reprise is
   what "transformed reprise only" needs.
2. **No two sections in a row may be the same arrangement.** The composer
   asserts that consecutive sections differ in at least two of the five
   dimensions BRIEF §6 names (instrumentation, harmonic center, rhythmic
   pattern, density, texture) and raises `PlanError` when they do not. The
   rhythm differs because the drum pattern turns by a step per section; the
   harmonic center because the mode shifts at the section boundaries.
3. **The motif is played, not declared.** The cell is a Karplus–Strong phrase
   that comes back every eight bars (every 30 s in a lane with no pulse),
   transformed: transposed, inverted, reversed, stretched or cut. The first
   statement is the cell as it is; every other one wears a transform, so the
   motif comes back without ever coming back the same. The plan records every
   appearance, and gate 13 counts the transformed ones.
4. **The Director draws, the Director applies.** `compose()` draws the moves
   from the station's strategy pool — every 8 to 32 bars in a pulsed lane,
   every 60 to 180 s in a lane with no pulse — and `director()` applies them
   as a pure `Plan -> Plan` transform, which BRIEF §8 demands. A strategy that
   names instruments the lane does not have is not drawn: a move that could
   not change anything would be a move that did not fire.
5. **The Director's strategies** are `transpose_up_fourth`, `transpose_motif`,
   `invert_motif`, `retrograde_motif`, `drop_drums`, `drop_kick`,
   `half_time`, `drop_bass`, `solo_texture`, `swap_delay_to_triplets` and
   `reharmonize_relative`. Each one is a pure function over the plan.
6. **The modal shifts are section events.** Every section carries a mode and
   a root; the shift never lands mid-bar, and the techniques that choose
   pitches (the deja-vu, the bass) read the section's own scale, so a shift
   is heard in the notes and not only in the metadata.
7. **T3, the Frippertronics, is a send on the main bus.** A 3–6 s feedback
   delay at 0.65–0.85, every pass lowpassed 200 Hz lower than the last and
   saturated, with the tape wow on the read position. The number of passes a
   sample has made is tracked exactly, with an integer counter beside the
   audio line, so the darkening is per pass and not an approximation.
8. **T10, the dub chain, is on the KS bus**, before the dotted-eighth delay:
   the stabs are bit-reduced to 8 bits, bandpassed at 450 Hz with a 1/f drift
   on the cutoff, and everything but the kick is ducked by the kick.

## 5. The gates that came with it, and the two measurements that had to change

- **Gate 5** (the energy trajectory) compares the delivered per-second RMS
  with the plan's section level curve, Pearson ≥ 0.5. Measured: 0.865 to
  0.982 across the five lanes.
- **Gate 6** (the timbre trajectory) compares the delivered spectral
  centroid, measured *per section*, with the plan's predicted centroids,
  Pearson ≥ 0.4. The plan's prediction is the lane's own recipe: each lane
  declares what each kind of section sounds like, in hertz, measured on real
  renders of that lane (BRIEF §5: "starting specs, measured, then tuned").
  A lane that declares a flat map is a lane that declared a static timbre,
  and the gate then measures the variance instead.
- **Gate 13** is three plan-level checks: the motif's transformed
  appearances (≥ 3), the Director's rate (≥ 1 fire per 32 bars in a pulsed
  lane) and the deja-vu's replay probability (it has to move).

Two measurement decisions are worth knowing, because both were found by
measuring and not by reasoning:

- **The trajectory gates measure the pre-master mix, not the delivered PCM.**
  The dither is a ±1 LSB of white noise spread over the whole spectrum, and
  it is enough to drag a spectral centroid up by kilohertz: the kosmische's
  measured centroid was 5952 Hz with the dither in and 1308 Hz without it.
- **The spectral centroid is compared per section, not per second.** The
  per-second centroid of a section that holds a poly-period loop swings with
  the loop's on-window, and that swing says nothing about the section's
  timbre.

## 6. The defects found and fixed in this slice

The judgment-day review (an independent reviewer, blind to the
orchestrator's own findings) found six real defects, and the seven-minute
measurement found a seventh. All seven are fixed, in the commit
`fix(s3): the arranger's moves compose, and the ending keeps its material`.

- **The Director applied only its last move.** Every move was applied to the
  *original* plan and the result overwrote the previous one, so a track that
  logged eight moves held the effect of one. The moves now apply to the
  running plan, one after the other.
- **Gate 13 was tautological.** It counted the *drawn* moves, and the draw's
  interval is at most 32 bars, so the inequality held by construction. It
  counts the *applied* moves now, and a move is not drawn where its
  instruments do not play.
- **The ending could be emptied.** A drop that ran into the last bars took
  the drums away and left twelve seconds of silence: the seven-minute dub
  render failed gate 8. The last three seconds of a track keep their
  material now.
- **The tape wow was a length ratio and not a pitch ratio**, so the wobble
  grew with the wow's rate: 2.5 % at 0.8 Hz against the brief's 0.8 %. The
  travel of the read position is now scaled by the rate.
- **The Director inverted the motif around the wrong axis** — the first
  section's root instead of the section the appearance is in — so the plan's
  appearance and the plucks that play it disagreed.
- **The gate 13 bar count was four times too high**: the meter is a count of
  beats over a note value, so 4/4 is four quarter-note beats to the bar, not
  one.
- **The modal shift could be held for 150 bars**, and the sections were
  longer than the 64 bars the brief allows a mode to be held for. Both are
  fixed, and a reprise now really takes the relative mode of the section it
  reprises.
- **The dub chain's Q and its send level were never read.** Both are read
  now.
- **The section lengths could go negative** on a short track: the snapping
  to four-bar multiples can overshoot the track, and the last section took
  the remainder.

## 7. The open items, in the order they matter

1. **Gate 7 is still seed-sensitive.** The dub lane gave 14 novelty peaks
   for seed 1042 and 2 for seed 1046 against a limit of 3 in S2. The
   arranger gives the piece real section-level changes now, which is the
   root cause, but the gate has not been re-measured across seeds — the
   five lanes at 90 s pass, and the seed sweep is still open. This belongs
   to S4 or to a fix in the detector's threshold.
2. **Nobody has listened to any of it.** The gates measure the shape of the
   arrangement, not whether it is any good. The brief's listening protocol
   (S6) needs human ears, and the first thing to ask for is the three
   tracks with timestamps.
3. **The S1 verify still owes a second pair of eyes.** The S1 remediation
   table was re-audited by the orchestrator, because the `sdd-verifier`
   subagent died four times under load. S3's review was done for real: an
   independent reviewer found six defects (the Director's cumulative
   application, the tautological gate, the empty ending, the dead dub
   fields, the wow's ratio and the unrealised reprise), and they are all
   fixed. The table is in `sdd-s3-arranger-judgment`.
4. **The board does not track this project** (see §2).
5. **S4** is the mix and master: the limiter as a mastering stage, the
   loudness gates, the sub-bass balance, the codec gate, all of §11. **S5**
   is the catalog and `install`. **S6** is the taste pass.

## 8. The measurements this slice is judged by

Seven-minute pieces, seed 1042, one process each (the README's table has the
same numbers with the hashes):

| Lane | Render time | Peak RSS | Loudness | Peak | True peak |
|---|---|---|---|---|---|
| `motorik` | 18.6 s | 1045 MB | −31.610 LUFS | −18.003 dBFS | −17.758 dBTP |
| `kosmische` | 71.5 s | 1113 MB | −31.979 LUFS | −18.001 dBFS | −17.995 dBTP |
| `dub-electronic` | 30.7 s | 1113 MB | −33.071 LUFS | −18.001 dBFS | −17.995 dBTP |
| `indie-noise` | 9.1 s | 1113 MB | −44.568 LUFS | −18.001 dBFS | −17.995 dBTP |
| `ambient` (8 min) | 52.5 s | 1180 MB | −34.845 LUFS | −18.001 dBFS | −17.995 dBTP |

Budget: an 8-minute track in ≤ 3 minutes, peak RSS ≤ 1.5 GB. Both hold, with
the kosmische the slowest lane: the Frippertronics' line is walked one sample
at a time in Python, at about 0.18 s per second of stereo. It is 60 % of the
kosmische's render time, and it is the first thing to optimise if S4 needs
the headroom.

The `indie-noise` lane is 13 LUFS quieter than the others. It is a noise
wall with a guitar over it, and the loudness gate is S4's business.

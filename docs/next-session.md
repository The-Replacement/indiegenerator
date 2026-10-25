# The next session's prompt

Copy the block below into a fresh session. It is self-contained: it carries
the state of the project, the decisions already made, the deviations already
declared, and what is left. Nothing in it needs the conversation that
produced it.

---

```text
You are taking over indiegenerator: a deterministic, offline, batch music
generator that makes tagged tracks for a private internet radio. The
repository is /home/estrocondoso/Repositories/indiegenerator. The
authoritative brief is BRIEF.md in the repository root - read it, it is the
contract (especially 6, 8, 11, 15, 16 and 18). Do not modify it.

=====================================================================
THE STATE
=====================================================================

master is at d199dcb (docs(c32): re-derive the indie-noise row of the
measured table). Clean tree. ruff check ., ruff format --check . and mypy
src are clean. pytest -q -m "not sweep": 581 passed, 15 deselected.
pytest -q -m sweep: 15 passed. pytest -m slow: 4 passed.

Slices S0-S5 and changes c21-c32 are done and archived in memory under the
topic keys sdd-<change_id>-{context,proposal,spec,design,tasks,impl,verify,
done}. The recent ones, most useful first:
  sdd-c32-short-form-trajectory-done   (the interlude band, three commits)
  c3336862  the density gate that leaked across section boundaries
  c32-density-scale-mechanism          (PatternCard.density_scale_permille)
  sdd-c31-masking-codec-*              (the hat's upper corner and the duck)
  sdd-c30-timbral-grit-*               (the drive and the snap)
  sdd-c29-longform-memory-*            (the streamed render and master)
Handoff documents are in docs/handoff/, one per change.

What exists: five lanes (motorik, kosmische, ambient, dub-electronic,
indie-noise); the arranger (section graph, tension curve, motif and
transforms, the Director, the modal shifts, the Frippertronics, the dub
chain); the mix bus (trims, sends, one low pass, and since c31 a bass-keyed
200-500 Hz duck); the master chain (measured loudness onto -16 LUFS, a
true-peak limiter, LRA, seeded TPDF dither); every gate of BRIEF 11 in force;
the CLI (render, batch, catalog, validate, install, explain); the catalog and
the atomic writer. The render streams: the mix is a float64 memmap stem and
the master holds only the int16 output (c29).

Measured on this machine, eight-minute pieces, seed 1042, after c32:

| lane | wall | loudness | true peak | LRA | pcm_sha256 |
|---|---|---|---|---|---|
| motorik | 89.3 s | -16.083 LUFS | -4.298 dBTP | 10.37 LU | 3a902b7a... |
| kosmische | 121.1 s | -16.051 LUFS | -4.299 dBTP | 10.06 LU | 2423db5b... |
| dub-electronic | 119.4 s | -16.099 LUFS | -4.297 dBTP | 11.75 LU | b5b63e10... |
| indie-noise | 129.9 s | -16.106 LUFS | -4.293 dBTP | 10.16 LU | 00b1513b... |
| ambient | 127.3 s | -16.095 LUFS | -4.299 dBTP | 11.44 LU | 4a586f55... |

Every lane passes every gate at eight minutes; the 240 s seed sweep passes
gates 4/5/6/7/13 at five lanes x three seeds. Every LRA is inside BRIEF 6's
4-12.

NEW IN c32: THE WHOLE INTERLUDE BAND IS GREEN. Every lane passes every gate
at 45, 60, 90 AND 120 seconds, which was not true before. That band is the
station's interlude form (45-120 s, station.yaml:19) and it used to refuse
kosmische at 45 s and 60 s, motorik at 45 s, indie-noise at 45 s and
dub-electronic at 45 s and 90 s.

=====================================================================
THE RULES THAT ARE NOT NEGOTIABLE
=====================================================================

- The Plan is data: frozen, integer-only pydantic, canonical JSON, SHA-256
  of those bytes. No float leaf, no bool leaf, no clock field. Audio is a
  pure function of the Plan. Randomness ends when the Plan is frozen.
- The renderer never rolls dice and never imports compose/. The master is
  the one stage that looks at its own output; do not add a second.
- A field that is declared and never read is a bug. Presets are swept by
  tests/test_preset_consumption.py: every declared key must move the plan.
  One key is deliberately exempt and says so in the source
  (density_scale_permille - see below).
- A default of 0 must be a strict no-op: the frozen S0 render
  (tests/test_migration.py) must stay bit-identical.
- No new third-party dependency. Exact pins; the pin list is the lockfile.
- Conventional commits, one change at a time, no AI attribution, no
  "Co-Authored-By".
- One change is one SDD run: memory records sdd-<change_id>-{explore,
  proposal,spec,design,tasks,impl,verify,done} via the n3rv-memory MCP.
- The project board does not track this project. Skip board updates.
- Never write into ~/Work/radio except through install, and only when
  asked. Do not start or restart the radio. (Overridden once, at the
  operator's explicit request, when c31 shipped: see the radio note below.
  The defaults stand.)

Commands: .venv/bin/pytest, .venv/bin/ruff check ., .venv/bin/ruff format
--check ., .venv/bin/mypy src, and
.venv/bin/python -m indiegen.cli render --preset motorik --seed 1042 --out out/
The seed sweep is its own CI job and a local .venv/bin/pytest -q -m sweep.
Gate 12 (the codec) and gate 11 need ffmpeg and run only in `validate` and
`install`, never in the render path. Note: there is no pytest-timeout
plugin, so --timeout is rejected.

=====================================================================
DECISIONS ALREADY MADE - DO NOT RE-LITIGATE
=====================================================================

- The loudness is measured, not declared (it moves 1.3-5.1 dB seed to seed).
- The limiter is true-peak aware, 4x oversampled, channels linked, gain may
  only fall.
- Gates 5 and 6 judge the plan against itself, and a static plan must not be
  failed for being static (c27).
- Micro-timing: swing on odd beats and 1/f onset jitter on plucks, at
  compose time, from a dedicated sub-RNG (c26).
- Grit: a per-lane drive, tanh(x*gain)/gain, identity at 0, applied in
  synth/ks.py ONLY (the plucked/string voices). The additive pad, drone and
  poly-period are deliberately clean (c30).
- The render streams over a float64 memmap stem; the master computes the
  peak envelope per block.
- c31: a hat's cutoff_hz is its LOWER corner, and lowpass_hz the optional
  upper one. All three hat lanes declare 14000. This is BRIEF 6's codec rule.
- c31: the duck is keyed on bass HIT FRAMES, runs BEFORE the drum bus is
  summed in, and is declared on motorik and dub-electronic only.
- c31: a station-wide >12 kHz shelf was built and CUT, because across three
  seeds, the 45 s interlude and the 900 s longform it changed no verdict.
  Do not rebuild it without new evidence.
- c32: A PULSED SECTION IS NEVER SHORTER THAN FOUR BARS (MINIMUM_SECTION_BARS,
  planner.py). _section_lengths asked for four-bar multiples and used to give
  the snapping up when the drawn section count did not fit - and the count is
  drawn independently of the duration, so a 45 s track got the same six
  sections as a 480 s one at two bars each. The count gives way now, not the
  floor: compose() caps the draw at what four bars per section allows, and
  _section_lengths falls back to a floor-pinned proportional split
  (_floored_shares) when the snap does not fit. The cap is floored at the
  lane's own section_count_range[0] - a five-second test render must keep the
  count it declared, or _walk_graph has no arrangement to build.
- c32: A DRUM VOICE'S DENSITY GATE BELONGS TO THE HIT'S FRAME, NOT TO ITS BAR
  (t6_drums.py, _audible). It used to be tested once per bar against the
  section the bar started in, so a bar straddling a section boundary carried
  the dense section's material into the sparse one. That ONE bug was both of
  the "remaining defects": dub-electronic took nine and seven stray hits into
  its quietest section at 45 s and 90 s and its energy arc inverted (gate 5),
  and indie-noise took four into its outro (gate 7).
- c32: PatternCard.density_scale_permille lets a pattern's pulse count follow
  the section's density. 0 is a strict no-op. It exists because indie-noise's
  wall is euclid(16, 16) - already maximum - so build (density 55) and
  plateau (80) were identical and the lane's documented "it crests in the
  plateau" was never implemented. At 1000 the wall plays 9 of 16 pulses at
  density 55 and 13 at 80. Measured: 4.73 -> 5.81 hits/s.
- The millibel is the SI millibel: 1/1000 dB, so gain.py is
  `10 ** (millibels / 20000)` and `-6000` is -6 dB. The unit was 1/100 dB
  until 2026-10-25 and every stored level was re-expressed x10 when it
  changed; the audio is bit-identical (the frozen S0 hash and the ambient
  PCM hash both still match), only the numbers got a digit.
- Declared deviations, in the s4-mix-master-spec record: gate 10 is "the
  same seed must NOT give a different hash"; the limiter is not safety-only
  on indie-noise; the LRA range has the documented dub exception; the Python
  pin is 3.15 not 3.12; BRIEF 6's "mono below ~120 Hz" is not implemented.

=====================================================================
WHAT IS LEFT - IN THIS ORDER
=====================================================================

--- 1. THE RENDER_BLOCK DRUM-TAIL DEFECT (carried from c31) --------------

A drum voice longer than RENDER_BLOCK loses its tail past the second block:
render_drum_block carries an overrunning hit as one PendingHit and
_mix_pending mixes it into the next block, but the tails are never
RE-carried, because `carried` is rebuilt from the current block's own hits.
Only kick, snare and bass are affected (the kick's decay_frames is 13000);
hat, pad and pluck are fine. Reproduces at RENDER_BLOCK 4099 and 8191, clean
at 16384. Latent in production (RENDER_BLOCK is 131072) and the existing
test uses 65536, so the suite gives false confidence. It matters because
RENDER_BLOCK is the obvious next memory dial after c29. Full detail: memory
topic c31-preexisting-drum-tail-block.

--- 2. c27-C: THE SHORT AMBIENT'S ARC (deferred from c27) ----------------

The ambient can draw a two-section intro(-1200) -> outro(-1400) plan, a
sixteen-minute piece with 0.2 dB of shape; it passes gate 5 only because of
c27's static-plan tolerance. Give it a real arc, without leaning on the
exemption. Note that ambient's timbre table is 800 Hz for EVERY function, so
gate 6 takes its static-variance branch there and never correlates a curve -
anything that gives the ambient a shape has to decide what that means for
the declaration.

--- 3. VOICE-LEADING AND MODAL MIXTURE (the last audit pillar) ----------

No voice-leading engine exists; harmony is modal stasis. This is the biggest
identity change and the biggest blast radius. Spike it first (a /tmp harness
with a pre-declared falsifier and a measured A/B) before it touches the
planner.

=====================================================================
A KNOWN CAVEAT ABOUT GATE 7 IN ONE LANE
=====================================================================

indie-noise passes gate 7 at every duration now, but at 45 s it passes
because the sparser build SPLIT the intro/build flux cluster, not because
the plateau boundary produces a peak: the flux there is 72300 against a
threshold of 100353. At 90 s the peaks do track the section boundaries. So
a green gate 7 in this lane is still not proof that every section change is
audible. Do not read it as one, and do not tune this lane against gate 7
without measuring the flux at the boundaries first - the dense wall gives
the flux a permanently high baseline (median ~68000) and only a large
spectral change clears the threshold.

Five candidate fixes for this lane were built and measured before the
mechanism that worked was found (a second wall, a kick, a snare, a pad, a
poly-period); four of them turned no failing case into a passing one and
were cut, with their numbers recorded. The kick was also rejected because
tests/test_bus.py asserts that indie-noise has no kick. That assertion is a
contract: the lane is defined as a lane without one.

=====================================================================
THE RADIO (state as of c31, unchanged by c32)
=====================================================================

~/Work/radio/music holds 20 tracks, all generated by c31 (seeds 4000-4019,
installed 2026-10-24; `install` validates every file with the codec gate and
copies atomically). The nine pre-c30 tracks that used to be in rotation were
MOVED OUT, not deleted, to /tmp/opencode/radio-old/.

Adding files to music/ needs no restart (reload_mode = "watch"). REMOVING
them does: liquidsoap keeps deleted tracks in its in-memory playlist, so
`docker compose restart liquidsoap` in ~/Work/radio is required. That was
done once, at the operator's request.

NOTE: c32 changed indie-noise's audio, so the 20 tracks on the radio are
pre-c32. Re-installing is a decision for the operator, not a step of this
change.

scripts/smoke.sh reports 29/29. The one historical failure was a Caddy 302
assertion caused by the RADIO repo's webcam token-in-URL fallback (de02e9a),
fixed there at 40c7c31. That fix now ENFORCES the token-in-URL redirect, so
reverting it to Location: / will FAIL the smoke suite; the accepted exposure
is the browser URL only, not the stream.

=====================================================================
METHOD THAT HAS WORKED HERE - AND THE WAYS IT WENT WRONG IN c32
=====================================================================

c32 turned up three defects the suite did not see, and the method that found
them is the one to keep: measure before writing code, give every spike a
pre-declared falsifier, and when a claim breaks, root-cause it or record the
deviation out loud.

Four things went wrong in c32. They are worth more than the fixes:

1. FIFTEEN HARNESS RUNS MEASURED THE WRONG PLAN. The CLI builds its plan as
   director(compose(...)) (cli.py:116). The harnesses called compose() alone,
   so every plan they measured had no Director - no strategy-deck moves and
   no _reshape_motif. It surfaced only because a plan-level gate (13,
   "director fires") reported zero on a plan the CLI accepts, which is
   impossible. THE CHEAPEST CHECK IS THE HASH: compare the harness's
   plan_sha256 with the CLI's for the same preset/seed/seconds before
   trusting a sweep. That hash was in hand from the first run.

2. A CAP ON A DRAWN COUNT MUST BE FLOORED AT THE DECLARED MINIMUM. The first
   version of c32's section-count cap used max(1, ...); at a test's five
   seconds that is one section, _walk_graph has no arrangement of one, and
   35 tests died with PlanError. The draw's range is what the rest of the
   pipeline assumes.

3. TWO HYPOTHESES WERE MEASURED DEAD. The motif's count-based placement was
   c32's root cause for a while, and a change to it DID make the gate pass -
   by altering the bright-onset rate, which is exactly BRIEF 11's "do not add
   a filter sweep to satisfy this gate" failure mode. It was reverted. The
   dub chain's sidechain was the second suspect and was also innocent. The
   real cause was one line of bar-versus-frame gating in a different file.

4. c31's STANDARD, APPLIED TO ITS SUCCESSORS. Five crest candidates were
   built and measured for indie-noise; the four that turned no failing case
   into a passing one were CUT rather than shipped, with their numbers
   recorded. That is the shelf precedent doing its job.

Habits worth keeping, all learned the hard way:
- When you add a stage to the render, prove bit-identity against a pre-change
  `git worktree` (PYTHONPATH override the venv's editable install).
- Do not trust a measured number's label. c31 found a mislabelled unit, a
  stale figure and two README claims that contradicted the README's tables.
  c32 found that the measured table's indie-noise row was stale the moment
  the wall changed - re-derive a table row when the thing it measures moves,
  and remember the goldens do not cover every lane (they cover motorik's plan
  and ambient's PCM).
- Never loosen a gate to make a number pass. Four c32 candidates died on
  that rule and the fifth earned its place.
```

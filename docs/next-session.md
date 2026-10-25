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

master is at the c33 commit (fix(c33): freeze the drum's micro-timing in the
Plan). Clean tree. ruff check ., ruff format --check . and mypy src are
clean (60 files). pytest -q -m "not sweep and not slow": 650 passed, 20
deselected. pytest -q -m sweep: 15 passed. pytest -m slow: 5 passed.

Slices S0-S5 and changes c21-c33 are done. SDD records are in memory under
sdd-<change_id>-{context,explore,proposal,spec,design,tasks,impl,verify,done}.
The recent ones, most useful first:
  sdd-c33-{explore,proposal,spec,design,tasks,impl,verify}  the drum drift
  c27c-ambient-timbre-declaration     (the ambient's flat timbre)
  c27c-ambient-45s-regression         (the silent poly-period voice)
  sdd-c32-short-form-trajectory-done  (the interlude band)
  c32-density-scale-mechanism         (PatternCard.density_scale_permille)
  c31-masking-codec-*                 (the hat's upper corner and the duck)
Handoff documents are in docs/handoff/, one per change. c33's is
docs/handoff/c33-drum-drift-in-the-plan.md.

What exists: five lanes (motorik, kosmische, ambient, dub-electronic,
indie-noise); the arranger (section graph, tension curve, motif and
transforms, the Director, the modal shifts, the Frippertronics, the dub
chain, a conservative voice-leading pass); the mix bus (trims, sends, one low
pass, the bass-keyed 200-500 Hz duck); the master chain (measured loudness
onto -16 LUFS, a true-peak limiter, LRA, seeded TPDF dither); every gate of
BRIEF 11 in force; the CLI (render, batch, catalog, validate, install,
explain); the catalog and the atomic writer. The render streams: the mix is a
float64 memmap stem and the master holds only the int16 output (c29).

Measured on this machine, eight-minute pieces, seed 1042, after c33. The
previous table was stale (4ed10b5 moved the harmony; 3a902b7a was the old
motorik row):

| lane | wall | loudness | true peak | LRA | pcm_sha256 |
|---|---|---|---|---|---|
| motorik | 118.8 s | -16.071 LUFS | -4.299 dBTP | 9.221 LU | 7a5b7afb... |
| kosmische | 148.9 s | -16.058 LUFS | -4.298 dBTP | 10.553 LU | 499c6efb... |
| dub-electronic | 149.2 s | -16.059 LUFS | -4.298 dBTP | 12.297 LU | 445142e2... |
| indie-noise | 159.4 s | -16.092 LUFS | -4.279 dBTP | 9.436 LU | d7c75aa8... |
| ambient | 167.7 s | -16.008 LUFS | -4.300 dBTP | 11.282 LU | 1ca0885d... |

dub-electronic's 12.297 LU is above BRIEF 6's 12 and is the documented dub
exception in the S4 declaration. Every other lane is inside 4-12.

The interlude band (45-120 s) is green for all five lanes, and has been
since c32. That band is the station's interlude form (45-120 s,
station.yaml:19).

NEW IN c33: THE RENDER IS BLOCK-INVARIANT, FOR REAL. A drum hit's played
frame is data in the Plan (HitBase.frame), and HitBase.drift_frames recovers
the grid frame the arrangement wrote. The renderer no longer adds an offset
of its own. Measured: 0 of 200 consecutive RENDER_BLOCK sizes (4000..4199)
change a sample; before c33, 10 of them lost a whole drum hit.

=====================================================================
THE RULES THAT ARE NOT NEGOTIABLE
=====================================================================

- The Plan is data: frozen, integer-only pydantic, canonical JSON, SHA-256
  of those bytes. No float leaf, no bool leaf, no clock field. Audio is a
  pure function of the Plan. Randomness ends when the Plan is frozen.
- The renderer never rolls dice and never imports compose/. The master is
  the one stage that looks at its own output; do not add a second.
- compose/ may not import synth/, mix/, master/ or fx/ - tests/test_hygiene.py
  enforces it. That is why the 1/f control stream lives in indiegen/control.py
  and not under synth/.
- The drift is the performance; every decision asks the grid. A hit has two
  frames: frame (where it plays) and grid_frame() (where it was scheduled).
  The voice's noise, the bus keyframes (the duck, the kick sidechain), the
  Director's move windows, and the density gates all read grid_frame().
  Reading frame where grid_frame() is meant changes the arrangement, and it
  did: 759 kicks became 761 at 480 s.
- A field that is declared and never read is a bug. Presets are swept by
  tests/test_preset_consumption.py: every declared key must move the plan.
  One key is deliberately exempt and says so in the source
  (density_scale_permille).
- A default of 0 must be a strict no-op: the frozen S0 render
  (tests/test_migration.py) must stay bit-identical.
- No new third-party dependency. Exact pins; the pin list is the lockfile.
- Conventional commits, one change at a time, no AI attribution, no
  "Co-Authored-By".
- One change is one SDD run: memory records sdd-<change_id>-{explore,
  proposal,spec,design,tasks,impl,verify,done} via the n3rv-memory MCP.
- The project board does not track this project. Skip board updates.
- Never write into ~/Work/radio except through install, and only when
  asked. Do not start or restart the radio.

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
- c27-C: the ambient declares a FLAT timbre - one centroid for every
  function - so gate 6 measures its variance, not a curve. Its delivered
  centroid moves with the track's DURATION, not with the section's function:
  a table fitted at 90 s correlates -0.37 / -0.28 / +0.35 at 45 s. Do not
  "fix" the table without a mechanism that makes the centroid
  duration-aware. Declared value 560 Hz (measured median, range 412-861).
- c27-C fallout, fixed: a poly-period phase is drawn INSIDE THE TRACK
  (t1_polyperiod.py). Renders at or above the card's longest period (90 s)
  are bit-identical; only shorter tracks moved.
- Micro-timing: swing on odd beats and 1/f onset jitter on plucks, at
  compose time (c26). The drum's micro-timing is compose-time too, since
  c33 - see above.
- Grit: a per-lane drive, tanh(x*gain)/gain, identity at 0, applied in
  synth/ks.py ONLY (the plucked/string voices). The additive pad, drone and
  poly-period are deliberately clean (c30).
- The render streams over a float64 memmap stem; the master computes the
  peak envelope per block.
- c31: a hat's cutoff_hz is its LOWER corner, and lowpass_hz the optional
  upper one. All three hat lanes declare 14000. This is BRIEF 6's codec rule.
- c31: the duck is keyed on bass HIT FRAMES, runs BEFORE the drum bus is
  summed in, and is declared on motorik and dub-electronic only. Its key is
  the GRID frame, deliberately: re-keying it on the played frame is audible
  (9.4e-2 in the 200-500 Hz band on motorik) and needs its own change.
- c31: a station-wide >12 kHz shelf was built and CUT, because across three
  seeds, the 45 s interlude and the 900 s longform it changed no verdict.
- c32: A PULSED SECTION IS NEVER SHORTER THAN FOUR BARS
  (MINIMUM_SECTION_BARS, planner.py). The count gives way, not the floor.
- c32: A DRUM VOICE'S DENSITY GATE BELONGS TO THE HIT'S FRAME, NOT TO ITS
  BAR (t6_drums.py, _audible).
- c32: PatternCard.density_scale_permille lets a pattern's pulse count follow
  the section's density. 0 is a strict no-op.
- c33: A DRUM HIT'S PLAYED FRAME IS IN THE PLAN. The drift is read at compose
  time from the same 1/f timing stream the renderer used to read, so the
  change moved no audio at any duration: the pre-master mix at 131072 is
  bit-identical to 5af67f3 at 20, 90 and 480 s on motorik, dub-electronic and
  indie-noise (motorik 7001c989, dub b7a520f3, indie-noise c3ad866d at 480 s).
  The plan golden moved (afab3b54) because hit frames and drift_frames are
  plan bytes.
- The millibel is the SI millibel: 1/1000 dB, so gain.py is
  `10 ** (millibels / 20000)` and `-6000` is -6 dB. Every stored level was
  re-expressed x10 when it changed; the audio is bit-identical.
- Declared deviations, in the s4-mix-master-spec record: gate 10 is "the
  same seed must NOT give a different hash"; the limiter is not safety-only
  on indie-noise; the LRA range has the documented dub exception; the Python
  pin is 3.15 not 3.12; BRIEF 6's "mono below ~120 Hz" is not implemented.

=====================================================================
WHAT IS LEFT - IN THIS ORDER
=====================================================================

--- 1. VOICE-LEADING AND MODAL MIXTURE (the last audit pillar) ----------

Harmony is modal stasis. There IS a conservative voice-leading pass
(planner._apply_voice_leading: it smooths large leaps while staying in
scale, for plucks and bass, and moves the recorded motif appearances with
them) - an earlier handover claimed no engine existed, which was wrong. What
does not exist is harmonic PROGRESSION: the mode changes between sections and
the melody is transposed to follow, but there is no voice leading across a
chord change, and no modal mixture.

This is the biggest identity change and the biggest blast radius. Spike it
first: a /tmp harness with a pre-declared falsifier and a measured A/B, and
check plan_sha256 against the CLI for the same preset/seed/seconds before
trusting any sweep (c32's fifteen harness runs all measured a plan with no
Director in it).

--- 2. RENDER_BLOCK, NOW THAT IT IS SAFE TO LOWER -----------------------

The drum-tail defect c31 recorded is fixed (4ed10b5) and the drift defect
c33 found is fixed, so the block size no longer changes the audio. 0 of 200
consecutive sizes is bit-identical on motorik, and the two regression tests
pin 4060. c29's workstream was memory; this is the next dial. Measure the
memory ceiling and the wall time at 32k and 16k on the 900 s longform before
choosing, and keep an eye on the per-block cost the master pays.

--- 3. AN ELEVEN-SECOND GAP IN THE HANDOVER THAT IS NOW CLOSED ----------

Nothing. This slot used to hold the "c27-C: the ambient's timbre" item, which
shipped in df005d2.

=====================================================================
A KNOWN CAVEAT ABOUT GATE 7 IN ONE LANE
=====================================================================

indie-noise passes gate 7 at every duration, but at 45 s it passes because
the sparser build SPLIT the intro/build flux cluster, not because the plateau
boundary produces a peak: the flux there is 72300 against a threshold of
100353. At 90 s the peaks do track the section boundaries. A green gate 7 in
this lane is not proof that every section change is audible. Do not tune this
lane against gate 7 without measuring the flux at the boundaries first.

Five candidate fixes were built and measured for this lane; four turned no
failing case into a passing one and were cut, with their numbers recorded. A
kick was rejected because tests/test_bus.py asserts that indie-noise has no
kick - that assertion is a contract.

=====================================================================
THE RADIO (state as of c31, unchanged since)
=====================================================================

~/Work/radio/music holds 20 tracks, all generated by c31 (seeds 4000-4019,
installed 2026-10-24; `install` validates every file with the codec gate and
copies atomically). The nine pre-c30 tracks that used to be in rotation were
MOVED OUT, not deleted, to /tmp/opencode/radio-old/.

Adding files to music/ needs no restart (reload_mode = "watch"). REMOVING
them does: liquidsoap keeps deleted tracks in its in-memory playlist, so
`docker compose restart liquidsoap` in ~/Work/radio is required.

NOTE: c32 changed indie-noise's audio, so the 20 tracks on the radio are
pre-c32. c33 changed no audio. Re-installing is a decision for the operator.

scripts/smoke.sh reports 29/29. The one historical failure was a Caddy 302
assertion caused by the RADIO repo's webcam token-in-URL fallback (de02e9a),
fixed there at 40c7c31. That fix now ENFORCES the token-in-URL redirect, so
reverting it to Location: / will FAIL the smoke suite; the accepted exposure
is the browser URL only, not the stream.

=====================================================================
METHOD THAT HAS WORKED HERE
=====================================================================

Measure before writing code, give every spike a pre-declared falsifier, and
when a claim breaks, root-cause it or record the deviation out loud.

The c33 session is the best recent example of that last rule: four claims
failed measurement in one session. The handover said the drum-tail defect was
open (it had been fixed by 4ed10b5), said the ambient timbre was open (it had
shipped), said no voice-leading engine existed (one does), and the change's
own AC3 - "bit-identical at production block size" - was false twice, once
because the voices key their noise on the hit's frame and once because the
Director windows hits by frame. The cheapest instrument every time was a git
worktree at the previous commit plus a hash comparison, and the 480 s
duration caught the Director one, which 20 s and 90 s could not.

Habits worth keeping, all learned the hard way:
- When you add a stage to the render, prove bit-identity against a pre-change
  `git worktree` (PYTHONPATH override the venv's editable install). Compare
  hashes, not impressions.
- Compare at a LONG duration as well as a short one. Arrangement-level
  effects appear only where the arrangement has room to differ.
- Do not trust a measured number's label. c31 found a mislabelled unit, a
  stale figure and two README claims that contradicted the README's tables.
  c32 found a stale table row; c33 found that the whole table had gone stale
  when 4ed10b5 moved the harmony. Re-derive a row when the thing it measures
  moves, and remember the goldens do not cover every lane (they cover
  motorik's plan and ambient's PCM).
- Never loosen a gate to make a number pass. When c33's drift pushed a hit
  one frame across a section line, the fix was to ask grid_frame(), not to
  widen the assertion into a tolerance.
- A change that moves no audio is worth paying some structural cost for. c33
  moved the control stream out of synth/ and taught four readers to ask the
  grid frame, and in exchange no gate verdict could move.
```

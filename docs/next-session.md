# The next session's prompt

Copy the whole block below into a fresh session. It is self-contained: it
carries the state of the project, the decisions already made, the
deviations already declared, and the three things that are left. Nothing in
it needs the conversation that produced it.

If you want to hand over your listening notes with it, paste them in the
marked slot: the session then starts by turning the notes into changes.

---

```text
You are taking over indiegenerator: a deterministic, offline, batch music
generator that makes tagged tracks for a private internet radio. The
repository is /home/estrocondoso/Repositories/indiegenerator. The
authoritative brief is BRIEF.md in the repository root - read it, it is the
contract (especially sections 6, 8, 11, 15 and 18). Do not modify it.

=====================================================================
THE STATE
=====================================================================

master, clean tree, 393 tests green, ruff check and ruff format --check
clean, mypy --strict clean over src/. The last commit is always
"chore: refresh the n3rv project metadata" (a test enforces it).

Slices S0 to S4 are done and archived in memory under the topic keys
sdd-s0-skeleton, sdd-s1-ambient-lane, sdd-s2-motorik-lane,
sdd-s3-arranger and sdd-s4-mix-master (each has explore, proposal, spec,
design, tasks, impl, verify and done records). The handoff documents are in
docs/handoff/. Read docs/handoff/s4-mix-master.md first: it carries the
measured numbers, the decisions, the defects and the open items.

What exists: five lanes (motorik, kosmische, ambient, dub-electronic,
indie-noise) that each render a 6-8 minute track; the arranger (the section
graph, the tension curve, the motif and its transforms, the Director, the
modal shifts, the Frippertronics, the dub chain); the mix bus (the
per-instrument trims, the send levels, the kick on every bus); the master
chain (the measured loudness onto -16 LUFS, the true-peak limiter at
-1.5 dBTP, the loudness range, the seeded TPDF dither); and every gate of
BRIEF section 11 in force.

Measured on this machine, eight-minute pieces, seed 1042:

| lane | wall | peak RSS | loudness | true peak | LRA |
|---|---|---|---|---|---|
| motorik | 75.0 s | 1182 MB | -16.000 LUFS | -1.891 dBTP | 9.68 LU |
| kosmische | 97.6 s | 1180 MB | -16.002 LUFS | -1.800 dBTP | 9.37 LU |
| ambient | 116.1 s | 1252 MB | -16.007 LUFS | -1.800 dBTP | 11.39 LU |
| dub-electronic | 81.2 s | 1182 MB | -16.001 LUFS | -1.800 dBTP | 12.50 LU |
| indie-noise | 76.4 s | 1289 MB | -16.120 LUFS | -1.778 dBTP | 9.10 LU |

The budget is three minutes and 1.5 GB. Every lane passes every gate, and
a twenty-render seed sweep (four seeds per lane, 420 s pieces) passes
every gate at every lane and every seed.

=====================================================================
THE RULES THAT ARE NOT NEGOTIABLE
=====================================================================

- The Plan is data: a frozen, integer-only pydantic model, canonical JSON,
  SHA-256 of those bytes. No float leaf, no bool leaf, no clock field.
  Audio is a pure function of the Plan. Randomness ends when the Plan is
  frozen. The renderer never rolls dice and never imports compose/.
- The master chain is the one place that looks at its own output: it
  measures the loudness of the finished mix and gains it onto the target.
  That is allowed because it is a named second pass over a finished stem.
  Do not add a second one.
- A send level is read. A field that is declared and never read is a bug,
  not a knob: the reverb's and the delay's send levels were dead until S4
  and cost a lane its stereo image.
- No new third-party dependency. numpy, scipy, soundfile, pydantic, typer,
  PyYAML, mutagen, pytest, ruff, mypy. Exact pins; the pin list is the
  lockfile.
- Conventional commits, one slice at a time, no AI attribution, no
  "Co-Authored-By". Run /review before any commit that touches src/.
- One slice is one change_id from BRIEF section 15, and it is one SDD
  change: the memory records sdd-<change_id>-{explore,proposal,spec,
  design,tasks,impl,verify,done}, written with the n3rv-memory MCP.
- Run /judgment-day after apply for S3 and S6.
- Never write into ~/Work/radio except through install, and only when
  asked. Do not start or restart the radio.
- The project board does not track this project (it belongs to another
  org). Skip the board updates; do not pass --issue.

Commands: .venv/bin/pytest, .venv/bin/ruff check ., .venv/bin/ruff format
--check ., .venv/bin/mypy src/, and
.venv/bin/python -m indiegen.cli render --preset motorik --seed 1042 --out out/

=====================================================================
THE DECISIONS ALREADY MADE - DO NOT RE-LITIGATE THEM
=====================================================================

- The loudness is measured, not declared: the loudness of a lane moves
  1.3 to 5.1 dB from seed to seed and gate 1 allows one LU.
- The limiter is true-peak aware: a 4x oversampled peak per base sample,
  the two channels linked, the gain the minimum of the next 5.8 ms, the
  deficit released exponentially over 40 ms. The gain may only fall.
- The gates that need ffmpeg (11 and 12) are dev gates. ffmpeg is a tool
  on this machine and not a runtime dependency.
- Gate 9's band is measured in the frequency domain, and its second clause
  (the full-band L/R correlation) is measured and reported, not a
  threshold: BRIEF's own caveat says a decorrelated delay must not fail
  that gate.
- Every arrangement reaches a dense section (density 70 or more), and a
  Director's drop that would silence the layer it drops is not drawn.
- No bus compressor. The brief's delivers line does not ask for one and a
  fast bus compressor would flatten the tension curve gate 5 measures.

Declared deviations, all in the s4-mix-master-spec record: D-1 gate 10
is implemented as "the same seed must NOT give a different hash" (BRIEF
11 writes it backwards and BRIEF 2 promises the opposite); D-2 the limiter
is not "safety only" on the indie-noise lane, whose crest is 27 dB; D-3
the loudness range is a range with a documented exception (the dub lane
measures 12.5 LU against the brief's 4-12); D-4 the Python pin (3.12 in
the brief, 3.15 in the project) is inherited from S0; D-5 BRIEF 6's "mono
below ~120 Hz" is not implemented (the mix is already mono in the low band,
and a causal crossover made the ambient's balance worse); D-6 as above.

=====================================================================
WHAT IS LEFT - THREE THINGS, IN THIS ORDER
=====================================================================

--- 1. THE LISTENING NOTES -> THE CHANGES THEY ASK FOR -----------

Three tracks are rendered and ready, with the current code, in
out/listening/ :

  motorik_glass_slow_s1042.flac      6:05   -16.0 LUFS
  kosmische_lantern_paper_s1042.flac  7:36   -16.0 LUFS
  ambient_drift_signal_s1042.flac    6:47   -16.0 LUFS

FLAC, 44.1 kHz, 16-bit, stereo, tagged. Play them with mpv, ffplay or vlc
(cd out/listening && mpv motorik_glass_slow_s1042.flac). Re-render them
after any change: .venv/bin/python -m indiegen.cli render --preset
<lane> --seed 1042 --out out/listening/

The protocol, per track: a timestamp and what happened ("at 2:14 the bass
disappears and nothing replaces it"), groove / timbre / structure / space /
fatigue scored 1-5 each, one thing to keep and one thing to cut, and
"would you leave it on as background radio? yes or no".

Three questions the meters cannot answer, and what each of them costs:

  (a) THE BALANCE. Which voice is too loud and which is too quiet? The mix
      bus carries a per-instrument trim, in integer millibels, in the lane
      presets under "bus_gains" (the key is the event kind: pad,
      poly_period, drone, pluck, kick, snare, hat, bass). Adding
        bus_gains:
          - {kind: pluck, gain_millibels: -600}
      to a lane's preset trims that voice for that lane. The measured
      balance is in the handoff, section 6.

  (b) THE INDIE-NOISE LIMITER. That lane's crest factor is 27 dB: the
      wall alone measures a 13.7 dB crest and the plucks alone 27.4 dB, so
      reaching -16 LUFS under a -1.5 dBTP ceiling needs about 12.8 dB of
      gain reduction, and the limiter squashes the guitar's transients. If
      that sounds wrong, the fix is NOT a quieter limiter: it is a louder
      noise wall or a softer guitar, which is an arrangement change (the
      wall's card, min_density, or the guitar's velocity in the lane
      preset), and it needs the ear to choose. Measure the result: the
      lane's crest and the limiter's gain reduction, and the gates.

  (c) THE ENDING AND THE GAPS. Every track ends composed, with no fade-out.
      Does the ending feel like an ending or like a stop? Does a section
      ever feel empty? The ending is the plan's fade_out and the outro
      section; the gaps are the Director's drops.

Rule: fix the earliest STRUCTURAL cause, not the loudest complaint, and
re-render and ask again. Do not silently re-tune three times. Every change
to a preset moves the arrangement, so re-measure the gates for the lane
you touched and regenerate the goldens (tests/golden/) if the plan or the
audio moved.

--- 2. S5, THE SLICE s5-batch-station --------------------------------

The brief's CLI is half missing. S5 adds, in this order:

  - `indiegen batch --preset station --count 20 --seed-base 1000 --out out/`
    the station blend, the seed base, the count, and the three track forms
    of BRIEF section 15: about 60 percent full tracks (4-10 min), 25
    percent longform (10-15 min), 15 percent interludes (45-120 s). The
    lane presets already declare duration_range_seconds [45, 900] for the
    forms and full_track_range_seconds [360, 480] for the default; the
    batch has to draw the form and the duration, and the plan has to
    declare which form it is.
  - `indiegen catalog --dir out/` a JSON catalog keyed by the decoded PCM
    SHA-256: seed, preset, duration, LUFS, TP, the section plan, the
    director log, the techniques, the path. The library size, and the
    refusal of a duplicate seed and of a duplicate hash.
  - `indiegen validate out/track.flac` every gate of section 11 on a file
    that is already on disk, including the codec round trip.
  - `indiegen install --dir out/ --to ~/Work/radio/music` validate first,
    then the same atomic rename the writer uses, into a watched directory.
    It never starts or restarts the radio, and it only ever runs when it
    is asked to.
  - The definition-of-done item: `indiegen batch --preset station --count
    10 --seed-base 2000` gives ten distinct tagged FLACs in under thirty
    minutes, every one of them passing validate including the codec gate.

The acceptance criteria are exactly BRIEF section 15's S5 line plus the
applicable parts of section 16, and they are binary. Measure the batch:
the wall time, the memory, and the per-track gates. S5 has no
composition changes: it is the batch, the catalog and the install.

--- 3. S6, THE SLICE s6-taste-pass ---------------------------------

The taste pass, and it needs human ears:

  - Start from the three tracks and the notes from step 1. Fix the
    earliest structural cause of each note.
  - Then the ten-track EP: 6 full, 2 longform, 2 interludes.
  - The last gate of BRIEF section 16 is a human gate and not a metric:
    "The 10 tracks on shuffle for an hour: no repeated section, no urge to
    skip." Ask for that explicitly, with the tracks and the timestamps.
  - Run /judgment-day after apply, and write the handoff.

=====================================================================
THE NOTES GO HERE
=====================================================================

Paste the listening notes in this slot if you have them. The session
starts by turning them into the changes in step 1, and it asks for what is
missing.

<notes>

=====================================================================
DONE MEANS
=====================================================================

- Every acceptance criterion of the slice measured on the running program,
  not on the test suite alone.
- The whole suite green, ruff and mypy clean, the tree clean, the last
  commit a chore: the n3rv refresh.
- The README's numbers are the measured ones, the handoff document is
  written, and the memory records exist: sdd-<change_id>-{impl,verify,done}.
- A report that says what was measured, what was decided, what was left
  open, and what the next session has to do.
```

---

## Why this is a prompt and not a summary

It is the *handover* the brief asks for at every checkpoint (BRIEF §18:
"the handoff document is how the next session starts from facts instead of
from a half-remembered chat"), written so that a session with no memory of
this conversation can execute it. Three sections do the work the context
would otherwise have done:

- **The state** — the commits, the tests, the gates, the measured numbers,
  so the fresh session does not re-derive them.
- **The decisions and the deviations** — so the fresh session does not
  re-litigate the measured loudness, the true-peak limiter, the dev gates,
  the dense-section rule or the six declared deviations (D-1…D-6).
- **The rules** — the integer-only Plan, the one sanctioned second pass, the
  read-your-send-levels rule, the no-new-dependency rule, the commit and
  memory conventions, and the two things the project must not touch
  (`~/Work/radio` and the board).

The notes slot is the hinge: paste your three answers there and the fresh
session starts by turning them into trims, an arrangement change or a
different ending — instead of re-rendering the same three tracks.

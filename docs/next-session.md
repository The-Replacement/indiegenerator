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

master is at fe97aa2 (feat(c31): an upper corner on the hat and a bass-keyed
masking duck). Clean tree. ruff check, ruff format --check and mypy src are
clean. pytest -q -m "not sweep": 543 passed, 15 deselected. pytest -q -m
sweep: 15 passed. pytest -m slow: 4 passed.

Slices S0-S5 and changes c21-c31 are done and archived in memory under the
topic keys sdd-<change_id>-{context,proposal,spec,design,tasks,impl,verify,
done}. The recent ones, most useful first:
  sdd-c31-masking-codec-*      (the hat's upper corner and the masking duck)
  sdd-c30-timbral-grit-*       (the drive and the snap)
  sdd-c29-longform-memory-*    (the streamed render and master)
  sdd-c28-seed-sweep-gate-coverage-*  (the sweep and its CI job)
  sdd-c27-ambient-energy-trajectory-* (gate 5 and the static plan)
Handoff documents are in docs/handoff/, one per change. Read
docs/handoff/c31-masking-codec.md first: it carries the measured numbers, the
shelf that was built and cut, and the two pre-existing defects.

Read the memory topic c31-preexisting-drum-tail-block and
c31-measurements-and-gate7-regression before touching the render block or a
gate: they are the latent defects found while landing c31 and the method that
found them.

What exists: five lanes (motorik, kosmische, ambient, dub-electronic,
indie-noise); the arranger (section graph, tension curve, motif and
transforms, the Director, the modal shifts, the Frippertronics, the dub
chain); the mix bus (trims, sends, one low pass, and since c31 a bass-keyed
200-500 Hz duck); the master chain (measured loudness onto -16 LUFS, a
true-peak limiter, LRA, seeded TPDF dither); every gate of BRIEF 11 in force;
the CLI (render, batch, catalog, validate, install, explain); the catalog and
the atomic writer. The render streams: the mix is a float64 memmap stem and
the master holds only the int16 output (c29).

Measured on this machine, eight-minute pieces, seed 1042, after c31:

| lane | wall | loudness | true peak | LRA | pcm_sha256 |
|---|---|---|---|---|---|
| motorik | 89.3 s | -16.083 LUFS | -4.298 dBTP | 10.37 LU | 3a902b7a... |
| kosmische | 121.1 s | -16.051 LUFS | -4.299 dBTP | 10.06 LU | 2423db5b... |
| dub-electronic | 119.4 s | -16.099 LUFS | -4.297 dBTP | 11.75 LU | b5b63e10... |
| indie-noise | 109.4 s | -16.116 LUFS | -4.292 dBTP | 10.11 LU | e1f6b6b0... |
| ambient | 127.3 s | -16.095 LUFS | -4.299 dBTP | 11.44 LU | 4a586f55... |

Every lane passes every gate at eight minutes; the 240 s seed sweep passes
gates 4/5/6/7/13 at five lanes x three seeds. Every LRA is inside BRIEF 6's
4-12.

=====================================================================
THE RULES THAT ARE NOT NEGOTIABLE
=====================================================================

- The Plan is data: frozen, integer-only pydantic, canonical JSON, SHA-256
  of those bytes. No float leaf, no bool leaf, no clock field. Audio is a
  pure function of the Plan. Randomness ends when the Plan is frozen.
- The renderer never rolls dice and never imports compose/. The master is
  the one stage that looks at its own output; do not add a second.
- A field that is declared and never read is a bug. Presets are swept by
  tests/test_preset_consumption.py: every declared key must move the plan,
  so a knob only a lane with the matching event can consume is declared
  only on that lane (see c30: snap on lanes with drums; c31: the duck on the
  two lanes with a bass).
- A default of 0 must be a strict no-op: the frozen S0 render
  (tests/test_migration.py) must stay bit-identical.
- No new third-party dependency. Exact pins; the pin list is the lockfile.
- Conventional commits, one change at a time, no AI attribution, no
  "Co-Authored-By".
- One change is one SDD run: memory records sdd-<change_id>-{explore,
  proposal,spec,design,tasks,impl,verify,done} via the n3rv-memory MCP.
- The project board does not track this project. Skip board updates.
- Never write into ~/Work/radio except through install, and only when
  asked. Do not start or restart the radio. (Both were overridden once, at
  the operator's explicit request, when c31 shipped: see the radio note
  below. The defaults stand.)

Commands: .venv/bin/pytest, .venv/bin/ruff check ., .venv/bin/ruff format
--check ., .venv/bin/mypy src, and
.venv/bin/python -m indiegen.cli render --preset motorik --seed 1042 --out out/
The seed sweep is its own CI job and a local .venv/bin/pytest -q -m sweep.
Gate 12 (the codec) and gate 11 need ffmpeg and run only in `validate` and
`install`, never in the render path.

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
  poly-period are deliberately clean: drive on the sustained bed lifted
  motorik's LRA to 16.49 LU (c30). A level-neutral shaper for the sustained
  bed is still deferred.
- The render streams over a float64 memmap stem; the master computes the
  peak envelope per block.
- c31: a hat's cutoff_hz is its LOWER corner (a closed hat is noise ABOVE
  it), and lowpass_hz is the optional upper one. All three hat lanes declare
  14000. This is BRIEF 6's codec rule, applied at the source.
- c31: the duck is keyed on bass HIT FRAMES (the sidechain rule), runs
  BEFORE the drum bus is summed in, and is declared on motorik and
  dub-electronic only.
- c31: a station-wide >12 kHz shelf was built and CUT, because across three
  seeds, the 45 s interlude and the 900 s longform it changed no verdict. Do
  not rebuild it without new evidence.
- A unit trap worth remembering: a millibel in this project is 1/100 dB
  (gain.py: 10 ** (millibels / 2000)). -6000 is -60 dB, not -6 dB.
- Declared deviations, in the s4-mix-master-spec record: gate 10 is "the
  same seed must NOT give a different hash"; the limiter is not safety-only
  on indie-noise; the LRA range has the documented dub exception; the Python
  pin is 3.15 not 3.12; BRIEF 6's "mono below ~120 Hz" is not implemented.

=====================================================================
WHAT IS LEFT - IN THIS ORDER
=====================================================================

--- 1. c32: THE SHORT-FORM TRAJECTORY ---------------------------------

kosmische fails gate 6 at 60 s: the pre-c31 code at the c30 commit measures
-0.214971 against the 0.4 limit for the shipped preset. The c30 handoff
recorded -0.10 cold / -0.013 warm and those figures DO NOT REPRODUCE - work
from -0.214971. It passes at 240 s. The station's interlude form is
45-120 s, so a legal short kosmische track is refused. Find the structural
cause (the timbre curve at short durations) and fix it, not the gate.
Reproduce: render --preset kosmische --seed 1042 --seconds 60.

--- 2. THE RENDER_BLOCK DRUM-TAIL DEFECT ------------------------------

A drum voice longer than RENDER_BLOCK loses its tail past the second block:
render_drum_block carries an overrunning hit as one PendingHit and
_mix_pending mixes it into the next block, but the tails are never
RE-carried, because `carried` is rebuilt from the current block's own hits.
Only kick, snare and bass are affected (the kick's decay_frames is 13000);
hat, pad and pluck are fine. Reproduces at RENDER_BLOCK 4099 and 8191, clean
at 16384. Latent in production (RENDER_BLOCK is 131072) and the existing
test uses 65536, so the suite gives false confidence. It matters because
RENDER_BLOCK is the obvious next memory dial after c29. Full detail:
memory topic c31-preexisting-drum-tail-block.

--- 3. c27-C: THE SHORT AMBIENT'S ARC (deferred from c27) --------------

The ambient can draw a two-section intro(-1200) -> outro(-1400) plan, a
sixteen-minute piece with 0.2 dB of shape; it passes gate 5 only because of
c27's static-plan tolerance. Give it a real arc, without leaning on the
exemption.

--- 4. VOICE-LEADING AND MODAL MIXTURE (the last audit pillar) --------

No voice-leading engine exists; harmony is modal stasis. This is the biggest
identity change and the biggest blast radius. Spike it first (a /tmp harness
with a pre-declared falsifier and a measured A/B) before it touches the
planner.

=====================================================================
THE RADIO (state as of c31)
=====================================================================

~/Work/radio/music holds 20 tracks, all generated by c31 (seeds 4000-4019,
installed 2026-10-24; `install` validates every file with the codec gate and
copies atomically). The nine pre-c30 tracks that used to be in rotation were
MOVED OUT, not deleted, to /tmp/opencode/radio-old/ - they are also
byte-identical to the copies in out_batch/, so they are recoverable two
ways. `rm` is blocked by the sandbox's permission policy; `mv` is not.

Adding files to music/ needs no restart (reload_mode = "watch"). REMOVING
them does: liquidsoap keeps deleted tracks in its in-memory playlist, so
`docker compose restart liquidsoap` in ~/Work/radio is required. That was
done once, at the operator's request.

scripts/smoke.sh reports 29/29. It reported 28/29 while c31 was landing, and
the one failure was "la redirección arrastra el token", a Caddy 302
assertion. It was not c31's and not this repo's: the cause was the webcam
token-in-URL fallback in the RADIO repo (de02e9a), which made the canje
redirect keep ?t= in the URL, so `grep -iE '^location: /$'` could never
match. It was fixed there at 40c7c31, by asserting the frontend URL instead.

Two things that fix changed, both worth knowing:
- The assertion now ENFORCES the token-in-URL redirect, so reverting it to
  Location: / will FAIL the smoke suite. The trade is encoded as a test.
- The boundary that still holds is the one that matters: "el token NO llega a
  Icecast" passes and the no-credential paths 404, so the token never reaches
  the stream. The accepted exposure is the browser URL only (history,
  Referer, CDN logs).

Method note, because it is the kind of reasoning that survives into other
diagnoses: while this was open, "Caddy has restarts=0 and was up throughout"
was offered as evidence that the failure predated the session. It is not. It
proves the PROCESS was not restarted, not that its BEHAVIOUR did not change -
a config edit or a deploy changes behaviour without touching the process. The
causal evidence was pinning the change to a specific commit.

=====================================================================
METHOD THAT HAS WORKED HERE
=====================================================================

Three of the last six changes (c27, c30, c31) each turned up a defect the
suite did not see, and c28 was the change that made that class visible. c31
found its cause by measuring BEFORE writing code: two /tmp spikes attributed
the gate-12 failure to the hat (90% of the >14 kHz energy) rather than to a
missing shelf, and a third spike retired the duck's LRA risk. Every spike
had a pre-declared falsifier.

Keep the discipline: run the sweep, measure before and after, and when a
claim breaks, root-cause it and fix the cause, or record the deviation out
loud. Several decisions in c31 were made by measurement refusing them (the
shelf, the timbre re-declaration) and those refusals are recorded with
numbers. Never loosen a gate to make a number pass.

Two habits worth keeping, both learned the hard way in c31:
- When you add a stage to the render, prove bit-identity against a pre-change
  `git worktree` (PYTHONPATH override the venv's editable install). That is
  how c31 showed kosmische and ambient were untouched.
- Do not trust a measured number's label. The c31 work found a mislabelled
  unit (-6000 millibels described as -6 dB), a stale c30 figure, and two
  README claims that contradicted the README's own tables.
```

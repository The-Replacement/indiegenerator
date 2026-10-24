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

master is at 666aaa3 (feat(c30): a per-voice drive on the string and a
snapped kit). Clean tree. ruff check, ruff format --check and mypy src are
clean. pytest -q -m "not sweep": 526 passed, 15 deselected. pytest -q -m
sweep: 15 passed. pytest -m slow: 4 passed.

Slices S0-S5 and changes c21-c30 are done and archived in memory under the
topic keys sdd-<change_id>-{context,proposal,spec,design,tasks,impl,verify,
done}. The recent ones, most useful first:
  sdd-c30-timbral-grit-* (the drive and the snap)
  sdd-c29-longform-memory-* (the streamed render and master)
  sdd-c28-seed-sweep-gate-coverage-* (the sweep and its CI job)
  sdd-c27-ambient-energy-trajectory-* (gate 5 and the static plan)
  sdd-c26-microtiming-groove-* (swing and 1/f onset jitter)
Handoff documents are in docs/handoff/, one per change. Read
docs/handoff/c30-timbral-grit.md first: it carries the measured numbers, the
LRA decision, and the two pre-existing defects.

Read memory topic c30-preexisting-gate-findings and c26-gate-sweep before
touching gates: they are the latent defects that were found and the method
that found them.

What exists: five lanes (motorik, kosmische, ambient, dub-electronic,
indie-noise); the arranger (section graph, tension curve, motif and
transforms, the Director, the modal shifts, the Frippertronics, the dub
chain); the mix bus; the master chain (measured loudness onto -16 LUFS, a
true-peak limiter, LRA, seeded TPDF dither); every gate of BRIEF 11 in
force; the CLI (render, batch, catalog, validate, install, explain); the
catalog and the atomic writer. The render now streams: the mix is a float64
memmap stem and the master holds only the int16 output (c29).

Measured on this machine, eight-minute pieces, seed 1042, after c30:

| lane | wall | loudness | true peak | LRA | pcm_sha256 |
|---|---|---|---|---|---|
| motorik | 88.7 s | -16.084 LUFS | -4.299 dBTP | 10.78 LU | f1c8de79... |
| kosmische | 112.6 s | -16.051 LUFS | -4.299 dBTP | 10.06 LU | 2423db5b... |
| dub-electronic | 119.5 s | -16.104 LUFS | -4.297 dBTP | 11.71 LU | 63016d07... |
| indie-noise | 94.2 s | -16.095 LUFS | -4.293 dBTP | 10.79 LU | aecfa8e9... |
| ambient | 134.9 s | -16.095 LUFS | -4.299 dBTP | 11.44 LU | 4a586f55... |

The budget is three minutes of wall and 1.5 GB of RSS for eight minutes; a
fifteen-minute ambient is 268.9 s and 1263 MB (c29). Every lane passes every
gate at eight minutes; the 240 s seed sweep passes gates 4/5/6/7/13 at five
lanes x three seeds.

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
  only on that lane (see c30: snap is only on lanes with drums).
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

=====================================================================
DECISIONS ALREADY MADE - DO NOT RE-LITIGATE
=====================================================================

- The loudness is measured, not declared (it moves 1.3-5.1 dB seed to seed).
- The limiter is true-peak aware, 4x oversampled, channels linked, gain may
  only fall.
- Gates 5 and 6 judge the plan against itself. Gate 5 treats a planned level
  spread of <= 0.3 dB as a static plan and passes it (c27); gate 6 already
  had the equivalent static-timbre tolerance. A static plan must not be
  failed for being static (BRIEF 11).
- Micro-timing: swing on odd beats (frames_per_beat * permille // 6000) and
  1/f onset jitter on plucks, at compose time, from a dedicated sub-RNG so
  the main draw order is untouched (c26). The KS detuned chorus pair drifts
  together; the motif's appearances move with their plucks.
- Grit: a per-lane drive, tanh(x * (1 + 6*d))/ (1 + 6*d), identity at 0,
  applied in synth/ks.py ONLY (the plucked/string voices). The additive pad,
  drone and poly-period are deliberately clean: drive on the sustained bed
  lifted motorik's LRA to 16.49 LU, outside BRIEF 6's 4-12. A level-neutral
  shaper for the sustained bed is deferred.
- The render streams over a float64 memmap stem; the master computes the
  peak envelope per block. peak_envelope_block and limit_block are the
  per-block bodies of peak_envelope and limit and are bit-identical to them.
- Declared deviations, in the s4-mix-master-spec record: gate 10 is "the
  same seed must NOT give a different hash"; the limiter is not safety-only
  on indie-noise (crest 27 dB); the LRA range has the documented dub
  exception; the Python pin is 3.15 not 3.12; BRIEF 6's "mono below ~120 Hz"
  is not implemented.

=====================================================================
WHAT IS LEFT - IN THIS ORDER
=====================================================================

--- 1. c31: MASKING AND THE CODEC (the next change) -------------------

Two things, and they share a stage:

(a) The indie-noise lane fails gate 12 (the codec) on `validate`: the
    FLAC -> MP3 128 -> decode loudness delta measures 0.905 LU cold (drive
    0) and 0.978 warm, against the 0.5 limit. It fails without c30's grit.
    motorik, dub and ambient validate ok. The render path does not run gate
    12 (it needs ffmpeg); only `indiegen validate <file>` does.
    Reproduce: .venv/bin/python -m indiegen.cli render --preset indie-noise
    --seed 1042 --seconds 60 --out /tmp/x && .venv/bin/python -m
    indiegen.cli validate /tmp/x/*.flac
(b) A masking stage: duck 200-500 Hz under the bass envelope, and a
    >12 kHz shelf for the codec rule (BRIEF 6: keep essential content below
    14 kHz). Precedents: mix/sidechain.py (the kick-keyed envelope) and
    synth/filter.py (the one-pole/biquad helpers).
(c) The level-neutral shaper for the sustained bed (pad/drone/poly): per-
    block RMS-matched or a parallel dry/wet blend, so the pad earns
    harmonics without moving the LRA. This is what c30 deferred.

Do the explore and proposal first and stop for the approach decision, the
way c27 and c29 were done. Any audio change moves every PCM golden and the
README table; say so in the commit.

--- 2. c32: THE SHORT-FORM TRAJECTORY ---------------------------------

kosmische fails gate 6 at 60 s: measured -0.10 cold, -0.013 warm, limit
0.4 (it passes at 240 s). The station's interlude form is 45-120 s, so a
legal short kosmische track is refused. Find the structural cause (the
timbre curve at short durations) and fix it, not the gate. Reproduce:
render --preset kosmische --seed 1042 --seconds 60.

--- 3. c27-C: THE SHORT AMBIENT'S ARC (deferred from c27) --------------

The ambient can draw a two-section intro(-1200) -> outro(-1400) plan, a
sixteen-minute piece with 0.2 dB of shape; it passes gate 5 only because of
c27's static-plan tolerance. Give it a real arc: either a stronger outro
contrast in the shared station graph or a floor of three sections for the
ambient, without leaning on the exemption.

--- 4. VOICE-LEADING AND MODAL MIXTURE (the last audit pillar) --------

No voice-leading engine exists; harmony is modal stasis. This is the
biggest identity change and the biggest blast radius. Spike it first (the
L-series pattern: a /tmp harness with a pre-declared falsifier and a
measured A/B) before it touches the planner. Counterpoint constraints can
sterilise a system as easily as enliven it.

--- 5. OPTIONAL: the drum-bus compressor's per-sample Python loop ------

synth/drumcomp.py loops per sample in Python. It is opt-in (plan.drum_bus_comp
default None), so it is a CPU cost only when on. Vectorise it if the CPU
matters; it is not on the default path.

=====================================================================
METHOD THAT HAS WORKED HERE
=====================================================================

Two of the last five changes (c27, c30) each turned up a defect the suite
did not see, and c28 was the change that made that class visible. Keep the
discipline: run the sweep, measure before and after, and when a claim breaks
root-cause it and fix the cause, or record the deviation out loud. Never
loosen a gate to make a number pass.
```

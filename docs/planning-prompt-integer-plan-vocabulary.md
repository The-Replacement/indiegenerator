# Planning Prompt — Integer Plan Vocabulary Implementation (c21 → c22 → c23)

You are planning the implementation of the adopted mechanisms from `docs/research-two-dimensions-report.md` (the "report"). Your job is NOT to write code. Your job is to run the full SDD pipeline — explore → propose → spec → design → tasks — three times, once per change_id, in sequence, so that each cycle's tasks are reviewable, falsifiable, and bit-identity-testable before the next cycle starts.

Read the report first. It is the single source of truth for scope, verdicts, ranges, and acceptance criteria. This prompt adds the execution discipline the report does not carry.

---

## Part 0 — Frozen Constraints (verified, with file:line)

These are non-negotiable. If anything in the report contradicts what you find in the tree, STOP at that point, cite both, and resolve before writing artifacts. The report's citations were verified in the research session; re-verify anything you rely on.

1. **Plan is integers and rationals only** — `plan.py:35,45,48-66,479-482,485-501`. No floats, no string enums carrying behavior. New fields obey this or they don't exist.
2. **RNG dies at compose** — `planner.py:1-4,611-612`; `render.py:3`. Nothing in c21–c23 may introduce runtime randomness. Probabilities (`ornament_permille` etc.) are plan-time gate tests, resolved before render.
3. **No new dependencies.** Compressor, saturation, send logic: numpy-only, repo-native.
4. **Never modify `BRIEF.md`.** It is the contract. The missing `passes` field (BRIEF:322) is therefore an implementation obligation or a formally documented rejection with a linked issue — never an edit to BRIEF.
5. **Bit-identity is the corner stone.** Every cycle must prove: legacy presets render **bit-identical** audio before/after, when new fields sit at their legacy defaults. First failing acceptance is usually the hash collateral, caught in review.
6. **Hash collateral travels with the change.** Any Plan schema change moves `plan_sha256` → README hash columns, goldens, plan-hash tests re-derive in the SAME change. A change that updates `src/` without collateral does not pass review. This is stated in report §4; treat it as a gate, not a suggestion.
7. **The 1500 MB RSS budget** (15-min ambient already measured 2177 MB — `README.md:111-115`). c21–c23 must not grow RSS: mutes reduce events; pad partials N ≤ 9; no layer multiplication beyond L16 doubling if it ever comes back.
8. **CPU numbers are this machine's measurements** — pad +8.26 ms/partial/block, drone +59.5 ms/partial/block (`/tmp/opencode/spike_dimensions.py`; memory topic `research-spike-2d`). Tests must MEASURE their own machine and compare against the budget table, not copy session numbers as assertions. Report numbers are reference annotations, not thresholds to assert.
9. **Master chain stays single-pass** — 4-iteration bounded pre-limit loop (`master/chain.py:42-43,62-77`), ceiling −4.0 dBFS (`presets/station.yaml` `ceiling_millibels: -400`). Saturation sits pre-limiter; nothing adds a second measuring pass.
10. **One voice per event.** No counterpoint allocator, no event-model rewrite. L05's rejection holds.
11. **Shader discipline for review**: conventional commits, never "Co-Authored-By". Own the per-cycle diffs; each PR maps to exactly one cycle.

---

## Part 1 — Inputs

Read, in this order:

1. `docs/research-two-dimensions-report.md` — scope, ledger, ranges, conflict resolutions, acceptance criteria (§9 is the contract for pass/fail).
2. Memory topic keys: `research-a-wagner`, `research-a-vivaldi`, `research-a-satie`, `research-a-stockhausen`, `research-b-vig`, `research-b-eno`, `research-b-rubin-kanye`, `research-spike-2d` (n3rv-memory, type discovery).
3. `/tmp/opencode/spike_dimensions.py` — the measurement harness. Reuse it for new spikes; extend, don't rewrite.
4. The tree: `plan.py`, `compose/planner.py`, `synth/pad.py`, `synth/drone.py`, `synth/env.py`, `render.py`, `master/chain.py`, `validate.py`, `presets/*.yaml`, `station.yaml`, `tests/`.

---

## Part 2 — Cycle Sequence and Gates

Three SDD cycles, strictly sequenced. No cycle starts until the previous one is merged with tests green and its verify verdict recorded.

```
c21-pad-partials-intonation → c22-per-bus-sends-drum-comp → c23-chord-segments-mutes
        (schema + DSP core)         (bus graph + compressor)      (harmony + arrangement)
```

Why this order: c21 replaces `PadEvent.partials` (the one structural schema change) + declares tuning + envelope family — every downstream change wants this schema settled first. c22's send/compressor work is orthogonal DSP but reads the EventBase `envelope_curve` from c21. c23 adds harmony/arrangement fields that are plan-level and cheap, and it inherits the fixed send list reading.

**Per cycle, mandatory:**
- Run `/sdd-new <change_id> <description>` (full 8 phases) with a GitHub issue; board tracking per repo convention.
- Spec restates the report's acceptance criteria for that cycle VERBATIM as testable bullets, plus the falsifiers of the included ledger rows as unit-test names.
- Design must show the DSP data flow and name the carry-state pattern (phase carries, `pad.py:54` style) wherever a new stage keeps state.
- Tasks are atomic: each task = one reviewable diff, with its test named in the task (test-first ordering).
- Verify (`sdd-verifier`) checks: bit-identity legacy, gate suite green, budget numbers measured and recorded, hash collateral complete, no dead-field regressions introduced.

---

## Part 3 — Cycle Content

### Cycle 1 — `c21-pad-partials-intonation` (ledger L06 + L09 + L10 + bugfix bundle)

Mechanisms: `PadEvent.partials: list[Partial]` replacing `partials:int` + `partial_detune_cents`; `tuning_system: 0|1` + mode-conditioned drone ratio pool (dorian pool drops 5/4); `envelope_curve: 0|1` on `EventBase`.

**Bugfix bundle folded here deliberately (tradeoff: one hash re-derivation instead of many):**
- `fifth_permille` (`config.py:176`, set `motorik.yaml:95`, read nowhere) — DECIDE: implement (BRIEF 5's phrase-end behavior) or delete. Choose with a written tradeoff; either way the field stops being dead. Beware: implementing means BRIEF promises must now be honored — re-read BRIEF 5 first.
- `palette` (`plan.py:436`, `planner.py:763`, read nowhere; advertises nonexistent `formant`/`noise` instruments) — delete or make real; write the decision.
- `SectionPlan.transform` (`plan.py:344`, copied `planner.py:940`, read by nothing) — delete or wire; write the decision.
- `passes` field (BRIEF:322 specifies; no infrastructure) — implement minimal, or formally reject with issue. Documented either way; BRIEF stays untouched.

Acceptance criteria (from report §9, binding):
1. ruff / mypy / pytest green.
2. Legacy renders bit-identical (legacy default partials = {1,2,3} @ 0 dB, curve=0, tuning=0).
3. Ambient dorian ratio pool: measured partial-vs-scale beat rate ≤ 6 Hz at f0=220 — test computes the frequency math itself; the 13.37 Hz baseline is recorded in the test as the before-number reference.
4. `envelope_curve=1`: measured 90% rise ≈ 0.575·A and bit-distinct from curve=0.
5. Pad N=9 within measured budget: ≤ ~96 ms per 131072-frame block per voice on the test machine (measure, don't assert session numbers).
6. All hash collateral re-derived in the same change.

Explicitly OUT of c21: L07 segment permutations, L03/L08/L16/L21/L24 (spikes). They return only in c23's optional spike block, behind their own falsifiers, never bundled into adopted work.

### Cycle 2 — `c22-per-bus-sends-drum-comp` (L14 + L15)

Mechanisms: per-bus `reverb_send_permille: 0..800` and `delay_send_permille: 0..600` (the `[0]`-only send defect dies here — this IS the bugfix for `render.py:155-160,266-285`; do not file a separate one); new `DrumBusComp` stage (`threshold_millibels -6000..0`, `ratio_permille 2000..10000`, `attack_frames 10..500`, `release_frames 1000..100000`, `makeup_millibels 0..6000`, `mix_permille 0..1000`), envelope-follower with carry state, between drum sum and bus mix; master chain untouched.

Acceptance criteria (report §9, binding):
1. Second wet source audible when its send > 0; dry buses bit-identical when their send = 0 (summation-bug falsifier).
2. Crest factor drop ≥ 1.5 dB at default compact settings, measured before/after on the test machine; codec gate green at the −4.0 dBFS ceiling.
3. Compressor restart-from-stated-block renders bit-identical audio (carry-state determinism test is mandatory, not optional).
4. Motorik render CPU ≤ +10% vs before on the test machine.
5. Full gate suite green; hash collateral re-derived.

### Cycle 3 — `c23-chord-segments-mutes` (L02 + L01 + L20 + L04, plus optional spike block)

Mechanisms: `chord_segments_per_section: 1..8`; `chord_tone_intervals` (len 3–5) + `chromatic_budget_permille: 0..1000`; `arrangement_mutes` binary {0,1000} per kind per section; bass `midi_offset_semitones: -12..12` replacing the hard-coded `root-12` (`t6_drums.py:222`); optional per-instrument `register_ceiling_offset: 0..24`.

Acceptance criteria (report §9, binding):
1. `chord_segments_per_section = 2` on motorik passes all 13 gates on regenerated goldens; declared chord changes match plan-log exactly.
2. Chromatic events ≤ `chromatic_budget_permille` (unit test on plan-log count).
3. `arrangement_mutes` validator rejects anything not in {0,1000}; reprise of a muted section is byte-identical.
4. Bass register offset default renders bit-identically to today.
5. Gate suite + hash collateral re-derived.

**Optional spike block (only if c1–c2 tasks of the cycle are green; each spike behind its falsifier, timeboxed, in `/tmp/opencode` first)**: L03 planar offset, L07 pad envelope segments, L08 ornaments, L16 micro-offset doubling, L21 pre-limiter saturation, L24 T16-in-the-bed third partial. A spike that fails its falsifier is deleted, not merged.

**Muted-piece Director interaction (L20's falsifier)**: design must state Director-awareness of mutes explicitly — a Director move must never target a section whose kind is muted, or the mismatch must be a validation error, never a silent crossfade into undeclared silence.

---

## Part 4 — Borrowed Hierarchy of Proof (from the research method)

- Every acceptance number in a test must be MEASURED on the machine running the test (or computed exactly), with the report number present as a reference comment.
- No test may assert a number the repo hasn't measured unless the computation is exact arithmetic (cent math, beat-rate math, crest-factor formulas).
- Gate runs are the arbiter of "green"; a change that passes tests but reds any of the 13 gates is a NO-GO, and the falsifier fires.
- Two independent sources per acted aesthetic claim is now moot (research done); the analogous rule here is TWO tests per behavior: the bit-identity test and the behavioral test must both exist for every new field.

---

## Part 5 — Open Questions the Planner MUST Answer Before Spec (put them in the Part-6 first reply)

1. `fifth_permille`: implement or delete? (Implementing = honoring BRIEF 5 at phrase ends; deleting = removing a preset key `motorik.yaml:95`. What does the phraseend actually require in execution terms?)
2. `palette`: pure delete, or wire to instruments the renderer actually has?
3. `SectionPlan.transform`: delete or wire; if wire, is `reprise_of` + Director enough cover?
4. `passes`: implement minimal (what does "passes" even mean in this event model — a duration subdivision?) or formally reject?
5. Does `PadEvent.partials` keep `pad_envelope_segments` OUT (report says c21 excludes L07)? Confirm the schema leaves a clean slot, not a half-hook.
6. Confirm the c2 ordering claim: does c21's `envelope_curve` actually reach every event kind's envelope path, or is the pluck excitation a special case (`synth/env.py:50-80` covers which kinds)?
7. Sequencing sanity: does anything in c22 depend on c23 changes (e.g., compressor on the drum bus vs mutes reducing drum events)? If mutes land after comp, comp sees fewer events — is crest-factor acceptance re-measured after c23?

---

## Part 6 — Execution Protocol (your FIRST reply, then STOP)

Your first reply must contain ONLY:

1. Verified-constraints confirmation: the Part 0 items you re-verified in the tree this session, with file:line for each, and any corrections found (report vs tree).
2. The cycle order you will run and any sequencing change you want to propose (with evidence).
3. Your answers-or-worked-tradeoffs for each Part 5 open question, marking any that need the user's decision.
4. Source/verification plan for the SDD cycles: which spike scripts you'll extend, which tests you expect to write per cycle (test names, not code), and the expected hash-collateral surface per cycle.
5. Expectation setting: what you predict each cycle's hardest falsifier will be (e.g., for c21 the bit-identity test on partial migration; for c22 the carry-state determinism test; for c23 gate-suite interplay with chord segments).

Then STOP and wait for go-ahead. Do not fetch, spike, write artifacts, or touch `src/` before the user answers.

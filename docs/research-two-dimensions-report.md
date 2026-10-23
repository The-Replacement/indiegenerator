# Research Report — Two New Dimensions (Harmony/Spectrum + Sound Treatment)

Research execution of `docs/research-prompt-two-dimensions.md`, full run (seed + sound treatment clusters).
**Scope discipline**: research only — no `src/` or `presets/` files written, no new dependencies, spikes only in `/tmp/opencode/spike_dimensions.py`. Repo facts below are `path:line` citations verified against the working tree this session; external claims carry a URL and an evidence grade.

Evidence grades used throughout:
- **A** — named engineer/composer's own published words, or arithmetic/DSP measured on this machine (spike scripts cited).
- **B** — authoritative secondary source with references at hand.
- **C** — weak secondary, uncorroborated (never acted on alone).
- **D** — would be dropped outright; none survived into a voiced mechanism.

---

## 1. Verdict

Both dimensions produce executable Plan vocabulary within the frozen-integer Plan; nothing required breaking Part 0.

- **Cluster A** converts into four ADOPT-NOW moves: per-partial amplitude for the pad (`list[Partial]` already exists at `plan.py:135-141`, only the drone uses it), a declared intonation system (the ambient lane's 5/4 drone partial beats against its own dorian scale at a measured **13.37 Hz** — a live, quantified contradiction), sub-section chord segments, and an integer envelope family. The pad is the leverage point: it renders partials 1..N at **unity amplitude** (`pad.py:51-55`), so every Stockhausen/Satie spectrum move is currently inaudible in the pad bed.
- **Cluster B** converts into three ADOPT-NOW moves: per-bus sends (`render.py:155-160` reads send `[0]` only — half-dead field, same class of bug as `fifth_permille`), one drum-bus compressor (none exists, `README.md:382`), and binary arrangement mutes (Rubin's subtraction, corroborated independently by Vig).
- **7 mechanisms are rejected with teeth** (measure-perfect mastering, global moment form, convolution spaces, instrumental vibrato, layering, counterpoint, dead-axis leitmotif) — each with the measured or architectural reason.
- Every schema touch invalidates `plan_sha256`; README hash columns, goldens, and plan-hash tests re-derive in the same change or the change does not ship.

---

## 2. Axis Model

Post-correction axis state (corrections established at Part 6, all `path:line` verified):

| Axis | Claim | Status after verification |
|------|-------|--------------------------|
| A1 chromatic sonority | Wagner's non-scale verticals within a tonal region | **ADOPT** — Tristan chord resolves to integer set {0,3,6,9} from the bass; needs a chromatic budget so the classical gate doesn't collapse |
| A2 harmonic rhythm / chord succession | Sub-section chord change | **ADOPT (reframed)** — section-level rhythm exists (`planner.py:77-80`, Director at `director.py:186-226`); the gap is sub-section |
| A2b static/planar harmony | Satie parallel chords | **SPIKE** — cheap, but today's default already IS static (`chord_segments=1`); the Gymnopédie delta is planar, not functional |
| A3a register discipline | Vivaldi solo/tutti registers | **ADOPT** — bass is hard-coded `root-12` (`t6_drums.py:222`) |
| A4 counterpoint | Independent voices | **REJECT** — one voice per event is an architecture constant |
| A5 spectral composition | Per-partial amplitude / permutation | **ADOPT + SPIKE** — pad has NO per-partial amplitude field today |
| A6 phrasing ornaments | Grace/anticipation; vibrato | **SPIKE (grace) / REJECT (vibrato)** |
| A7 leitmotif/drone identity | Motif as identity | **REJECT** — déjà-vu/replay/reprise already implement it |
| A8 intonation system | JI vs 12-TET declaration | **ADOPT** — live measured contradiction (13.37 Hz beat) |
| A9 envelope family | Linear vs exp attack | **ADOPT** — one linear ramp for every instrument (`env.py:50-80`) |
| B1 space arrangement | Dry capture vs wet sculpture | **ADOPT (per-bus sends) / REJECT (IR rooms)** |
| B2 bus compression | Drum-bus compressor | **ADOPT** — none exists |
| B3 layering/double-tracking | Multi-take thickness | **SPIKE (micro-offset doubling) / REJECT (track-stacking)** |
| B4 grit/saturation | Pre-limiter distortion identity | **SPIKE** |
| B5 subtraction/timing | Arrangement silence + budget | **ADOPT (mutes) / DEFER (voice budget) — REJECT (RSS-bound layering)** |
| B6 measuring-perfect mastering | Second measuring pass | **REJECT** — rule 0; the one legal pass exists (`master/chain.py:42-77`) |

---

## 3. Technique Ledger (24 rows)

Compact sources referenced in-table:
- **[S1]** https://en.wikipedia.org/wiki/Tristan_chord (B)
- **[S2]** https://en.wikipedia.org/wiki/Harmonic_rhythm (B)
- **[S3]** https://en.wikipedia.org/wiki/L%27estro_armonico (B)
- **[S4]** https://en.wikipedia.org/wiki/Sequence_(music) (B)
- **[S5]** https://en.wikipedia.org/wiki/Gymnop%C3%A9dies (B)
- **[S6]** https://en.wikipedia.org/wiki/Vexations (B)
- **[S7]** https://en.wikipedia.org/wiki/Stimmung (B)
- **[S8]** https://en.wikipedia.org/wiki/Klangfarbenmelodie (B)
- **[S9]** https://en.wikipedia.org/wiki/Moment_form (B)
- **[S10]** https://www.soundonsound.com/people/butcvig-nevermind-garbage (A — Vig's own words, interviewed by R. Buskin)
- **[S11]** https://www.inmotionmagazine.com/eno1.html (A — Eno's own words, 1996 talk)
- **[S12]** https://pitchfork.com/features/article/9157-the-yeezus-sessions/ (B — named producer/engineer quotes)
- **[M1]** `/tmp/opencode/spike_dimensions.py` (A — measured this machine; numbers in §5 and memory `research-spike-2d`)
- **[R]** repo code citation (A — the repo is ground truth for executability)

| id | axis | artist | mechanism | placement | integer plan fields (range) | DSP location | proxy metric | budget cost | determinism risk | IP class | evidence / URL | verdict | falsifier |
|----|------|--------|-----------|-----------|------------------------------|--------------|--------------|-------------|------------------|----------|------------------|---------|-----------|
| L01 | A1 | Wagner | Non-scale chord-tone sets inside a tonal region: Tristan sonority = {0,3,6,9} above the bass, allowed only within a budget | plan | `chord_tone_intervals: list[int 0..11]` (len 3–5); `chromatic_budget_permille: 0..1000` (default 0) | `theory/scales.py` chord pool + `compose/planner.py` selection | off-scale event fraction ≤ `chromatic_budget_permille` (unit test on plan) | ~0 (plan-time) | none — no RNG, no runtime state | method idea (public domain idiom; attribution only) | B [S1] + R (`plan.py:485-501`) | **ADOPT NOW** | If scale-membership filtering (`t1_polyperiod.py` today) is load-bearing for gate 4/6 stability, chromatic events shift section centroid beyond the one-value-per-section resolution (`validate.py:465-540`) — then budget must drop to 0 and the row dies |
| L02 | A2 | Wagner | Harmonic rhythm as an integer: chord changes at sub-section stride | plan | `chord_segments_per_section: 1..8` (1 = today) | `compose/planner.py` `_chord_roots` (286) — derivative roots per segment | declared changes/bar vs plan-log count (exact) | ~0; pad/drone event count ×N₀ (≤8×) — see RSS note §7 | none | method idea | B [S2] + R | **ADOPT NOW** | If segments < 2 bars make Director moves (`crossfade_frames`) misalign with root changes, Director crossfades no longer land on *any* root — gate 2/5 metrics degrades: measured in verify gate run |
| L03 | A2b | Satie | Planar (parallel) chord motion: every chord tone + k semitones, scale membership waived for the offset only | plan | `planar_offset_semitones: -12..12` (default 0) | `compose/planner.py` voicing post-pass offline | plan-log: all chord tones offset by exactly k (exact) | ~0 | none | method idea | B [S5] + R (`plan.py:436`) | **SPIKE** | Gymnopédie's static-parallel feel on a scales-filtered chord set ≡ T1's static interval list; if k≠0 yields a chord that then gets re-filtered to today's pool (event-identical, centroid shift < 20 Hz), the field is a no-op — cut |
| L04 | A3a | Vivaldi | Register discipline: instrument octave/bass offsets as plan values instead of hard-coded constants | plan | for bass: `midi_offset_semitones: -12..12` (default -12 preserves today); per instrument `register_ceiling_offset: 0..24` | `compose/techniques/t6_drums.py:222` (read plan field instead of constant) | plan-log mean register per instrument | ~0 | none | method idea | B [S3] + R | **ADOPT NOW** | None beyond existing gate-1 range checks: any regression is caught by red gates |
| L05 | A4 | Wagner/Nina Simone | Independent contrapuntal voices under one motif | plan+render | n/a | n/a | n/a | n/a | n/a | method idea | R (BRIEF §8: one voice per event) | **REJECT** | Not rejected by evidence — rejected by architecture: one voice per event is a load-bearing constant; a voice allocator is a new synthesis scheduling model, not a Plan field. Re-open only with a change that rewrites the event model (out of scope) |
| L06 | A5 | Stockhausen (Stimmung) | Per-partial amplitude on the pad: a held fundamental whose overtones can be individually weighted/permutated | plan+render | `PadEvent.partials: list[Partial(ratio_num 1..16, ratio_den 1..16, amplitude_millibels -3000..0, detune_cents -50..50)]`, len 1..9; legacy default `[(1,1,0 dB),(2,1,0),(3,1,0)]` preserves today exactly | `synth/pad.py:51-55` — weight each partial term; `Partial` model already at `plan.py:135-141` | gate-6 centroid per section (already measured); spike: centroid 442.1 Hz (N=3 flat) → 689–770 Hz (N=9 formant peak choices) [M1] | **+8.26 ms/partial/block measured**; N=3→9 = +8 s CPU per pad voice per 8-min track [M1] | none — pure additive, phase carries already blockwise-replayable | method idea | B [S7] ("first major Western composition based entirely on the production of vocal harmonics"; sung harmonics 2,3,4,5,7,9 with rotating emphasis) + A [M1] + R | **ADOPT NOW** | Acceptance: on legacy presets (0 dB per partial) rendered audio must be **bit-identical** to today; if not, the migration is wrong, not the axis |
| L07 | A5 | Stockhausen (Farben / Klangfarbenmelodie) | Amplitude-permutation segments: a held chord cycles its overtone weighting (orchestration changes while pitch is static) | plan+render | `pad_envelope_segments: list[(delta_frames 1.., permutation list[int])]` ≤ 4 segments/event | `synth/pad.py` control-rate amplitude switch per segment (same pattern as `render_drone_block`'s control layer, `synth/drone.py:56-69`) | centroid trajectory variance over the event, vs static-timbre gate-6 threshold | control-rate switch: O(partial count), negligible; growth bounded by ≤4 segments | LOW: amplitude switch is a pure function of local frame index (blockwise-determinable); no partial phase carries involved | method idea | B [S8] ("sound-color melody": Op.16/3 *Farben* = standing chord with rotating orchestration) + R | **SPIKE** | If permutation count pushes pad voices past the mix-loop event budget or gate 6 reads the variation as texture drift > declared, the segments get clamped to 1 — no-op, row dies |
| L08 | A6 | Satie (Vexations) | Grace/anticipation ornament events at phrase boundaries (theme-and-shadow repetition feel) | plan | `ornament_permille: 0..200`; `grace_offset_frames: 10..500` (lands before the host bar → clipped to bar start, never crosses) | `compose/planner.py` post-pass — plan-time event emission | extra event count ≤ clamp; all 13 gates on regenerated goldens | ≤ +20% events on ornamented lanes | none (composed at plan time; no runtime randomness) | method idea | B [S6] + R (repetition infra: déjà-vu + `reprise_of` + `replay_permille` already exist) | **SPIKE** | If grace events break déjà-vu determinism hashes (identical sections must remain byte-identical across reprises, which they do by construction) — the falsifier is a gate-run failure, cheap to detect |
| L09 | A8 | Satie / Stockhausen | Declared intonation system + mode-conditioned drone ratio pool: kill the measured 5/4-vs-dorian contradiction | plan+preset | `tuning_system: 0 (12-TET) \| 1 (JI-pure)`; presets carry `drone_ratio_pool` per mode (dorian/aeolian pool drops 5/4, keeps {1, 9/8, 4/3, 3/2}) | `synth/drone.py` ratio lists (today: `presets/ambient.yaml` ratios incl. 5/4, audited against `mode_pool` in the plan) | **beat rate between drone partials and scale tones**: today 13.37 Hz (5/4 @ 275.00 Hz vs dorian third @ 261.63 Hz at f0=220) [M1]; target ≤ 6 Hz | 0 — replaces ratio entries in presets | none — ratio lists are static | method idea | A [M1] (measured deltas: 9/8 +3.91¢, 5/4 −13.69¢, 4/3 −1.96¢, 3/2 +1.96¢ vs nearest dorian degree) + B [S7] | **ADOPT NOW** | If the pool that keeps ambient's character (must retain ≥1 non-trivial non-octave member) still beats > 6 Hz against its mode, the "declared JI coloration" stays undocumented-by-sound and the row degrades to documentation-only — honest death |
| L10 | A9 | (envelope family — no artist needed; Vig's "control his dynamics" is the production anchor) | Integer envelope family: linear vs exponential attack/release | plan | `envelope_curve: 0 (linear) \| 1 (exp, tau=A/4)` on every `EventBase` (`plan.py:164-174`) | `synth/env.py:50-80` — replace the single linear ramp branch | **measured rise-time ratio**: 90% point at 0.90·A (linear) vs 0.575·A (exp) [M1]; spectral centroid proxy is INSENSITIVE (both 220 Hz first-100ms) so the metric is the rise time, not spectrum | 0 | none | method idea | A [M1] + A [S10] ("compression... control his dynamics") | **ADOPT NOW** | If curve=1 renders bit-identical to curve=0 in the unit test, the implementation is broken (that outcome kills the PR, not the axis) |
| L11 | A6 | Chet Baker / Nina Simone | Instrumental vibrato (pitch wobble of a solo line, musician's expressive device) | render | n/a | n/a | n/a | n/a | n/a | **recording-specific** — would require measurement of copyrighted recordings (transcription) to parameterize | A/B (their recordings) — **not fetched, not allowed** | **REJECT** | Rejected on rules: no transcription/analysis of copyrighted recordings; synth voices have no per-sample pitch path (only slow `DetuneLfo`, `plan.py:143-147`, which is drone/pad drift, not a solo line). The measurable residue (detune LFO depth/rate) already exists — nothing new is actionable |
| L12 | A7 | Wagner | Leitmotif as new identity mechanism (recurring motif binding sections) | plan | n/a | n/a | n/a | n/a | n/a | method idea | B [S1] + R | **REJECT** | Already covered: déjà-vu events, `reprise_of` sections, replay mechanism (`planner.py` motif system) implement motif-identity recurrence; a second mechanism would duplicate a live one — dead axis by redundancy, not by infeasibility |
| L13 | A2/A9 | Stockhausen | Global moment form ("a mosaic of moments", no global narrative curve — his own definition, *Kontakte* programme) | plan | n/a | n/a | n/a | n/a | n/a | method idea | B [S9] (Stockhausen's own definitions) + R (gate 5: planned arc vs loudness) | **REJECT** | A globally planned moment form is a flat planned curve — it degenerates gate 5's correlation by construction. The legal residue is section-internal static (already exists). Re-open only if the gate contract changes, which is out of scope |
| L14 | B1a | Butch Vig | Dry capture + wet added later per surface: per-bus reverb/delay sends (his own method: capture dry, decide space in the mix) | plan+render | per bus: `reverb_send_permille: 0..800`, `delay_send_permille: 0..600` (default 0 = today's dry 2-bus) | `render.py:155-160,266-285` — the send lists are read, not just `[0]`; `render.py:293-298` reverb host input | when send>0: wet-bus input RMS rises; per-bus send changes dry/wet ratio exactly as declared (measured in test) | reverb host runs per active wet source; CPU scales with bus count — bounded ≤ 4 buses (measure in spike before apply) | none — sends are plan-static scalars | method idea | A [S10] ("recording everything very dry... if you wanted to add reverb or echo later you could") + R (`fx_sends`/`delay_sends` half-dead field verified) | **ADOPT NOW** | Falsifier: if enabling a second wet source changes the reverb input for sends that should be 0 (summation bug), the bit-diff test on dry buses fails |
| L15 | B2 | Butch Vig | One compressor stage on the drum bus ("a fair amount of compression... to control dynamics") | plan+render | new `DrumBusComp`: `threshold_millibels: -6000..0`, `ratio_permille: 2000..10000`, `attack_frames: 10..500`, `release_frames: 1000..100000`, `makeup_millibels: 0..6000`, `mix_permille: 0..1000` (0 = disabled/bypass, poles kept separate for parallel comp) | new `synth/drumcomp.py` envelope-follower stage applied to the drum bus between `render.py` drum sum and bus mix; master chain untouched (`master/chain.py` still the only measuring pass) | drum-bus crest factor drop ≥ 1.5 dB at default compact settings (measured); codec gate unchanged | envelope follower: O(frames) one pass — cheap; bounded memory (follower state only) | **HIGH if done naïvely**: blockwise comp must be state-carry-based (phase-carry pattern of `pad.py:54`) or RMS envelope computed with full-history semantics; acceptance test = restart-from-state renders bit-identical audio | method idea | A [S10] (quote; **no numeric compressor settings appear in the published interview** — ranges above are repo-native, set as instruments: "ranges, not presets") | **ADOPT NOW** | Falsifier: if makeup gain pushes the pre-limiter level so the limiter binds and the master loop gives up (`master/chain.py:62-77` gives-up condition), the codec gate goes red → parameter ranges shrink, not the axis |
| L16 | B3 | Butch Vig (Garbage "As Heaven Is Wide") | Multi-take doubling with micro-timing offsets ("3 bass tracks slightly out of sync... strange flangey effect") | plan | per event kind: `double_copies: 0..2`, `double_offset_frames: 1..50` | planner event cloning + existing per-voice routing | comb-filter notch positions at 1/(2·offset) — measurable null location in rendered spectrum | ×(copies+1) voices for doubled kinds — event-count bounded | none (offsets are plan integers) | method idea | A [S10] | **SPIKE** | Falsifier: at offsets ≥ 1/(60 kHz·...) the flange null leaves the audible band for low bass fundamentals; if the doubled bass measures identical RMS envelope and no null inside 40–800 Hz, effect is inaudible — cut |
| L17 | B3 | Butch Vig / Smashing Pumpkins | Massive track stacking (91–130 guitar layers; Garbage "48 tracks of samples and loops") | render | n/a | n/a | n/a | n/a | n/a | method idea | A [S10] + R (README.md:111-115) | **REJECT** | Budget, not taste: 1500 MB RSS budget vs 15-min ambient already **measured at 2177 MB** — zero headroom for voice-count multiplication beyond existing mix architecture. Doubling (L16) is the bounded legal subset |
| L18 | B1b | Brian Eno (On Land) | Space-as-instrument: distinct room/IR character per surface ("place" as compositional material) | render | n/a | n/a | n/a | n/a | n/a | method idea | C (only secondary mentions retrieved: academic *Music Beyond Airports* collection, "in the liner notes to On Land Eno went so far...") — no primary text fetched | **REJECT** | Grade C without a corroborator (rule: C needs A/B). Executable core dies regardless: convolution needs IR assets (new dependency + large memory) and the architecture has ONE reverb fed by the whole main bus (`render.py:293-298`). Per-bus sends (L14) is the legal fragment of this idea |
| L19 | B1c | Brian Eno | Oblique Strategies / probabilistic rule deviations as process ("greater chance it's going to play a fifth than a flat fifth") | n/a | n/a | n/a | n/a | n/a | n/a | method idea | A [S11] (Eno's own words) | **REJECT** | Not by evidence — by rule: non-deterministic process steps are banned (RNG dies at compose, `planner.py:1-4,611-612`). The *deterministic residue* is already banked: T1 polyperiod loops implement incommensurable periods (Eno's own 23½ / 25 7/8 / 29 15/16 s description, [S11]) with probable-interval biases as fixed plan-time weights — this axis is **already built**, the research confirms it rather than extends it |
| L20 | B5a | Rick Rubin (via Kilhoffer, corroborated by Vig) | Subtraction as arrangement: per-section per-instrument silence + whittled lengths ("start out at six minutes, then get whittled down to the best parts") | plan | `arrangement_mutes: list[(kind, section_index, mute 0|1000)]` — **binary only** (poles, never degrees); optional tighter `track_length_targets` in station | `render.py` bus mixing — skip events per mute; `station.yaml` length targets | silent-span log; gate 5 arc unchanged (mutes shape the arc the plan *declares*); event count drops (cheaper) | ≤ 0 (removes work) | none — mutes are plan-static; a muted section reprise of a déjà-vu stays byte-identical by construction | method idea | B [S12] (Kilhoffer on Rubin) + A [S10] (Vig: "we'd add and subtract until we'd get to a point where the song still came across") — **2 independent sources, A+B** | **ADOPT NOW** | Falsifier: if a mute on a section that a Director move targets (`applies_to`, `plan.py:124-132`) produces a crossfade into silence the plan didn't declare, validation catches the mismatch — then mutes required to be Director-aware, a bounded fix |
| L21 | B4 | Kanye West / Mike Dean | Pre-limiter saturation/grit as sonic identity ("distorted acid instrumental", "rough-edged") | master | `saturation_drive_millibels: 0..1800`, `saturation_mix_permille: 0..1000` (0 = off) | `master/chain.py` — inserted BEFORE the limiter (sat must shape tone, not loudness; ceiling is −4.0 dBFS, `presets/station.yaml` `ceiling_millibels: -400`) | harmonic ratio k2/k1 on a sine probe (offline spike test); codec gate must stay green | tanh curve: O(frames), negligible | none — static curve | method idea | B [S12] | **SPIKE** | Falsifier: the master loop re-limits up to 4 iterations and gives up when the limiter binds (`master/chain.py:42-43,62-77`); if drive past the audio-range limit produces give-up/mis-limit behavior the ranges are wrong → measure and cap, or the row dies at that drive value |
| L22 | B4 | Butch Vig | Tape glue on 2-bus ("kind of glues everything together and is very forgiving") | master | same engine as L21, separate instance | same (L21) | same as L21 | negligible | none | method idea | A [S10] | **DEFER** | identical engine as L21 (grit); shipping two instances before one passes a gate-run is waste — adopt after L21 passes, if the second instance still has a use |
| L23 | B5b | (station) | Global voice/simultaneity budget field (cap concurrent events to defend RSS) | plan | `max_concurrent_events: 0..5000` unbounded default | `render.py` mix loop guard | RSS ceiling test on 15-min ambient (already measured 2177 MB > 1500 MB budget, README.md:111-115) | 0 | none | method idea | R | **DEFER** | Deferred, not rejected: RSS overshoot is real and already measured, but the *fix* belongs to the station quiet-lane rework, not to either artist axis; revisit with the memory workstream |
| L24 | A1 | Wagner | Consequence row: make T16 mode-shifts audible in the bed (motorik pad is root+octave+twelfth — no third — so a T16 reharmonization is inaudible in the sustained bed) | plan+render | inherits L06 `PadEvent.partials`: bed gains an optional mode-appropriate third partial declared per segment | `synth/pad.py` via L06 field; `compose/planner.py` mode-shift logic fills the partial | perceptual proxy = centroid shift at section boundary when mode flips (declared vs measured) | +1 partial ≈ +8.3 ms/block [M1] | none | method idea | R (t11/t16 audit from Part 6) + B [S1] (non-scale coloration) | **SPIKE** | Falsifier: if gate 6 still resolves one centroid per section (it does, `validate.py:465-540`) the shift is only verifiable at *section-boundary deltas* — measured delta < declared epsilon in a cold A/B render → the T16-in-the-bed claim dies as inaudible and the row is cut |

---

## 4. Proposed Plan Vocabulary

**Rule unchanged**: integers and rationals only, midis/millibels/permille/frames, no floats, no strings-as-behavior. New/changed fields (all additions to `src/indiegen/plan.py` unless noted; `presets/` only carries ratio pools and preset defaults):

```jsonc
// plan.py — canonical fragment (additions marked with *)
{
  "harmony": {
    "chord_segments_per_section": 1,          // * 1..8 (1 = current behavior)
    "chord_tone_intervals": [0, 3, 7],        // * list[u0..11], len 3..5
    "chromatic_budget_permille": 0,           // * 0..1000
    "planar_offset_semitones": 0              // * -12..12
  },
  "tuning": {
    "tuning_system": 0                        // * 0=12-TET (current), 1=JI-pure (drone ratio pool governs)
  },
  // EventBase additions (plan.py:164-174), inherited by every event kind:
  "envelope_curve": 0,                        // * 0=linear (current), 1=exp tau=A/4
  // PadEvent changes (plan.py:177-184):
  "partials": [                               // * REPLACES partials:int + partial_detune_cents
    { "ratio_num": 1, "ratio_den": 1, "amplitude_millibels": 0, "detune_cents": 0 },
    { "ratio_num": 2, "ratio_den": 1, "amplitude_millibels": 0, "detune_cents": 0 },
    { "ratio_num": 3, "ratio_den": 1, "amplitude_millibels": 0, "detune_cents": 0 }
  ],                                          // legacy default == current audio exactly
  "pad_envelope_segments": [                  // * optional, list len 0..4
    { "delta_frames": 4, "held_partial_weights": {} }
  ],
  // buses (plan.py:112-122 BusGain family):
  "reverb_send_permille": 0,                  // * per bus, 0..800
  "delay_send_permille": 0,                   // * per bus, 0..600
  "drum_bus_comp": {                          // * optional structured value
    "threshold_millibels": 0,   "ratio_permille": 2000, "attack_frames": 10,
    "release_frames": 1000,     "makeup_millibels": 0,  "mix_permille": 0
  },
  "arrangement_mutes": []                     // * list of {kind, section_index, mute: 0|1000} — BINARY
  // master chain (master-stage only):
  "saturation_drive_millibels": 0,            // * 0..1800
  "saturation_mix_permille": 0                // * 0..1000
}
```

**Compatibility**: the legacy default for every added field equals today's behavior bit-for-bit. `PadEvent.partials` migration is the one structural replacement (replacing `partials:int` + `partial_detune_cents:list[int]`); its default serialization must produce exactly the current partial set {1,2,3} at 0 dB.

**Invalidation warning (mandatory statement per prompt)**: every one of these changes the serialized Plan → **every `plan_sha256` changes → all README hash columns, all golden plans, and every plan-hash test must be re-derived in the same change**. A change that updates `src/` but not the hash collateral does not pass review. This applies to `docs/` hash tables and to `tests/` fixtures.

---

## 5. DSP Integration Map

| Field (art.) | Function touched | Change type | Notes |
|---|---|---|---|
| `chord_segments_per_section` (L02) | `compose/planner.py` `_chord_roots` :286, `_assign_modes` :227 | derivation extension | per-segment roots derived deterministically from section root + segment index; Director untouched (`director.py:186-226`) |
| `chord_tone_intervals` + `chromatic_budget_permille` (L01) | `theory/scales.py` + `planner.py` chord-pool builder | new pool builder | today's T1 chords are scale-filtered static lists (`t1_polyperiod.py`); the pool builder filters by declared intervals, scale-or-interval gated per permille |
| `planar_offset_semitones` (L03) | `planner.py` voicing post-pass | post-pass | applied after pool build, before event emission |
| `PadEvent.partials` (L06) | `synth/pad.py:50-55` loop | per-term weight | one line change inside the loop: `voice += amp_k * sin(...)`; amplitude comes from the partial entry; `pad_state` unchanged (phase carries already per-index) |
| `pad_envelope_segments` (L07) | `synth/pad.py` control layer | new (pattern of `drone.py:56-69`) | amplitude is a pure function of local frame → blockwise-determinable, no carries beyond what exists |
| `envelope_curve` (L10) | `synth/env.py:50-80` | branch | replaces/if-branches the single linear ramp; pure function of local frame |
| `reverb_send_permille`, `delay_send_permille` (L14) | `render.py:155-160,266-285,293-298` | **bug fix + feature** | send lists become fully read (kill the `[0]`-only defect); reverb/delay host may accept per-bus input sums |
| `drum_bus_comp` (L15) | new `synth/drumcomp.py` + `render.py` drum-bus point | new stage | envelope follower with carry state (pattern: `pad.py` phase carries); deterministic restart test mandatory |
| `arrangement_mutes` (L20) | `render.py` mix loop + `station.yaml` targets | skip logic | pure subtraction of work; Director must never target a muted section (`plan.py:124-132`) |
| `saturation_drive/mix` (L21) | `master/chain.py` pre-limiter stage | new stage | BEFORE the limiter; interacts with the 4-iteration re-limit loop — measured before ranges unlocked |
| `tuning_system` + preset ratio pools (L09) | `synth/drone.py` + `presets/ambient.yaml` | preset + gate | declared, not averaged: pools chosen per mode; measured beat-rate test |

**Feasibility spikes (measured this session, `/tmp/opencode/spike_dimensions.py`, single-thread BLAS)**:
- pad: +8.26 ms per partial per 131072-frame block; N=3→9 = +8 s CPU per pad voice over an 8-min track.
- drone: ~59.5 ms per partial per block (pink-LFO control layer, ~7× the pad's cost); 6→12 partials = +58 s per drone voice per track. **Drone partial-count growth is the expensive direction; per-partial amplitude on the pad is nearly free.**
- intonation: measured JI-vs-12-TET deltas and the ambient beat rate 13.37 Hz (see L09).
- envelope: exp(tau=A/4) reaches 90% at 0.575·A vs linear 0.90·A — the acceptance metric is the rise-time ratio; a first-100ms centroid proxy is insensitive and is explicitly rejected as the metric.
- spectral-envelope model (offline): centroid 1095 Hz (flat N=9) vs 699–770 Hz (1/n ± formant peak choices) — hundreds of Hz of movement without touching any pitch field; this is the gate-6-visible handle.

---

## 6. Conflict Resolution

Per prompt rule: **poles are integers, never averaged**; when two poles fight, the lane picks a pole per section (the plan declares which) or the mechanism dies.

1. **Vig dry vs Eno wet (B1)** — both live in the same DSP (the send level). Resolution: `reverb_send_permille` per bus per section is a plan integer; a section uses a pole (0 or a declared high value), not a blend. Dry capture (Vig's invariant) is retained as the *default* pole 0; "place" (Eno) becomes a declared send on chosen buses. No averaging; the reverb host sees either bus-level or none.
2. **Rubin subtraction vs Kanye maximalism (same production lane)** — the Yeezus Sessions make the contradiction literal (MBDTF: 180 days layered; Yeezus: 30–40 days sparse). Resolution: arrangement is per-section binary — `arrangement_mutes` mute 0|1000 — never opacity; density budgets come from the existing density field. The two artists occupy different *sections*, not a blend in one section.
3. **Satie static vs Vivaldi/Wagner directed harmony (A-lane)** — `chord_segments_per_section` is the integer pole: 1 = static (Satie default, already the repo default), 2–8 = directed harmonic rhythm. Discrete levels, no interpolation between "some" and "more".
4. **Stockhausen moment form vs station gate 5 (planned arc)** — moment form's no-global-curve requirement would plan a flat arc and degenerate the gate. Resolution: moment form is rejected at global scope (L13); section-internal static (already implemented) is the legal fragment. No partial adoption that breaks the gate contract.
5. **JI purity vs the dorian/aeolian mode pool (A8/intonation)** — measured conflict (5/4 partial vs mode's third: +86.3¢/13.37 Hz beat). Resolution options are discrete: (a) drop 5/4 from the dorian pool (beat → small measured residual), (b) restrict melodic degrees near the conflict, (c) declare `tuning_system: 0` and document the coloration as intentional. **No "tempered 5/4" compromise tuning** — a flattened 5/4 is exactly the average the rule forbids; the mode-conditioned pool (option a, default) is what ships, with the measured beat rate as its acceptance number.
6. **Compression glue vs the no-second-pass rule (B2/B4 vs rule 0)** — compression/saturation are *transformations applied to known audio*, not second measuring passes; both are legal inside the existing `master/chain.py` loop's single-pass contract. Resolution: saturation sits pre-limiter (tone, not loudness); compression on the drum bus reads the drum bus's own signal only; neither introduces a new measuring pass. Poles: comp either engages at `threshold_millibels` or is bypassed by `mix_permille: 0` — no soft half-state.

---

## 7. Risk Register

| risk | evidence | mitigation / acceptance |
|---|---|---|
| Determinism regression in the drum compressor (L15) | blockwise audio requires state; naive envelope followers are history-dependent | carry-state pattern (`pad.py:54` style); mandatory test: restart-from-stated-block renders bit-identical audio; also full-render byte-equality on re-run |
| per-bus send summation bug (L14) | `fx_sends`/`delay_sends` only `[0]` read today (`render.py:155-160,266-285`) | treat as bug fix; dry-bus bit-diff test when send lists are enabled |
| CPU: pad/drone partial growth | measured 8.26 ms (pad) vs 59.5 ms (drone) per partial/block [M1] | pad N ≤ 9; drone partial growth stays with the ambient preset (no new drone fields this cycle); budget table updated with measured numbers |
| RSS | 15-min ambient = 2177 MB vs 1500 MB budget (README.md:111-115) | L17 (layering) rejected; L20 mutes *reduce* events; L23 voice budget deferred to the memory workstream |
| Gate 6 static-timbre variance sensitivity | one centroid value per section today (`validate.py:465-540`); L06/L07 move centroids by 100s of Hz | centroid changes are plan-declared (partials + segments), so static-timbre comparisons compare plan-declared against measured; falsifiers defined per row |
| Master chain interplay | 4-iteration re-limit, gives up when limiter binds (`master/chain.py:42-43,62-77`); ceiling −4.0 dBFS (`station.yaml` `ceiling_millibels: -400`) | L21 saturation pre-limiter with measured give-up behavior; ranges unlocked only after the codec gate stays green |
| Hash invalidation | every Plan schema change moves `plan_sha256` | rejection rule stated in §4: hash collateral (README columns, goldens, plan-hash tests) re-derived in the same change |
| Live dead fields discovered (rule 9 = bugs, must not ship silently) | `fifth_permille` (`config.py:176`, set `motorik.yaml:95`, read nowhere); `palette` (`plan.py:436`, `planner.py:763`, read nowhere, advertises nonexistent `formant`/`noise` instruments); `SectionPlan.transform` (`plan.py:344`, copied `planner.py:940`, read nowhere); send lists `[0]`-only (`render.py:155-160`); no `passes` field despite BRIEF:322 | report them here; each is a separate bugfix change (not bundled into artist work), with a linked issue number per the repo's universal rules |
| IP | all artist mechanisms are method/idea level | no samples, no transcription of copyrighted recordings, no audio assets; artists' own words quoted with URL + grade; the one recording-specific device (L11 vibrato) is rejected precisely on this ground |

---

## 8. Not Doing

- No second measuring pass, no reference-track matching, no ML, no realtime, no web UI.
- No convolution/IR room modeling (new dependency + assets; the single-reverb architecture is untouched).
- No counterpoint voice allocator (event-model rewrite, out of scope).
- No per-sample vibrato or expressive control (no transcription of copyrighted recordings, no per-sample DSP path).
- No Vexations-style 840× degenerate repetition (existing déjà-vu covers the legal subset).
- No 15-minute memory benchmarking beyond the already-measured numbers (no new renders of multi-minute material to pad the risk register).
- No score-measure-perfect harmonic analyses beyond the structural facts actually retrieved (measure 1/6/10/12 for the Tristan chord; no invented bar numbers anywhere).
- No new dependencies (numpy-only spikes; compressor/saturation implemented repo-natively).
- No `src/` or `presets/` writes in this research phase (deliverable is this document + memory records).
- SM's "range is an instrument" applied to *presets*, not to Plan-level free floats: no float parameters were requested anywhere.

---

## 9. Next Step

Three change_ids (prompt asks for 2–4, measurable):

### `c21-pad-partials-intonation` (L06 + L09 + L10)
The three cheapest-highest-leverage moves: `PadEvent.partials: list[Partial]`, `tuning_system` + mode-conditioned drone ratio pool, `envelope_curve`.
Acceptance criteria:
1. `ruff check`, `mypy`, `pytest` all green.
2. Legacy presets render **bit-identical** audio (legacy default partials = {1,2,3} @ 0 dB, curve=0, tuning=12-TET).
3. Ambient preset with the dorian ratio pool (5/4 dropped): measured partial-vs-scale beat rate ≤ 6 Hz at f0=220 (unit test asserts the frequency math; the 13.37 Hz baseline is recorded in the test as the before-number).
4. `envelope_curve=1` changes measured 90% rise time to 0.575·A ± tolerance and is bit-distinct from curve=0.
5. Pad N=9 CPU within measured bounds: ≤ 96 ms per 131072-frame block per voice (measured 95.3 ms) recorded in the budget table.
6. All hash collateral re-derived in the same change (README hash columns, goldens, plan-hash tests).

### `c22-per-bus-sends-drum-comp` (L14 + L15)
Acceptance criteria:
1. All send indexes read (test: a second wet source becomes audible when its send > 0; dry buses stay bit-identical when their send = 0).
2. Drum-bus compressor: crest factor drops ≥ 1.5 dB at the default compact settings (measured before/after in test); codec gate green (no overs regression at the −4.0 dBFS ceiling).
3. Compressor restart-from-state renders bit-identical audio (carry-state determinism test).
4. Render CPU on the motorik preset ≤ +10% versus today's measured baseline.
5. Full gate suite green; hash collateral re-derived.

### `c23-chord-segments-mutes` (L02 + L01 + L20 + L04, spikes first: L03/L07/L08/L16/L21/L24)
Acceptance criteria:
1. `chord_segments_per_section = 2` on the motorik preset passes all 13 gates on regenerated goldens (declared changes match plan-log exactly).
2. Chromatic events (interval-set sonorities) occur at or under `chromatic_budget_permille`; unit test buys the plan-log count vs the budget.
3. `arrangement_mutes` validation rejects any non-{0,1000} value (poles only); a muted section re-renders byte-identically when reprised.
4. Bass register offset field replaces the hard-coded root-12; default value renders bit-identically to today.
5. Gate suite + hash collateral re-derived; the six spike rows land only after L02/L01/L20 are green, each behind its own falsifier numbers.

**Bugfix changes to file separately (not bundled with artist work, per the dead-field rule)**: `fifth_permille`, `palette`, `SectionPlan.transform`, send-list `[0]`-only rendering, missing `passes` field (BRIEF:322) — each with a linked issue number.

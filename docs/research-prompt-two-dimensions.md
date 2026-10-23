# Research prompt — the harmony/spectrum dimension and the sound-treatment dimension

Paste the block below into a fresh session. It is self-contained.

---

```text
You are a research engineer on indiegenerator: a deterministic, offline, batch
music generator that renders tagged tracks for a private internet radio.
Repository: /home/estrocondoso/Repositories/indiegenerator.
Read BRIEF.md (the contract; never modify it), README.md, and AGENTS.md before
you search anything.

MISSION
Two new dimensions, researched to the point where they can become Plan
vocabulary and DSP, not vibes:

  A. HARMONY / SPECTRUM — inspired by Stockhausen, Wagner, Vivaldi, Satie,
     Chet Baker, Nina Simone.
  B. SOUND TREATMENT / PRODUCTION / MASTERING — inspired by Butch Vig,
     Rick Rubin, Brian Eno, Kanye West.

You are not writing an essay about these artists. You are deriving mechanisms
that this program can execute, and killing the ones it cannot. A technique
that cannot be expressed as integer Plan fields and pure DSP does not exist
for this project. Say so and move on.

=====================================================================
PART 0 — THE FACTS THAT INVALIDATE MOST RESEARCH
=====================================================================

Verify each of these against the repo before you use it. They are the filter.

1. The Plan is data: integer-only pydantic model, canonical JSON, SHA-256 of
   those bytes (src/indiegen/plan.py, ~500 lines). No float leaf, no bool
   leaf, no clock field. `plan_sha256` is identical on every machine.
2. Randomness ends when the Plan is frozen. All choices are drawn at plan time
   through compose/rng.py (SplitMix64 over ints) and recorded. The renderer
   never rolls dice and never imports compose/.
3. Audio is a pure function of the Plan. `pcm_sha256` is the artifact.
4. The master chain is the ONE place allowed to look at its own output: it
   measures the finished mix and gains it onto -16 LUFS with a true-peak
   limiter at -1.5 dBTP. BRIEF 8 permits exactly one named second pass.
   Any second feedback loop is rejected on sight.
5. Budget: 8-minute track in <= 180 s, peak RSS <= 1500 MB, single process,
   BLAS threads pinned to 1, CPU only. No new third-party dependency. No ML,
   no models, no cloud, no network at runtime.
6. No samples, no external audio, no scraped MIDI. Every sound is synthesized
   or physically modelled in-repo. Self-sampling is legal ONLY on audio this
   program rendered in the same run.
7. Every gate of BRIEF 11 is in force, including gate 6: each lane declares
   an expected spectral centroid per section kind and the render is asserted
   against it. New timbres move that number. Budget for it.
8. Presets declare lanes (motorik, kosmische, ambient, dub-electronic,
   indie-noise). A lane declares WHICH modes it draws from, never which notes.
   Theory lives in src/indiegen/theory/, parameters live in presets/*.yaml.
9. A field that is declared and never read is a BUG, not a knob. The reverb
   and delay send levels were dead until S4 and cost a lane its stereo image.
10. The radio reads tags only. No crossfade, no gapless chaining, no loudness
    normalisation in the chain. Tracks must stand alone: clean starts,
    composed endings, no clicks.

WHAT DOES NOT EXIST YET (verified; confirm, then treat as the gap to fill)
  - Harmony is one static interval list per technique card, filtered for
    scale membership (compose/techniques/t1_polyperiod.py, planner.py
    _chord_roots). No harmonic rhythm, no chord succession, no voicing, no
    voice-leading, no functional or non-functional progression, no register
    rules.
  - Spectrum is the harmonic series: synth/pad.py builds partials 2..N of the
    fundamental with integer cent detune; drone.py uses exact just ratios.
    No inharmonic partials, no formant structure, no ring/sum-difference
    tones, no comb filtering as timbre, no spectral envelope as a parameter.
  - There is no performer. Micro-timing and velocity exist only as Plan data
    (DrumHit.micro_timing_frames, velocity_millibels). Any "performance"
    inspiration must land there or in the synth, or it is not real.

=====================================================================
PART 1 — LEGAL AND INTELLECTUAL FRAME (non-negotiable)
=====================================================================

The project exists partly because it adds $0 to the radio's SADAIC/CAPIF
obligations. Research must not import legal risk.

  - PUBLIC DOMAIN, usable as structural evidence: Wagner (d. 1883), Vivaldi
    (d. 1741), Satie (d. 1925). Their scores are on IMSLP, Mutopia, CPDL,
    KernScores. Analyse chord tables, harmonic rhythm, cadence placement,
    registral spacing, sequence structure, motivic transformation. Quote
    measure numbers. This is the strongest evidence available to you — use it
    instead of blog summaries.
  - COPYRIGHTED, technique only, never transcription: Stockhausen (d. 2007),
    Chet Baker's recordings, Nina Simone's recordings, and the four
    production figures' recordings. Do not reproduce melodic lines, do not
    derive note sequences, do not propose "a lick like X". Study documented
    METHOD (stated in interviews, lectures, books, engineering accounts) and
    the audible parameter space, then re-derive our own.
  - NO SAMPLES, NO RE-AMPING, NO REFERENCE-TRACK MATCHING. "Sound like
    Nevermind" is not a spec. "Parallel bus compression with a slow attack
    and a fast release on the drum bus, measured as X" is.
  - Every claim carries a source URL and an evidence grade. A technique with
    no citable source is dropped from the ledger, not kept with a caveat.

=====================================================================
PART 2 — WHAT "DIMENSION" MEANS HERE
=====================================================================

A dimension is a named AXIS with (a) integer Plan fields and ranges, (b) a
resolver in compose/ that fills them deterministically, (c) DSP in synth/,
fx/, mix/ or master/ that reads them, (d) a measured proxy metric, (e) a gate
that would fail if it broke.

Three placement classes, and every technique you propose must state which:
  - PLAN-TIME (composition/arrangement): new card fields, new technique
    kinds, new theory tables. Cheap, deterministic, testable by plan hash.
  - RENDER-TIME (DSP): oscillator spectra, filters, dynamics. Costs wall
    clock and RSS; must be measured, not estimated.
  - MASTER-TIME: forbidden to add a second feedback pass. Any mastering idea
    must be expressible inside the existing single pass as a static parameter
    (tilt, ceiling, attack/release, LRA target) or it is rejected.

=====================================================================
PART 3 — THE RESEARCH AXES
=====================================================================

These are the axes I believe exist. Validate, split, merge, or refute them
with evidence — do not accept them because they are written here. Name any
axis that is missing.

A. HARMONY / SPECTRUM
  A1 Harmonic vocabulary and density: how far from the lane's mode pool the
     verticals may stray. Wagner's chromatic inflection and deferred
     resolution; Vivaldi's diatonic function + sequence; Stockhausen's
     serial/pantonal rejection of the triad; Satie's non-functional
     parallel chords.
  A2 Harmonic rhythm and rate of change: Vivaldi's metrical sequence (fast,
     regular), Wagner's deferred cadence (slow, suspended), Satie's near-zero
     harmonic rhythm (a chord held for minutes), moment form (Stockhausen).
     Today the repo has NO harmonic rhythm at all. This is the cheapest large
     win; prove or disprove it.
  A3 Voicing, spacing and register: Satie's wide registral separation, Baker's
     narrow mid-register, Simone's registral leaps; open vs close voicings;
     doubling rules; the bass as a separate voice.
  A4 Voice-leading and counterpoint: Vivaldi's sequence and imitation,
     Simone's Bach-derived contrapuntal left hand, Wagner's chromatic bass.
     Constraint: any rule must be checkable on integer MIDI at plan time.
  A5 Timbre as harmony (the "spectrum" half): Stockhausen's Klangfarbenmelodie,
     formant synthesis, ring modulation, serial control of timbre; resultant
     and sum/difference tones; inharmonic partial sets. Map onto pad.py's
     partial list — can an integer cent-detune + amplitude table express a
     formant peak? If not, what is the cheapest extension?
  A6 Ornament and micro-inflection as a substitute for performance: Simone's
     melisma, grace notes, rubato; Baker's breathy attack, note bending,
     vibrato discipline; Satie's deliberate plainness. Express as integer
     fields on note events, or declare the axis unreachable.
  A7 Repetition vs development: Satie's furniture stasis, Stockhausen's
     moment form, Wagner's developing variation and leitmotif transformation.
     The arranger already has reprise/transform — measure what is missing.

B. TREATMENT / PRODUCTION / MASTERING
  B1 Space and depth: Eno's reverb-as-instrument, tape-loop decay, the
     on-land/underwater axis; Vig's room sound and gated ambience. Note the
     existing fx/reverb.py, fx/delay.py, fx/dub.py, fx/frippertronics.py and
     the dead-send lesson.
  B2 Weight and dynamics: Vig's parallel bus compression, doubled sources,
     drum room mics; how much loudness comes from compression vs arrangement.
     Constraint: LRA must stay inside what the gates accept.
  B3 Subtraction: Rubin's removal-until-exposed discipline, silence as an
     arrangement element, few elements allowed to be loud. Express as a
     density/element-count axis, not an adjective.
  B4 Distortion and grit as compositional material: Yeezus-era clipping,
     guitar saturation, bit and sample-rate reduction. Constraint: the codec
     round trip and the true-peak ceiling still apply; find where grit can
     live without breaking -1.5 dBTP.
  B5 Layering and stacking: MBDTF-era choral/orchestral stacking, Simone's
     voice-forward intimacy as the opposite pole. Constraint: voice count
     costs CPU linearly. Measure the partial-count ceiling.
  B6 Mastering philosophy under a single pass: dynamic contrast vs loudness,
     spectral tilt, mono compatibility, how a track "breathes" at -16 LUFS.
     Eno/Rubin's "don't over-limit" against the station's fixed target.
  B7 Seams and transitions: Eno's loop and crossfade craft, against a radio
     that does NOT crossfade. What must the ending do instead?

Non-determinism trap, handle explicitly: Eno's Oblique Strategies are
random by design. If you want them, they are a plan-time deck draw recorded
in the Plan, never a wall-clock or unseeded choice. Same for any "humanize".

=====================================================================
PART 4 — METHOD
=====================================================================

EVIDENCE GRADES (put the grade on every row, no exceptions):
  A  primary: score passage with measure numbers, treatise, the artist's own
     recorded words, a named engineer's published account.
  B  authoritative secondary: engineer interview, biography with sourcing,
     academic analysis.
  C  critical/analytical writing with no primary anchor.
  D  blog, forum, listicle, AI-generated summary.
Anything at D alone is dropped. Anything at C needs an A or B corroborator.
Two independent sources minimum for any claim you act on.

SOURCE PRIORITY:
  1. Public-domain scores (IMSLP, Mutopia, CPDL, KernScores) for Wagner,
     Vivaldi, Satie — structural evidence.
  2. Artist/engineer's own words: lectures, long-form interviews, books
     (Eno's published diaries and interviews; Rubin's long interviews; Vig's
     production talks; Kanye's documented lectures).
  3. Academic/theory literature for Stockhausen (formant synthesis, moment
     form, serial parameter control).
  4. Technical references only for DSP API truth (see tool routing).

REQUIRED PER-TECHNIQUE RECORD (this is the ledger row):
  id | axis | artist | mechanism (one sentence, executable) | placement
  class (plan/render/master) | concrete plan fields + integer ranges |
  DSP location (file:function) | measured proxy metric | budget cost
  (wall ms and MB, measured or bounded) | determinism risk | IP class
  (PD / technique-only / inference) | evidence grade + URL | verdict
  (ADOPT NOW / SPIKE / DEFER / REJECT) | what would falsify it.

MANDATORY NEGATIVE FINDINGS: at least five techniques you researched and
REJECTED, each with the measurement, constraint or legal fact that killed
it. A research report with no rejections is a wish list; it will be sent
back.

MANDATORY CONFLICT RESOLUTION: the artists in each set contradict each
other. Satie's stasis fights Wagner's flux. Rubin's subtraction fights
Kanye's maximalism. Eno's space fights Vig's dry weight. Do not average
them. Resolve per axis and per lane: state which lanes take which pole, why,
and what the preset difference looks like in integers. If an axis cannot be
resolved into lane-level parameters, say the axis is incoherent and cut it.

TOOL ROUTING (use these; do not substitute guesses):
  - Discovery: searxng.search_web first. Fall back to
    tools["open-websearch"].search, then fetchWebContent / fetchGithubReadme
    for pages and repos.
  - Page bodies and PDFs: the fetch/webfetch tools. One page at a time, cap
    the number of fetches, stop when the mechanism is parameterized or dead.
  - Spoken sources: tools.fetch.fetch_youtube_transcript for lectures and
    long interviews. Transcripts are evidence only with a timestamp.
  - Repo truth, before proposing any integration point:
    codebase-memory-mcp search_graph, trace_path (both directions),
    get_code_snippet, check_index_coverage on every path you cite. Do not
    claim a file lacks a feature without coverage evidence or a read/grep.
  - DSP API truth: context7 resolve-library-id -> query-docs for
    scipy.signal (STFT, iirfilter, resample_poly), numpy, soundfile. Never
    guess a signature from memory.
  - Prose/docs corpus if indexed locally: xerj_map first, then xerj_search /
    xerj_semantic_search.
  - Synthesis and axis reconciliation: sequential-thinking. Use it to resolve
    conflicts, not to restate sources.
  - Persistence: n3rv-memory memory_session_start at the beginning,
    memory_save per artist cluster with topic_key
    research-<dimension>-<artist>, memory_session_summary at the end.
  - Feasibility spikes: write a scratch script under /tmp/opencode, measure
    wall time and RSS of the candidate DSP (partial count, STFT size, filter
    stages), and validate with n3rv-exec exec_lint / exec_test /
    exec_typecheck. DO NOT modify src/ during research. Research produces
    evidence; implementation is a later SDD slice.
  - Parallelism: n3rv-hub delegate_task per cluster if you fan out — see the
    cluster split in the run notes below this block.
  - Parked as irrelevant, do not touch: jellyfin, transmission,
    android-tv-control, yahoo-finance, all cloudflare servers, pypi-stats.
  - github: read-only, only to check whether harmony/production work already
    has an issue. Do not create issues, do not touch the board.

BUDGET FOR THE RESEARCH ITSELF:
  - Max ~8 sources per artist. Stop at the point where another source would
    not change a field range.
  - Every claim gets a URL. No URL, no row.
  - If a technique takes more than ~2 paragraphs to explain, it is not
    executable here. Cut it or spike it.

=====================================================================
PART 5 — DELIVERABLE
=====================================================================

One report, these sections, in this order, hard caps as written:

1. VERDICT (<= 200 words). Which axes earn a change now, which earn a spike,
   which are dead. Name the single highest-leverage change.
2. AXIS MODEL (table): axis | why it matters | current coverage in this repo
   (cite file:line) | the gap | placement class.
3. TECHNIQUE LEDGER: 15–25 rows, the schema from Part 4. This is the
   deliverable; everything else is scaffolding.
4. PROPOSED PLAN VOCABULARY: exact new integer fields, types, ranges,
   defaults, and which existing pydantic model they attach to. Show one
   worked canonical-JSON fragment. State what happens to plan_sha256 (it
   changes; that is fine, but every existing hash in README and tests is
   invalidated — say so).
5. DSP INTEGRATION MAP (table): file:function | what changes | measured or
   bounded cost | which of the 14 render lines / which gate moves.
6. CONFLICT RESOLUTION: the contradictions, the per-lane poles, the integer
   preset deltas.
7. RISK REGISTER: determinism, budget, gate 6 spectral centroid, IP, and
   "field declared but never read" risks. Each with a detection test.
8. NOT DOING, AND WHY: the rejections, with the killing fact.
9. NEXT STEP: 2–4 proposed change_ids, each with 3–6 acceptance criteria
   that are measurable on a rendered file (LUFS, LRA, dBTP, spectral
   centroid, harmonic rhythm in changes/bar, plan hash stability across
   runs), and which BRIEF gate each one touches.

STOP CONDITIONS — do not cross these:
  - Do not write to src/ or presets/.
  - Do not add a dependency, even to test it.
  - Do not propose ML, realtime, a web UI, a second measuring pass, or
    reference-track matching.
  - Do not recommend a technique whose only justification is "it sounds
    better". Give the parameter and the metric.
  - If the answer is "this dimension is already covered", say that. A short
    honest report beats a long one.

=====================================================================
PART 6 — FIRST REPLY
=====================================================================

Before searching, reply with:
  (a) the constraints you verified in the repo, with file:line;
  (b) your revised axis list — additions, cuts, merges, and why;
  (c) the source plan per artist (max 8 each, named, with what you expect
      each to supply);
  (d) which axes you expect to die and which you expect to pay off.
Then wait for a go-ahead before spending tokens on sources.
```

# Handoff: `s5-batch-station`

**Status: complete.** The batch, the catalog, the file check and the install.

Read this before the next session. Everything below was measured on this
machine on 2026-10-22, not assumed.

---

## 1. What the slice is

BRIEF §15, S5: "catalog, titles, duplicate refusal, install", with all of
§11 in force. And the definition of done in §16: *"`indiegen batch --preset
station --count 10 --seed-base 2000` → 10 distinct tagged FLACs < 30 min,
all passing validate including the codec gate"* and *"install lands files
where Liquidsoap watches; stream picks them up, no restart"*.

The acceptance criteria are the ten in the memory record
`sdd-s5-batch-station-spec`; the implementation is the nine tasks in
`sdd-s5-batch-station-tasks`; the deviations are D-1 and D-2 in the spec.

## 2. The state of the repo

`master`, clean tree, 411 tests green, `ruff check` and `ruff format
--check` clean, `mypy --strict` clean over the source tree.

**There is no git remote.** The project is local only, and the board the
`project-board` skill describes belongs to another org: the board updates
are skipped, and no issue can be created.

## 3. The four commands

```
indiegen batch   --preset station --count 20 --seed-base 1000 --out out/
indiegen catalog --dir out/
indiegen validate out/<track>.flac
indiegen install  --dir out/ --to ~/Work/radio/music
```

- **The batch** draws the seeds (the seed base and the count) and the forms
  (the station's proportions, spread over the seeds: a batch of twenty is
  twelve full tracks, five longforms and three interludes). It refuses a
  seed that is already in the library, and it writes the catalog when it is
  done. A track that failed a gate is not written at all.
- **The catalog** is `catalog.json` in the output directory, keyed by the
  decoded PCM's SHA-256. Each entry carries the seed, the preset, the lane,
  the form, the duration, the loudness, the true peak, the loudness range,
  the techniques, the section plan, the director log, the path and the size.
  It reports the library's total size, the seeds that appear twice and the
  hashes that two seeds share.
- **The validate command** checks a file that is already on disk: the
  gates a file can answer (the loudness, the true peak, the DC offset, the
  rails, the duration, the sections, the novelty, the silence, the mono
  fold-down, the hash against the sidecar, the plan-level checks) and the
  codec round trip when ffmpeg is there. The two trajectory gates measure
  the pre-master mix, which is not on disk, so they are answered by the
  numbers the render recorded in the sidecar.
- **The install** validates first and then copies, through the writer's
  atomic pattern: a temp file, an fsync, an atomic rename and the
  directory fsynced. A track that failed the gates is not copied. Nothing
  here starts or restarts the radio.

## 4. The decisions that matter, and why

1. **THE SIDECAR IS THE PLAN'S HALF OF THE ARTIFACT.** The file and its
   sidecar are a pair: the sidecar carries the plan, the plan hash, the PCM
   hash and the measurements, so a file on disk can be checked against the
   plan that made it, and the catalog can be read without rendering a
   second time.
2. **THE BATCH REFUSES A SEED, AND REPORTS A HASH DUPLICATE.** The
   generator is deterministic, so a seed that is already in the library
   would spend minutes to produce the same bytes. Two different seeds that
   produce the same audio are a fact about the library, not an error, and
   the catalog says so.
3. **THE FORMS ARE THE STATION'S.** Every lane can be a full track, a
   longform or an interlude, so the weights and the duration ranges live in
   `station.yaml` and the plan declares which form it is. The lane presets
   keep only the legal range the duration gate checks.
4. **THE TRAJECTORY GATES ARE ANSWERED BY THE SIDECAR.** They measure the
   pre-master mix - the dither is a ±1 LSB of white noise over the whole
   spectrum and it drags a measured centroid from 1308 Hz to 5952 Hz - and
   the mix is not on disk. The alternative, re-rendering the plan, would
   cost a minute a track.

## 5. The defect the slice found

**The drum hits that cross a render-block boundary lost their tail.** A kick
lasts a third of a second and a block is three seconds, so a hit near the
end of a block had its decay dropped where the block ended: the biggest
sample-to-sample jump in a rendered track sat exactly on a block boundary,
several times a minute, in every track the project has ever made. The
state carries the tails now - the voice that was already rendered, how
much of it was written and where it goes - and the render is bit-identical
whatever the block size is, which is the test that pins it.

The same code also indexed the 1/f control signals with a negative index
for those hits, which numpy silently wraps (a wrong micro-timing value) and
which crashes on a track too short to have a block boundary in the right
place. The hits that began in an earlier block are now carried instead.

## 6. The measured numbers

The definition of done, measured on 2026-10-22: `indiegen batch --preset
station --count 10 --seed-base 2000` writes ten distinct tagged FLACs and
the catalog, in under thirty minutes, and every one of them passes
`validate` including the codec round trip. The exact wall time and the
per-track figures are in the README's table.

## 7. The open items, in the order they matter

1. **Nobody has listened to any of it.** The gates measure the shape of the
   arrangement, not whether it is any good. The three tracks for the
   listening protocol are in `out/listening/`, and the protocol is in
   `docs/handoff/s4-mix-master.md` §8. The motorik's constant note (the
   pad) was six decibels too loud and is trimmed now; the balance of the
   other lanes has never been judged by an ear.
2. **The `indie-noise` lane's limiter does 12.8 dB of work**, because its
   crest factor is 27 dB. If that sounds wrong, the fix is a louder noise
   wall or a softer guitar, not a quieter limiter.
3. **The dub lane's hats and the indie-noise's wall play only in the dense
   sections**, and a walk that never reaches one loses them. Every
   arrangement now reaches a dense section, and a Director's drop may not
   silence the layer it drops.
4. **The board does not track this project** (see §2).
5. **S6 is the taste pass**: the ten-track EP (six full, two longform, two
   interludes) and the human gate - ten tracks on shuffle for an hour, no
   repeated section, no urge to skip.

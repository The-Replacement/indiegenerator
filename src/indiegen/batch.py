"""The batch: a library's worth of tracks, and the refusals.

The seeds are a window at or after the seed base, and the forms are dealt out
of the station's proportions. The window is not simply ``seed_base .. + count``:
the lane is drawn from the seed, so that window can miss a lane entirely - a
batch of twelve misses indie-noise 32 % of the time and dub 14 % (measured; see
docs/RESEARCH-2026-10-25-what-would-make-it-greater.md, F3). The batch looks
forward for the first window that covers every lane the station declares, so
one release is one of each colour, and it says when it moved. A seed that is
already in the library is still refused: the generator is deterministic and
the same seed would render the same bytes again.

The render itself is the one the CLI's render command does: compose, the
Director, the mix, the master, the gates, the file and its sidecar. A track
that failed a gate is not written: the radio is watching, and a file that
failed the gates must not exist.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import numpy as np

from indiegen.catalog import Catalog, build_catalog, write_catalog
from indiegen.compose import compose, director
from indiegen.compose.planner import Form, pick_lane
from indiegen.compose.rng import SplitMix64, seed_from_bytes
from indiegen.config import FormCard, Preset
from indiegen.errors import PlanError
from indiegen.master.chain import master
from indiegen.master.loudness import measure
from indiegen.metadata import build_tags, filename_for
from indiegen.plan import Plan, plan_sha256
from indiegen.render import BLOCK_SIZE, write_mix_stem
from indiegen.validate import (
    GateFailure,
    energy_correlation,
    run_gates,
    stereo_correlation,
    tension_correlation,
    timbre_measurement,
)
from indiegen.writer import TEMP_DIR_NAME, pcm_sha256, read_pcm, write_flac_atomic, write_sidecar_atomic


@dataclass(frozen=True)
class TrackOutcome:
    """One rendered track."""

    path: Path
    sidecar: Path
    seed: int
    lane: str
    form: str
    duration_seconds: float
    integrated_lufs: float
    sample_peak_dbfs: float
    true_peak_dbtp: float
    loudness_range_lu: float
    pcm_sha256: str


@dataclass
class RenderResult:
    """What rendering one plan did."""

    outcome: TrackOutcome | None = None
    failure: GateFailure | None = None


@dataclass
class BatchResult:
    """What a batch did."""

    tracks: list[TrackOutcome] = field(default_factory=list)
    catalog: Catalog = field(default_factory=Catalog)
    seconds: float = 0.0
    seed_base: int = 0
    requested_base: int = 0


def form_slots(forms: list[FormCard]) -> list[str]:
    """The forms of a batch, in the proportions the station declares.

    The weights are percentages, so the station's three forms are a hundred
    slots and a batch of twenty takes twenty of them.
    """
    slots: list[str] = []
    for card in forms:
        slots.extend([card.form] * card.weight)
    return slots


def batch_forms(forms: list[FormCard], count: int) -> list[Form]:
    """The forms of a batch: the station's proportions, spread over the seeds.

    The slots are sampled every len(slots) / count of the way, so a batch of
    twenty takes twelve full tracks, five longforms and three interludes,
    and they are spread over the seeds instead of in blocks.
    """
    slots = form_slots(forms)
    if not slots or count <= 0:
        return ["full"] * max(0, count)
    return [cast(Form, slots[(index * len(slots)) // count]) for index in range(count)]


LANE_SEARCH_LIMIT: int = 4096
"""How far a batch will look for a seed window that covers every lane.

Coverage becomes near-certain long before this: a window of twelve covers all
five lanes from a weighted draw most of the time, so the search almost always
returns the requested base. The limit exists so a preset that cannot cover -
a batch smaller than its lane count, or a degenerate weight - fails loudly
instead of spinning.
"""


def station_lanes(preset: Preset) -> list[str]:
    """The lanes a batch has to cover.

    The rule is the one ``pick_lane`` uses: a lane preset is its own single
    lane whatever its weight says, and a station is its positive-weight lanes.
    """
    if preset.kind == "lane":
        return [preset.lanes[0].lane]
    return [entry.lane for entry in preset.lanes if entry.weight > 0]


def lane_for(preset: Preset, seed: int) -> str:
    """The lane the composer draws for one seed, without composing anything.

    ``compose`` seeds one RNG from the preset's identity and the seed and
    spends its FIRST draw on ``pick_lane``, so this is the same value for one
    number instead of one render. tests/test_c35.py pins that agreement, so the
    mirror cannot drift from the composer silently.
    """
    rng = SplitMix64(seed_from_bytes(f"{preset.name}|{seed}".encode()))
    return pick_lane(preset, rng)


def covering_seed_base(preset: Preset, count: int, seed_base: int) -> int:
    """The first seed window at or after ``seed_base`` that covers every lane.

    The window is ``base .. base + count - 1``. Coverage is the ONLY reason to
    move: a window that collides with the library still raises, because that
    refusal is a safety net against re-rendering bytes that already exist, and
    stepping over it silently would turn a mistake into a surprise. A batch
    smaller than the lane count cannot cover them all and is left where it was
    asked for.
    """
    lanes = station_lanes(preset)
    if count < len(lanes):
        return seed_base
    wanted = set(lanes)
    for offset in range(LANE_SEARCH_LIMIT):
        base = seed_base + offset
        if {lane_for(preset, base + index) for index in range(count)} >= wanted:
            return base
    raise PlanError(
        f"no seed window at or after {seed_base} covers the lanes {sorted(wanted)}",
        preset=preset.name,
    )


def render_track(plan: Plan, out_dir: Path) -> RenderResult:
    """Render one plan into a directory: the file, its sidecar and its numbers.

    A track that failed a gate is not written: the radio is watching the
    output directory and a file that failed the gates must not exist. The
    failure is data, and the caller decides what to do with it.

    The mix is rendered to a float64 stem and read back through a memmap,
    so the whole-track array is on disk and not on the heap. The stem is
    removed whatever happens after it.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = out_dir / TEMP_DIR_NAME
    tmp_dir.mkdir(parents=True, exist_ok=True)
    stem = tmp_dir / f"{plan.file_token}_s{plan.seed}.mix"
    try:
        shape = write_mix_stem(plan, stem)
        mix = np.memmap(stem, dtype=np.float64, mode="r", shape=shape)
        pcm = master(plan, mix, BLOCK_SIZE)
        failure = run_gates(plan, mix, pcm)
        if failure is not None:
            return RenderResult(failure=failure)
        energy = energy_correlation(plan, mix)
        timbre, static = timbre_measurement(plan, mix)
        del mix
    finally:
        stem.unlink(missing_ok=True)

    filename = filename_for(plan)
    tags = build_tags(plan)
    path = write_flac_atomic(
        out_dir,
        filename,
        pcm,
        plan.sample_rate,
        tags,
        preset=plan.preset,
        seed=plan.seed,
    )
    decoded = read_pcm(path)
    measurements = measure(decoded, plan.sample_rate)
    digest = pcm_sha256(decoded)
    sidecar = write_sidecar_atomic(
        out_dir,
        filename,
        {
            "schema": "indiegen/sidecar/1",
            "preset": plan.preset,
            "seed": plan.seed,
            "lane": plan.lane,
            "form": plan.form,
            "plan": plan.model_dump(mode="json"),
            "plan_sha256": plan_sha256(plan),
            "pcm_sha256": digest,
            "measurements": {
                "duration_seconds": plan.duration_frames / plan.sample_rate,
                "integrated_lufs": measurements["integrated_lufs"],
                "sample_peak_dbfs": measurements["sample_peak_dbfs"],
                "true_peak_dbtp": measurements["true_peak_dbtp"],
                "loudness_range_lu": measurements["loudness_range_lu"],
                "stereo_correlation": stereo_correlation(decoded),
                "energy_correlation": energy,
                "timbre_correlation": timbre,
                "timbre_static": bool(static),
                # Shadow name retained after promotion for sidecar compatibility;
                # filecheck reads this key as the live gate 14 measurement.
                "tension_shadow_correlation": float(tension_correlation(plan, decoded)),
            },
        },
        preset=plan.preset,
        seed=plan.seed,
    )
    return RenderResult(
        outcome=TrackOutcome(
            path=path,
            sidecar=sidecar,
            seed=plan.seed,
            lane=plan.lane,
            form=plan.form,
            duration_seconds=plan.duration_frames / plan.sample_rate,
            integrated_lufs=measurements["integrated_lufs"],
            sample_peak_dbfs=measurements["sample_peak_dbfs"],
            true_peak_dbtp=measurements["true_peak_dbtp"],
            loudness_range_lu=measurements["loudness_range_lu"],
            pcm_sha256=digest,
        )
    )


def batch(
    preset: Preset,
    count: int,
    seed_base: int,
    out_dir: Path,
) -> BatchResult:
    """Render a batch of tracks and write the catalog."""
    if count <= 0:
        raise PlanError("a batch needs at least one track", preset=preset.name)
    existing = build_catalog(out_dir)
    known = {entry.seed for entry in existing.entries.values()}
    base = covering_seed_base(preset, count, seed_base)
    seeds = [base + index for index in range(count)]
    already = sorted(seed for seed in seeds if seed in known)
    if already:
        raise PlanError(
            "the seeds " + ", ".join(str(seed) for seed in already) + " are already in the library",
            preset=preset.name,
        )

    started = time.perf_counter()
    result = BatchResult(seed_base=base, requested_base=seed_base)
    forms = batch_forms(preset.station.forms, count)
    for index, seed in enumerate(seeds):
        plan = director(compose(preset, seed, None, forms[index]))
        rendered = render_track(plan, out_dir)
        if rendered.failure is not None or rendered.outcome is None:
            reasons = ", ".join(
                f"gate {item.gate} {item.check}" for item in (rendered.failure.failures if rendered.failure else [])
            )
            raise PlanError(f"the track at seed {seed} failed the gates: {reasons}", preset=preset.name, seed=seed)
        result.tracks.append(rendered.outcome)
    result.seconds = time.perf_counter() - started
    result.catalog = build_catalog(out_dir)
    write_catalog(out_dir, result.catalog)
    return result

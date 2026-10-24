"""The batch: a library's worth of tracks, and the refusals.

The seeds are the seed base and the count; the forms are dealt out of the
station's proportions; and a seed that is already in the library is
refused, because the generator is deterministic and the same seed would
render the same bytes again.

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
from indiegen.compose.planner import Form
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
    seeds = [seed_base + index for index in range(count)]
    known = {entry.seed for entry in existing.entries.values()}
    already = sorted(seed for seed in seeds if seed in known)
    if already:
        raise PlanError(
            "the seeds " + ", ".join(str(seed) for seed in already) + " are already in the library",
            preset=preset.name,
        )

    started = time.perf_counter()
    result = BatchResult()
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

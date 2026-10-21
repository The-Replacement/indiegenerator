"""Preset models and the loader.

Two levels, no inheritance engine (BRIEF section 9): the station file carries
the shared signature and the lane weights; each lane file carries that lane's
musical parameters and its identity. There are no merge keys, no anchors, no
``extends`` and no second configuration language.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, Literal, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from indiegen.errors import PlanError
from indiegen.plan import DirectorMove, FxSend, LaneWeight, Rational, SectionProfile

LANE_NAMES: tuple[str, ...] = ("motorik", "kosmische", "ambient", "dub-electronic", "indie-noise")

PresetModel = TypeVar("PresetModel", bound=BaseModel)


class RangeInt(BaseModel):
    """An inclusive integer range."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    min: int
    max: int


class PadCard(BaseModel):
    """The pad drone's parameters."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["pad"]
    partials: RangeInt
    detune_min_cents: int
    detune_max_cents: int
    lfo_rate: Rational
    lfo_depth_cents: int
    amplitude_millibels: int


class PolyPeriodCard(BaseModel):
    """T1: poly-period loops with distinct periods and one chord."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["poly_period"]
    voice_count: RangeInt
    period_seconds_range: RangeInt
    on_fraction_permille: RangeInt
    attack_seconds_range: RangeInt
    chord_intervals: list[int]
    partial_ratios: list[Rational]


class DroneCard(BaseModel):
    """T11: a spectral drone stack with per-partial drift."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["drone"]
    partial_count: RangeInt
    detune_cents_range: RangeInt
    detune_lfo_rate: Rational
    detune_lfo_depth_cents: int
    amplitude_lfo_rate: Rational
    amplitude_lfo_depth_millibels: int
    ratios: list[Rational]


class PluckCard(BaseModel):
    """T13: the Karplus-Strong guitar, the station's signature timbre."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["pluck"]
    count: RangeInt
    feedback_num_min: int
    feedback_num_max: int
    feedback_den: int
    detune_cents: int
    brightness: Rational
    pluck_position_permille: int
    duration_seconds: RangeInt
    spacing_seconds: RangeInt


TechniqueCard = Annotated[
    PadCard | PolyPeriodCard | DroneCard | PluckCard,
    Field(discriminator="kind"),
]


class DelayCard(BaseModel):
    """The station's dotted-eighth delay send."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    delay_ratio: Rational
    feedback: Rational
    damping: Rational
    send_millibels: int


class ReverbCard(BaseModel):
    """A lane's short Schroeder reverb."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    comb_delays_frames: list[int]
    comb_feedback: Rational
    damping: Rational
    allpass_delays_frames: list[int]
    allpass_feedback: Rational
    stereo_spread_frames: int
    send_millibels: int


class LanePreset(BaseModel):
    """One lane's musical parameters and its identity."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["lane"]
    lane: str
    alias: str
    album: str
    file_token: str
    tempo_range_bpm: list[int]
    meter: list[int]
    scale_midi: list[int]
    fx_sends: list[FxSend]
    techniques: list[TechniqueCard]
    section_count_range: list[int]
    duration_range_seconds: list[int]
    attack_frames: int
    release_frames: int
    reverb: ReverbCard | None = None


class LaneEntry(BaseModel):
    """A lane and its weight inside the station blend."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    lane: str
    weight: int
    parameters: LanePreset


class StationPreset(BaseModel):
    """The shared station signature: what makes three tracks the same station."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["station"]
    station_id: str
    lane_weights: list[LaneWeight]
    palette: list[str]
    motif_bank: list[list[int]]
    title_words: list[str]
    section_profiles: list[SectionProfile]
    strategy_deck: list[DirectorMove]
    fade_in_frames: int
    fade_out_frames: int
    section_crossfade_frames: int
    target_peak_millibels: int
    ceiling_millibels: int
    dither_lsb: int
    track_number: int
    format_version: int
    delay: DelayCard


class Preset(BaseModel):
    """A resolved preset: the station signature plus every lane's parameters."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    name: str
    kind: Literal["station", "lane"]
    station: StationPreset
    lanes: list[LaneEntry]


def resolve_presets_dir(explicit: Path | None = None) -> Path:
    """Find the presets directory: explicit argument, repo root, then cwd."""
    if explicit is not None:
        return explicit
    candidates = (Path(__file__).resolve().parents[2] / "presets", Path.cwd() / "presets")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise PlanError("presets directory not found")


def _read_yaml(path: Path, preset_name: str) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PlanError(f"cannot read preset file {path.name}: {exc}", preset=preset_name) from exc
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PlanError(f"invalid YAML in {path.name}: {exc}", preset=preset_name) from exc


def _load_model[M: BaseModel](path: Path, model: type[M], preset_name: str) -> M:
    raw = _read_yaml(path, preset_name)
    if not isinstance(raw, dict):
        raise PlanError(f"preset file {path.name} must contain a mapping", preset=preset_name)
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        raise PlanError(f"invalid preset {path.name}: {exc}", preset=preset_name) from exc


def _load_lane(directory: Path, lane: str, weight: int, preset_name: str) -> LaneEntry:
    path = directory / f"{lane}.yaml"
    if not path.is_file():
        raise PlanError(f"lane preset file {path.name} not found", preset=preset_name)
    parameters = _load_model(path, LanePreset, preset_name)
    if parameters.lane != lane:
        raise PlanError(f"lane preset {path.name} declares lane {parameters.lane!r}", preset=preset_name)
    return LaneEntry(lane=lane, weight=weight, parameters=parameters)


def load_preset(name: str, *, presets_dir: Path | None = None) -> Preset:
    """Resolve a preset name into one validated :class:`Preset`."""
    directory = resolve_presets_dir(presets_dir)
    station = _load_model(directory / "station.yaml", StationPreset, name)
    if name == "station":
        lanes = [_load_lane(directory, entry.lane, entry.weight, name) for entry in station.lane_weights]
        return Preset(name=name, kind="station", station=station, lanes=lanes)
    if name not in LANE_NAMES:
        raise PlanError("unknown preset", preset=name)
    return Preset(name=name, kind="lane", station=station, lanes=[_load_lane(directory, name, 0, name)])


def canonical_preset_json(preset: Preset) -> bytes:
    """The canonical bytes of a preset, used to seed the compose PRNG."""
    return json.dumps(
        preset.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")

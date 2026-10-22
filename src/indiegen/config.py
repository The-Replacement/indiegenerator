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
from indiegen.plan import BusGain, FxSend, LaneWeight, Rational, SectionProfile

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
    min_density: int


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
    min_density: int


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
    min_density: int


class FrippertronicsCard(BaseModel):
    """T3: the Frippertronics send of the kosmische and ambient lanes."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["frippertronics"]
    delay_seconds: RangeInt
    feedback_permille: RangeInt
    cutoff_start_hz: int
    cutoff_step_hz: int
    cutoff_floor_hz: int
    saturation_permille: int
    wow_depth_permille: int
    wow_rate_hz: RangeInt
    send_millibels: int
    min_density: int


class DubChainCard(BaseModel):
    """T10: the dub chain, and the sidechain to the kick."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["dub_chain"]
    bit_depth: int
    bandpass_hz: int
    bandpass_q_num: int
    bandpass_q_den: int
    drift_depth_hz: int
    send_millibels: int
    sidechain_depth_millibels: int
    sidechain_release_frames: int
    min_density: int


class PluckCard(BaseModel):
    """T13: the Karplus-Strong guitar, the station's signature timbre."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["pluck"]
    count: RangeInt
    min_density: int
    feedback_num_min: int
    feedback_num_max: int
    feedback_den: int
    detune_cents: int
    brightness: Rational
    pluck_position_permille: int
    duration_seconds: RangeInt
    spacing_seconds: RangeInt


class PatternCard(BaseModel):
    """How one drum voice's hits are laid out on the grid.

    The euclid pattern is the pulse count and the step count, rotated. The
    condition is what lets a voice in: always, every other step, three in
    four, the first step of a phrase, or only in a fill.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    steps_per_bar: int
    euclid_k: int
    euclid_n: int
    rotation: int
    condition: Literal["always", "one_in_two", "three_in_four", "first_of_phrase", "fill_only"]
    condition_period: int
    min_density: int
    ghost_permille: int
    velocity_millibels: int


class KickCard(BaseModel):
    """T6: the kick drum."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["kick"]
    pattern: PatternCard
    body_hz: int
    drop_hz: int
    drop_frames: int
    decay_frames: int


class SnareCard(BaseModel):
    """T6: the snare drum."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["snare"]
    pattern: PatternCard
    body_hz: int
    body_decay_frames: int
    noise_decay_frames: int


class HatCard(BaseModel):
    """T6: the closed hat."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["hat"]
    pattern: PatternCard
    cutoff_hz: int
    decay_frames: int


class BassCard(BaseModel):
    """T6: the bass line, an eighth-note root with octave jumps."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["bass"]
    pattern: PatternCard
    cutoff_hz: int
    decay_frames: int
    octave_jump_permille: int
    fifth_permille: int


class PinkCard(BaseModel):
    """T7: the 1/f control signals of the lane."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["pink"]
    velocity_depth_millibels: int
    micro_timing_frames: int
    pan_drift_permille: int


class DejaVuCard(BaseModel):
    """T5: the deja-vu sequencer, over the Karplus-Strong stabs."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["deja_vu"]
    step_beats: int
    buffer_size: int
    min_density: int
    replay_min_permille: int
    replay_max_permille: int
    bias: int
    spread: int
    note_frames: int
    feedback_num: int
    feedback_den: int
    brightness: Rational
    pluck_position_permille: int
    detune_cents: int


TechniqueCard = Annotated[
    PadCard
    | PolyPeriodCard
    | DroneCard
    | PluckCard
    | KickCard
    | SnareCard
    | HatCard
    | BassCard
    | PinkCard
    | DejaVuCard
    | FrippertronicsCard
    | DubChainCard,
    Field(discriminator="kind"),
]


class StrategyCard(BaseModel):
    """One transformation in the Director's deck.

    The deck is a pool, not a list of moves: the arranger draws from it,
    and the draw is the only randomness the Director ever has.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    strategy: str
    detail: str
    parameter_min: int
    parameter_max: int
    applies_to: list[str]
    crossfade_frames: int = Field(ge=0)
    span_bars: int = Field(ge=0)


class DirectorCard(BaseModel):
    """How often the Director fires, and what it can do."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    bars_min: int = Field(ge=1)
    bars_max: int = Field(ge=1)
    seconds_min: int = Field(ge=1)
    seconds_max: int = Field(ge=1)
    strategies: list[StrategyCard]


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
    mode_pool: list[str]
    pulse: Literal["bars", "seconds"]
    timbre: dict[str, int]
    fx_sends: list[FxSend]
    techniques: list[TechniqueCard]
    section_count_range: list[int]
    duration_range_seconds: list[int]
    bus_gains: list[BusGain] = []
    attack_frames: int | None = None
    release_frames: int | None = None
    reverb: ReverbCard | None = None


class LaneEntry(BaseModel):
    """A lane and its weight inside the station blend."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    lane: str
    weight: int
    parameters: LanePreset


class FormCard(BaseModel):
    """One of the station's track forms, and how many of them there are.

    BRIEF 15: "A 20-track batch is not 20 tracks: ~60% full tracks (4-10
    min), ~25% longform (10-15 min), ~15% interludes (45-120 s)". The
    forms are the station's release policy, so they are the same for every
    lane.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    form: Literal["full", "longform", "interlude"]
    weight: int = Field(ge=0)
    duration_range_seconds: list[int]


class StationPreset(BaseModel):
    """The shared station signature: what makes three tracks the same station."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["station"]
    lane_weights: list[LaneWeight]
    forms: list[FormCard]
    palette: list[str]
    motif_bank: list[list[int]]
    motif_rhythm: list[int]
    title_words: list[str]
    section_graph: list[SectionProfile]
    director: DirectorCard
    fade_in_frames: int
    fade_out_frames: int
    section_crossfade_frames: int
    target_lufs_millibels: int
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

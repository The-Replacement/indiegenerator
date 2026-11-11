"""Preset models and the loader.

Two levels, no inheritance engine (BRIEF section 9): the station file carries
the shared signature and the lane weights; each lane file carries that lane's
musical parameters and its identity. There are no merge keys, no anchors, no
``extends`` and no second configuration language.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal, TypeVar

import yaml
from pydantic import BaseModel, Field, ValidationError

from indiegen.errors import PlanError
from indiegen.plan import (
    BusGain,
    DuckSpec,
    FrozenModel,
    FxSend,
    LaneWeight,
    Rational,
    SectionProfile,
)

LANE_NAMES: tuple[str, ...] = ("motorik", "kosmische", "ambient", "dub-electronic", "indie-noise")

PresetModel = TypeVar("PresetModel", bound=FrozenModel)


class RangeInt(FrozenModel):
    """An inclusive integer range."""

    min: int
    max: int


class PadCard(FrozenModel):
    """The pad drone's parameters."""

    kind: Literal["pad"]
    partials: RangeInt
    detune_min_cents: int
    detune_max_cents: int
    lfo_rate: Rational
    lfo_depth_cents: int
    amplitude_millibels: int
    min_density: int
    envelope_segments: int = Field(default=0, ge=0, le=4)


class LeadCard(FrozenModel):
    """The lane's sustained lead: BRIEF 5's two-oscillator detuned voice.

    It plays from ``entry_section`` on, which is what "enters at section 3+"
    means and what makes the section's instrumentation differ for the first
    time in a lane that used to hold one colour for the whole track.
    """

    kind: Literal["lead"]
    partials: RangeInt
    detune_min_cents: int
    detune_max_cents: int
    lfo_rate: Rational
    lfo_depth_cents: int
    amplitude_millibels: int
    min_density: int
    entry_section: int = Field(default=3, ge=1)
    pan_permille: int = 0
    attack_seconds: int = Field(default=2, ge=0)
    release_seconds: int = Field(default=3, ge=0)


class PolyPeriodCard(FrozenModel):
    """T1: poly-period loops with distinct periods and one chord."""

    kind: Literal["poly_period"]
    voice_count: RangeInt
    period_seconds_range: RangeInt
    on_fraction_permille: RangeInt
    attack_seconds_range: RangeInt
    chord_intervals: list[int]
    partial_ratios: list[Rational]
    min_density: int


class DroneCard(FrozenModel):
    """T11: a spectral drone stack with per-partial drift."""

    kind: Literal["drone"]
    partial_count: RangeInt
    detune_cents_range: RangeInt
    detune_lfo_rate: Rational
    detune_lfo_depth_cents: int
    amplitude_lfo_rate: Rational
    amplitude_lfo_depth_millibels: int
    ratios: list[Rational]
    min_density: int


class FrippertronicsCard(FrozenModel):
    """T3: the Frippertronics send of the kosmische and ambient lanes."""

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


class DubChainCard(FrozenModel):
    """T10: the dub chain, and the sidechain to the kick."""

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


class PluckCard(FrozenModel):
    """T13: the Karplus-Strong guitar, the station's signature timbre."""

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


class PatternCard(FrozenModel):
    """How one drum voice's hits are laid out on the grid.

    The euclid pattern is the pulse count and the step count, rotated. The
    condition is what lets a voice in: always, every other step, three in
    four, the first step of a phrase, or only in a fill.
    """

    steps_per_bar: int
    euclid_k: int
    euclid_n: int
    rotation: int
    condition: Literal["always", "one_in_two", "three_in_four", "first_of_phrase", "fill_only"]
    condition_period: int
    min_density: int
    ghost_permille: int
    velocity_millibels: int
    # How far the pulse count follows the section's density, in permille of
    # the fall from a density of 100. 0 is a strict no-op: the pattern is
    # the same in every section, which is what every voice but the
    # indie-noise wall wants. At 1000 a voice plays euclid_k pulses in the
    # densest section and proportionally fewer in the sparser ones, so its
    # density is a property of the section and not only a threshold.
    density_scale_permille: int = Field(default=0, ge=0, le=1000)


class KickCard(FrozenModel):
    """T6: the kick drum."""

    kind: Literal["kick"]
    pattern: PatternCard
    body_hz: int
    drop_hz: int
    drop_frames: int
    decay_frames: int


class SnareCard(FrozenModel):
    """T6: the snare drum."""

    kind: Literal["snare"]
    pattern: PatternCard
    body_hz: int
    body_decay_frames: int
    noise_decay_frames: int


class HatCard(FrozenModel):
    """T6: the closed hat.

    ``cutoff_hz`` is the lower corner (a closed hat is noise above it) and
    ``lowpass_hz`` is the optional upper corner that keeps a dense hat wall
    out of BRIEF 6's >14 kHz codec region. 0 means no upper corner.
    """

    kind: Literal["hat"]
    pattern: PatternCard
    cutoff_hz: int
    decay_frames: int
    lowpass_hz: int = Field(default=0, ge=0, le=24000)


class BassCard(FrozenModel):
    """T6: the bass line, an eighth-note root with octave jumps."""

    kind: Literal["bass"]
    pattern: PatternCard
    cutoff_hz: int
    decay_frames: int
    octave_jump_permille: int
    fifth_permille: int = Field(ge=0, le=1000)
    midi_offset_semitones: int = Field(default=-12, ge=-12, le=12)


class PinkCard(FrozenModel):
    """T7: the 1/f control signals of the lane."""

    kind: Literal["pink"]
    velocity_depth_millibels: int
    micro_timing_frames: int
    pan_drift_permille: int


class DejaVuCard(FrozenModel):
    """T5: the deja-vu sequencer, over the Karplus-Strong stabs."""

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
    | DubChainCard
    | LeadCard,
    Field(discriminator="kind"),
]


class StrategyCard(FrozenModel):
    """One transformation in the Director's deck.

    The deck is a pool, not a list of moves: the arranger draws from it,
    and the draw is the only randomness the Director ever has.
    """

    strategy: str
    detail: str
    parameter_min: int
    parameter_max: int
    applies_to: list[str]
    crossfade_frames: int = Field(ge=0)
    span_bars: int = Field(ge=0)


class DirectorCard(FrozenModel):
    """How often the Director fires, and what it can do."""

    bars_min: int = Field(ge=1)
    bars_max: int = Field(ge=1)
    seconds_min: int = Field(ge=1)
    seconds_max: int = Field(ge=1)
    strategies: list[StrategyCard]


class DelayCard(FrozenModel):
    """The station's dotted-eighth delay send."""

    delay_ratio: Rational
    feedback: Rational
    damping: Rational
    send_millibels: int


class ReverbCard(FrozenModel):
    """A lane's short Schroeder reverb."""

    comb_delays_frames: list[int]
    comb_feedback: Rational
    damping: Rational
    allpass_delays_frames: list[int]
    allpass_feedback: Rational
    stereo_spread_frames: int
    send_millibels: int


class LanePreset(FrozenModel):
    """One lane's musical parameters and its identity."""

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
    tension_admission_enabled: bool = False
    fx_sends: list[FxSend]
    techniques: list[TechniqueCard]
    section_count_range: list[int]
    duration_range_seconds: list[int]
    bus_gains: list[BusGain] = []
    attack_frames: int | None = None
    release_frames: int | None = None
    swing_permille: int = Field(default=0, ge=0, le=1000)
    melodic_jitter_frames: int = Field(default=0, ge=0, le=200)
    drive_permille: int = Field(default=0, ge=0, le=1000)
    snap_permille: int = Field(default=0, ge=0, le=1000)
    duck: DuckSpec | None = None
    reverb: ReverbCard | None = None


class LaneEntry(FrozenModel):
    """A lane and its weight inside the station blend."""

    lane: str
    weight: int
    parameters: LanePreset


class FormCard(FrozenModel):
    """One of the station's track forms, and how many of them there are.

    BRIEF 15: "A 20-track batch is not 20 tracks: ~60% full tracks (4-10
    min), ~25% longform (10-15 min), ~15% interludes (45-120 s)". The
    forms are the station's release policy, so they are the same for every
    lane.
    """

    form: Literal["full", "longform", "interlude"]
    weight: int = Field(ge=0)
    duration_range_seconds: list[int]


class StationPreset(FrozenModel):
    """The shared station signature: what makes three tracks the same station."""

    kind: Literal["station"]
    lane_weights: list[LaneWeight]
    forms: list[FormCard]
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
    tuning_system: int = Field(default=0, ge=0, le=1)
    chord_segments_per_section: int = Field(default=1, ge=1, le=8)
    chromatic_budget_permille: int = Field(default=0, ge=0, le=1000)
    chord_tone_intervals: list[int] = []
    # c12: opt-in constraint-programming harmonic progression.
    harmony_cp_enabled: bool = False
    harmony_voice_leading_limit: int = Field(default=7, ge=1, le=24)
    # c13: opt-in orbifold-geodesic voice leading (wrapped mod-12 quotient).
    # Code-only, never declared in preset YAML (c12 precedent).
    geodesic_voice_leading: bool = False
    planar_offset_semitones: int = Field(default=0, ge=-12, le=12)
    ornament_permille: int = Field(default=0, ge=0, le=200)
    grace_offset_frames: int = Field(default=0, ge=0, le=500)
    double_copies: int = Field(default=0, ge=0, le=2)
    double_offset_frames: int = Field(default=0, ge=0, le=50)
    dither_lsb: int
    track_number: int
    format_version: int
    delay: DelayCard


class Preset(FrozenModel):
    """A resolved preset: the station signature plus every lane's parameters."""

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

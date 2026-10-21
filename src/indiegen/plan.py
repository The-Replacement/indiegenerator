"""The frozen Plan: integer-only data that fully determines a render.

Two promises are made here, and they are different promises (BRIEF section 8):

* ``plan_sha256`` is bit-identical on every machine. It hashes the canonical
  JSON of this model, and every numeric leaf is an integer, so the byte string
  cannot drift.
* ``pcm_sha256`` is bit-identical on *this* machine with the pinned
  dependencies and single-threaded BLAS. Float summation is not associative, so
  cross-machine PCM identity is not promised and is not chased.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from indiegen.errors import PlanError

SAMPLE_RATE: int = 44100
CHANNELS: int = 2


def reject_non_integer_leaves(value: Any, path: str = "plan") -> None:
    """Raise :class:`PlanError` if any numeric leaf is not a plain ``int``.

    Strings are legal leaves (names, ids, title words). ``bool`` is rejected
    even though it is an ``int`` subclass: the Plan declares no boolean field,
    and ``strict=True`` cannot catch a bool that lands in a bool-typed field.
    """
    if isinstance(value, bool) or isinstance(value, float) or isinstance(value, Decimal):
        raise PlanError(f"plan contains a non-integer leaf at {path}: {value!r}")
    if isinstance(value, dict):
        for key, item in value.items():
            reject_non_integer_leaves(item, f"{path}.{key}")
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            reject_non_integer_leaves(item, f"{path}[{index}]")


class Rational(BaseModel):
    """An exact integer ratio, e.g. an LFO rate of 1/8 Hz."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    numerator: int = Field(gt=0)
    denominator: int = Field(gt=0)


class LaneWeight(BaseModel):
    """One lane of the station blend and its relative weight."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    lane: str
    weight: int = Field(ge=0)


class FxSend(BaseModel):
    """A send from a bus into an effect, with the effect's integer parameters."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    name: str
    send_millibels: int
    cutoff_hz: int = Field(gt=0)
    q_num: int = Field(gt=0)
    q_den: int = Field(gt=0)


class SectionProfile(BaseModel):
    """One node of the station's section graph.

    A node declares what it is (the function), where it can go (the
    successors), how loud and how dense it is (the tension curve), how long
    it lasts (the bars) and, when it reprises an earlier section, which one
    and under which transform.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    function: str
    next: list[str]
    density: int = Field(ge=0, le=100)
    level_millibels: int
    bars: int = Field(gt=0)
    reprise_of: str
    transform: str
    texture: str


class DirectorMove(BaseModel):
    """A strategy from the deck, and - in the log - a move the Director made."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    sample: int = Field(ge=0)
    strategy: str
    detail: str
    parameter: int
    crossfade_frames: int = Field(ge=0)
    applies_to: list[str]


class Partial(BaseModel):
    """One partial of an additive voice, with its exact ratio."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    ratio: Rational
    amplitude_millibels: int
    detune_cents: int


class DetuneLfo(BaseModel):
    """The slow drift of a partial's detune, in cents."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    rate: Rational
    depth_cents: int = Field(ge=0)


class AmplitudeLfo(BaseModel):
    """The slow drift of a partial's amplitude, in millibels."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    rate: Rational
    depth_millibels: int = Field(ge=0)


class DriftingPartial(Partial):
    """A partial with its own independent drift on detune and on amplitude."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    detune_lfo: DetuneLfo
    amplitude_lfo: AmplitudeLfo


class EventBase(BaseModel):
    """What every scheduled event carries, whatever instrument plays it."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    instrument: str
    start_frame: int = Field(ge=0)
    duration_frames: int = Field(gt=0)
    midi: int
    pan_permille: int
    amplitude_millibels: int
    attack_frames: int = Field(ge=0)
    release_frames: int = Field(ge=0)


class PadEvent(EventBase):
    """A sustained additive pad. The S0 instrument, unchanged."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["pad"]
    partials: int = Field(ge=1)
    partial_detune_cents: list[int]
    lfo_rate: Rational
    lfo_depth_cents: int


class PolyPeriodVoice(BaseModel):
    """One voice of a poly-period loop: its own period, on-window and pitch."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    period_frames: int = Field(gt=0)
    on_frames: int = Field(gt=0)
    phase_frames: int = Field(ge=0)
    midi: int


class PolyPeriodEvent(EventBase):
    """A poly-period loop: several voices, each on its own distinct period."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["poly_period"]
    voices: list[PolyPeriodVoice]
    partials: list[Partial]


class DroneEvent(EventBase):
    """A spectral drone stack: near-unison partials drifting against each other."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["drone"]
    partials: list[DriftingPartial]
    noise_seed: int


class PluckEvent(EventBase):
    """A plucked string. The station's signature timbre."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["pluck"]
    feedback: Rational
    brightness: Rational
    pluck_position_permille: int
    detune_cents: int
    excitation_seed: int


class HitBase(BaseModel):
    """What every hit carries: where it lands and how hard it is."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    frame: int = Field(ge=0)
    velocity_millibels: int


class DrumHit(HitBase):
    """One hit of a drum pattern: where it lands and how hard it is."""


class BassHit(HitBase):
    """One hit of a bass line: where it lands, how hard it is and its pitch."""

    midi: int


class RhythmEvent(EventBase):
    """The 1/f control signals every drum pattern carries.

    The hits themselves are resolved at compose time. The euclid pattern, its
    rotation and the conditional triggers are decisions about the
    arrangement, and the renderer only plays what the plan says.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    noise_seed: int
    velocity_depth_millibels: int
    micro_timing_frames: int
    pan_drift_permille: int


class KickEvent(RhythmEvent):
    """A kick drum: a round body with a fast pitch drop and a soft transient."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["kick"]
    hits: list[DrumHit]
    body_hz: int
    drop_hz: int
    drop_frames: int
    decay_frames: int


class SnareEvent(RhythmEvent):
    """A snare drum: a body tone and a noise burst, decaying apart."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["snare"]
    hits: list[DrumHit]
    body_hz: int
    body_decay_frames: int
    noise_decay_frames: int


class HatEvent(RhythmEvent):
    """A closed hat: a short burst of high-passed noise."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["hat"]
    hits: list[DrumHit]
    cutoff_hz: int
    decay_frames: int


class BassEvent(RhythmEvent):
    """A bass line: a filtered saw on the lane's root, with octave jumps."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    kind: Literal["bass"]
    hits: list[BassHit]
    cutoff_hz: int
    decay_frames: int


Event = Annotated[
    PadEvent | PolyPeriodEvent | DroneEvent | PluckEvent | KickEvent | SnareEvent | HatEvent | BassEvent,
    Field(discriminator="kind"),
]


class DelaySend(BaseModel):
    """A delay send: the station's dotted-eighth delay lives here."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    name: str
    delay_frames: int = Field(gt=0)
    feedback: Rational
    damping: Rational
    send_millibels: int


class ReverbSpec(BaseModel):
    """A short Schroeder reverb: parallel combs into series allpasses."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    comb_delays_frames: list[int]
    comb_feedback: Rational
    damping: Rational
    allpass_delays_frames: list[int]
    allpass_feedback: Rational
    stereo_spread_frames: int = Field(ge=0)
    send_millibels: int


class SectionPlan(BaseModel):
    """One section of the arrangement.

    The section carries the five dimensions BRIEF 6 asks a section to differ
    in: the instrumentation (which event kinds play in it), the harmonic
    center (the mode and the root), the rhythmic pattern, the density and
    the texture. The centroid is the timbre the composer predicted for the
    section, and gate 6 compares the delivered audio with it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    index: int
    function: str
    start_frame: int
    end_frame: int
    bars: int
    density: int
    level_millibels: int
    techniques: list[str]
    instrumentation: list[str]
    mode: str
    root_midi: int
    texture: str
    reprise_of: int
    transform: str
    centroid_hz: int = Field(gt=0)


class MotifNote(BaseModel):
    """One note of the motif cell: its pitch and how long it lasts."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    midi: int
    duration_frames: int = Field(gt=0)


class MotifCell(BaseModel):
    """The motif: three to seven notes, one cell."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    notes: list[MotifNote]


class MotifAppearance(BaseModel):
    """One appearance of the motif, and the transform it wears.

    The appearance is what gate 13 counts: the motif has to come back at
    least three times in a transformed form.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    section_index: int = Field(ge=0)
    transform: str
    parameter: int
    start_frame: int = Field(ge=0)
    notes: list[int]
    durations: list[int]


class FrippertronicsSpec(BaseModel):
    """T3: a long feedback delay whose passes darken and die.

    The number of passes a sample has made is exact, not an approximation:
    the render path keeps a counter beside the audio line, so the cutoff
    really does fall by the declared step on every pass.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    delay_frames: int = Field(gt=0)
    feedback_permille: int = Field(ge=0, le=1000)
    cutoff_start_hz: int = Field(gt=0)
    cutoff_step_hz: int = Field(ge=0)
    cutoff_floor_hz: int = Field(gt=0)
    saturation_permille: int = Field(ge=0, le=1000)
    wow_depth_permille: int = Field(ge=0)
    wow_rate: Rational
    send_millibels: int


class DubChainSpec(BaseModel):
    """T10: the dub chain, from the bit reduction to the sidechain."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    bit_depth: int = Field(ge=1, le=16)
    bandpass_hz: int = Field(gt=0)
    bandpass_q_num: int = Field(gt=0)
    bandpass_q_den: int = Field(gt=0)
    drift_depth_hz: int = Field(ge=0)
    drift_seed: int
    send_millibels: int
    sidechain_depth_millibels: int
    sidechain_release_frames: int = Field(gt=0)


class Plan(BaseModel):
    """Everything a render needs, and nothing else.

    There is no date, no clock and no float in here. The audio is a pure
    function of this object.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    version: int
    format_version: int
    preset: str
    seed: int
    lane: str
    alias: str
    album: str
    file_token: str
    title: str
    sample_rate: int
    channels: int
    duration_frames: int
    duration_range_frames: list[int]
    tempo_bpm: int
    frames_per_beat: int
    meter_numerator: int
    meter_denominator: int
    pulse: Literal["bars", "seconds"]
    scale_midi: list[int]
    palette: list[str]
    fx_sends: list[FxSend]
    techniques: list[str]
    strategy_deck: list[DirectorMove]
    section_count_range: list[int]
    section_count: int
    sections: list[SectionPlan]
    motif: MotifCell
    motif_appearances: list[MotifAppearance]
    deja_vu_replay_permille: list[int]
    title_words: list[str]
    lane_weights: list[LaneWeight]
    dither_seed: int
    dither_lsb: int
    master_gain_millibels: int
    ceiling_millibels: int
    fade_in_frames: int
    fade_out_frames: int
    section_crossfade_frames: int
    track_number: int
    delay_sends: list[DelaySend]
    reverb: ReverbSpec | None
    frippertronics: FrippertronicsSpec | None
    dub_chain: DubChainSpec | None
    events: list[Event]
    director_log: list[DirectorMove]

    @model_validator(mode="after")
    def _enforce_integer_leaves(self) -> Self:
        reject_non_integer_leaves(self.model_dump(), "plan")
        return self


def canonical_json(plan: Plan) -> bytes:
    """The one serialisation of the Plan that may enter a hash."""
    return json.dumps(
        plan.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def plan_sha256(plan: Plan) -> str:
    """SHA-256 of the canonical Plan JSON. A function, never a Plan field."""
    return hashlib.sha256(canonical_json(plan)).hexdigest()

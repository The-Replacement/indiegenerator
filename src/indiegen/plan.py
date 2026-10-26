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
INT16_MIN: int = -32768
INT16_MAX: int = 32767
# The station's own ceiling: the longest form is fifteen minutes. A plan is
# data that can arrive from a file, and every buffer in the render is sized by
# `duration_frames`, so an unbounded duration is an unbounded allocation.
MAX_DURATION_FRAMES: int = 15 * 60 * SAMPLE_RATE
MAX_EVENTS: int = 50_000
MAX_HITS: int = 500_000

_NON_INTEGER_LEAVES: tuple[type, ...] = (bool, float, Decimal)


class FrozenModel(BaseModel):
    """The one configuration of every data model: frozen, strict, closed.

    Inherited rather than repeated: a model that forgets ``strict=True`` would
    accept a float from a JSON sidecar and break the Plan's integer promise.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


def reject_non_integer_leaves(value: Any, path: str = "plan") -> None:
    """Raise :class:`PlanError` if any numeric leaf is not a plain ``int``.

    Strings are legal leaves (names, ids, title words). ``bool`` is rejected
    even though it is an ``int`` subclass: the Plan declares no boolean field,
    and ``strict=True`` cannot catch a bool that lands in a bool-typed field.

    One ``isinstance`` call over a tuple, not three over the same value: this
    walk is the largest single cost of validating a plan, and a triple test is
    measured at twice the price of a single one.
    """
    if isinstance(value, _NON_INTEGER_LEAVES):
        raise PlanError(f"plan contains a non-integer leaf at {path}: {value!r}")
    if isinstance(value, dict):
        for key, item in value.items():
            reject_non_integer_leaves(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            reject_non_integer_leaves(item, f"{path}[{index}]")


class Rational(FrozenModel):
    """An exact integer ratio, e.g. an LFO rate of 1/8 Hz."""

    numerator: int = Field(gt=0)
    denominator: int = Field(gt=0)


class LaneWeight(FrozenModel):
    """One lane of the station blend and its relative weight."""

    lane: str
    weight: int = Field(ge=0)


class FxSend(FrozenModel):
    """A send from a bus into an effect, with the effect's integer parameters."""

    name: str
    send_millibels: int
    cutoff_hz: int = Field(gt=0)
    q_num: int = Field(gt=0)
    q_den: int = Field(gt=0)


class SectionProfile(FrozenModel):
    """One node of the station's section graph.

    A node declares what it is (the function), where it can go (the
    successors), how loud and how dense it is (the tension curve), how long
    it lasts (the bars) and, when it reprises an earlier section, which one
    and under which transform.
    """

    function: str
    next: list[str] = Field(max_length=16)
    density: int = Field(ge=0, le=100)
    level_millibels: int
    bars: int = Field(gt=0)
    reprise_of: str
    transform: str
    texture: str


class BusGain(FrozenModel):
    """One instrument's trim on the mix bus.

    The key is the event's kind, so the motif's plucks are trimmed with the
    guitar and not separately. The trim is in millibels, like every other
    level in the Plan.
    """

    kind: str
    gain_millibels: int


class DrumBusComp(FrozenModel):
    """A compressor on the drum bus: threshold, ratio, attack, release, makeup, mix."""

    threshold_millibels: int = Field(default=0, ge=-60000, le=0)
    ratio_permille: int = Field(default=2000, ge=2000, le=10000)
    attack_frames: int = Field(default=10, ge=10, le=500)
    release_frames: int = Field(default=1000, ge=1000, le=100000)
    makeup_millibels: int = Field(default=0, ge=0, le=60000)
    mix_permille: int = Field(default=0, ge=0, le=1000)


class DuckSpec(FrozenModel):
    """c31: the masking duck - the 200-500 Hz band, ducked by the bass.

    BRIEF 6's mix charge: the pad and the bass share a band, and the bass
    should win it while it is playing. The envelope is keyed on the bass HIT
    FRAMES, not on the bass audio, so it is identical block-wise and
    whole-track (the sidechain rule) and costs one exponential per second.

    ``None`` on the Plan means the lane does not duck at all.
    """

    depth_millibels: int = Field(ge=-120000, le=0)
    release_frames: int = Field(gt=0)


class ArrangementMute(FrozenModel):
    """A per-section per-instrument mute (binary: 0 or 1000)."""

    kind: str
    section_index: int = Field(ge=0)
    mute: int = Field(ge=0, le=1000)

    @model_validator(mode="after")
    def _poles_only(self) -> ArrangementMute:
        if self.mute not in (0, 1000):
            raise PlanError(f"arrangement_mutes mute must be 0 or 1000, got {self.mute}")
        return self


class DirectorMove(FrozenModel):
    """A strategy from the deck, and - in the log - a move the Director made."""

    sample: int = Field(ge=0)
    strategy: str
    detail: str
    parameter: int
    crossfade_frames: int = Field(ge=0)
    applies_to: list[str] = Field(max_length=16)


class Partial(FrozenModel):
    """One partial of an additive voice, with its exact ratio."""

    ratio: Rational
    amplitude_millibels: int
    detune_cents: int


class DetuneLfo(FrozenModel):
    """The slow drift of a partial's detune, in cents."""

    rate: Rational
    depth_cents: int = Field(ge=0)


class AmplitudeLfo(FrozenModel):
    """The slow drift of a partial's amplitude, in millibels."""

    rate: Rational
    depth_millibels: int = Field(ge=0)


class DriftingPartial(Partial):
    """A partial with its own independent drift on detune and on amplitude."""

    detune_lfo: DetuneLfo
    amplitude_lfo: AmplitudeLfo


class EventBase(FrozenModel):
    """What every scheduled event carries, whatever instrument plays it."""

    instrument: str
    start_frame: int = Field(ge=0)
    duration_frames: int = Field(gt=0)
    midi: int
    pan_permille: int
    amplitude_millibels: int
    attack_frames: int = Field(ge=0)
    release_frames: int = Field(ge=0)
    envelope_curve: int = Field(default=0, ge=0, le=1)
    drive_permille: int = Field(default=0, ge=0, le=1000)


class PadEnvelopeSegment(FrozenModel):
    """One amplitude-permutation segment of a pad event.

    ``delta_frames`` is the segment's length measured from the previous
    boundary (the first from the event start); the last segment runs to the
    event's end. The permutation reassigns the partial weights: partial ``i``
    sounds with the base weight of partial ``permutation[i]``.
    """

    delta_frames: int = Field(ge=1)
    permutation: list[int] = Field(min_length=2, max_length=16)


class PadEvent(EventBase):
    """A sustained additive pad. The S0 instrument, unchanged."""

    kind: Literal["pad"]
    partials: list[Partial] = Field(min_length=1, max_length=9)
    lfo_rate: Rational
    lfo_depth_cents: int
    envelope_segments: list[PadEnvelopeSegment] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def _permutations_match_partials(self) -> Self:
        """Each segment's permutation must be a permutation of the partials."""
        size = len(self.partials)
        for segment in self.envelope_segments:
            if sorted(segment.permutation) != list(range(size)):
                raise PlanError(
                    f"pad envelope segment permutation {segment.permutation} "
                    f"is not a permutation of {size} partial indices"
                )
        return self


class PolyPeriodVoice(FrozenModel):
    """One voice of a poly-period loop: its own period, on-window and pitch."""

    period_frames: int = Field(gt=0)
    on_frames: int = Field(gt=0)
    phase_frames: int = Field(ge=0)
    midi: int


class PolyPeriodEvent(EventBase):
    """A poly-period loop: several voices, each on its own distinct period."""

    kind: Literal["poly_period"]
    voices: list[PolyPeriodVoice] = Field(max_length=16)
    partials: list[Partial] = Field(max_length=16)


class DroneEvent(EventBase):
    """A spectral drone stack: near-unison partials drifting against each other."""

    kind: Literal["drone"]
    partials: list[DriftingPartial] = Field(max_length=16)
    noise_seed: int


class PluckEvent(EventBase):
    """A plucked string. The station's signature timbre."""

    kind: Literal["pluck"]
    feedback: Rational
    brightness: Rational
    pluck_position_permille: int
    detune_cents: int
    excitation_seed: int


class HitBase(FrozenModel):
    """What every hit carries: where it lands and how hard it is.

    ``frame`` is where the hit PLAYS: the plan carries the micro-timing
    drift, so the renderer places the voice at this frame and never adds an
    offset of its own (c33). ``drift_frames`` is how far the performance
    pulled the hit off the grid, and the grid frame is ``frame -
    drift_frames``. The voice's noise is keyed on the grid frame, because a
    drummer's drift is a timing decision and must not re-draw the sound of
    the drum. A hit that sits on the grid carries 0.
    """

    frame: int = Field(ge=0)
    velocity_millibels: int
    drift_frames: int = 0

    def grid_frame(self) -> int:
        """The frame the arrangement wrote, before the micro-timing drift."""
        return self.frame - self.drift_frames


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

    noise_seed: int
    velocity_depth_millibels: int
    micro_timing_frames: int
    pan_drift_permille: int
    snap_permille: int = Field(default=0, ge=0, le=1000)


class KickEvent(RhythmEvent):
    """A kick drum: a round body with a fast pitch drop and a soft transient."""

    kind: Literal["kick"]
    hits: list[DrumHit] = Field(max_length=MAX_HITS)
    body_hz: int
    drop_hz: int
    drop_frames: int
    decay_frames: int


class SnareEvent(RhythmEvent):
    """A snare drum: a body tone and a noise burst, decaying apart."""

    kind: Literal["snare"]
    hits: list[DrumHit] = Field(max_length=MAX_HITS)
    body_hz: int
    body_decay_frames: int
    noise_decay_frames: int


class HatEvent(RhythmEvent):
    """A closed hat: a short burst of band-passed noise.

    ``cutoff_hz`` is the LOWER corner - a closed hat is noise above it.
    ``lowpass_hz`` is the optional upper corner, and 0 means there is none.
    """

    kind: Literal["hat"]
    hits: list[DrumHit] = Field(max_length=MAX_HITS)
    cutoff_hz: int
    decay_frames: int
    lowpass_hz: int = Field(default=0, ge=0, le=24000)


class BassEvent(RhythmEvent):
    """A bass line: a filtered saw on the lane's root, with octave jumps."""

    kind: Literal["bass"]
    hits: list[BassHit] = Field(max_length=MAX_HITS)
    cutoff_hz: int
    decay_frames: int


class LeadEvent(EventBase):
    """A sustained lead: the pad's additive synth, entering where the lane says.

    BRIEF 5 gives kosmische a "two-oscillator detuned lead entering at section
    3+", and there was no lead voice in the composer at all: the lane ran
    drone plus arpeggios for eleven minutes with no third act (measured, issue
    #36). The lead is the pad's instrument with a different palette - a detuned
    pair, a fifth and an add9 - and its own kind so the section's
    instrumentation records that it entered, which is the dimension that lane
    never moved.
    """

    kind: Literal["lead"]
    partials: list[Partial] = Field(min_length=1, max_length=9)
    lfo_rate: Rational
    lfo_depth_cents: int
    envelope_segments: list[PadEnvelopeSegment] = Field(default_factory=list, max_length=16)


SustainedEvent = PadEvent | LeadEvent
"""The voices the additive synth renders: the pad and the lead on top of it."""


Event = Annotated[
    PadEvent | PolyPeriodEvent | DroneEvent | PluckEvent | KickEvent | SnareEvent | HatEvent | BassEvent | LeadEvent,
    Field(discriminator="kind"),
]


class DelaySend(FrozenModel):
    """A delay send: the station's dotted-eighth delay lives here."""

    name: str
    delay_frames: int = Field(gt=0)
    feedback: Rational
    damping: Rational
    send_millibels: int


class ReverbSpec(FrozenModel):
    """A short Schroeder reverb: parallel combs into series allpasses."""

    comb_delays_frames: list[int] = Field(max_length=16)
    comb_feedback: Rational
    damping: Rational
    allpass_delays_frames: list[int] = Field(max_length=8)
    allpass_feedback: Rational
    stereo_spread_frames: int = Field(ge=0)
    send_millibels: int


class SectionPlan(FrozenModel):
    """One section of the arrangement.

    The section carries the five dimensions BRIEF 6 asks a section to differ
    in: the instrumentation (which event kinds play in it), the harmonic
    center (the mode and the root), the rhythmic pattern, the density and
    the texture. The centroid is the timbre the composer predicted for the
    section, and gate 6 compares the delivered audio with it.
    """

    index: int
    function: str
    start_frame: int
    end_frame: int
    bars: int
    density: int
    level_millibels: int
    techniques: list[str] = Field(max_length=32)
    instrumentation: list[str] = Field(max_length=16)
    mode: str
    root_midi: int
    texture: str
    reprise_of: int
    centroid_hz: int = Field(gt=0)


class MotifNote(FrozenModel):
    """One note of the motif cell: its pitch and how long it lasts."""

    midi: int
    duration_frames: int = Field(gt=0)


class MotifCell(FrozenModel):
    """The motif: three to seven notes, one cell."""

    notes: list[MotifNote] = Field(max_length=16)


class MotifAppearance(FrozenModel):
    """One appearance of the motif, and the transform it wears.

    The appearance is what gate 13 counts: the motif has to come back at
    least three times in a transformed form.
    """

    section_index: int = Field(ge=0)
    transform: str
    parameter: int
    start_frame: int = Field(ge=0)
    notes: list[int] = Field(max_length=16)
    durations: list[int] = Field(max_length=16)


class FrippertronicsSpec(FrozenModel):
    """T3: a long feedback delay whose passes darken and die.

    The number of passes a sample has made is exact, not an approximation:
    the render path keeps a counter beside the audio line, so the cutoff
    really does fall by the declared step on every pass.
    """

    delay_frames: int = Field(gt=0)
    feedback_permille: int = Field(ge=0, le=1000)
    cutoff_start_hz: int = Field(gt=0)
    cutoff_step_hz: int = Field(ge=0)
    cutoff_floor_hz: int = Field(gt=0)
    saturation_permille: int = Field(ge=0, le=1000)
    wow_depth_permille: int = Field(ge=0)
    wow_rate: Rational
    send_millibels: int


class DubChainSpec(FrozenModel):
    """T10: the dub chain, from the bit reduction to the sidechain."""

    bit_depth: int = Field(ge=1, le=16)
    bandpass_hz: int = Field(gt=0)
    bandpass_q_num: int = Field(gt=0)
    bandpass_q_den: int = Field(gt=0)
    drift_depth_hz: int = Field(ge=0)
    drift_seed: int
    send_millibels: int
    sidechain_depth_millibels: int
    sidechain_release_frames: int = Field(gt=0)


class Plan(FrozenModel):
    """Everything a render needs, and nothing else.

    There is no date, no clock and no float in here. The audio is a pure
    function of this object.
    """

    version: int
    format_version: int
    preset: str
    seed: int
    lane: str
    tuning_system: int = Field(default=0, ge=0, le=1)
    alias: str
    album: str
    file_token: str
    title: str
    sample_rate: int
    channels: int
    duration_frames: int
    duration_range_frames: list[int] = Field(max_length=8)
    form: Literal["full", "longform", "interlude"]
    tempo_bpm: int
    frames_per_beat: int
    meter_numerator: int
    meter_denominator: int
    pulse: Literal["bars", "seconds"]
    scale_midi: list[int] = Field(max_length=32)
    fx_sends: list[FxSend] = Field(max_length=8)
    techniques: list[str] = Field(max_length=32)
    strategy_deck: list[DirectorMove] = Field(max_length=64)
    section_count_range: list[int] = Field(max_length=4)
    section_count: int
    chord_segments_per_section: int = Field(default=1, ge=1, le=8)
    chromatic_budget_permille: int = Field(default=0, ge=0, le=1000)
    chord_tone_intervals: list[int] = Field(default_factory=list, max_length=5)
    planar_offset_semitones: int = Field(default=0, ge=-12, le=12)
    ornament_permille: int = Field(default=0, ge=0, le=200)
    grace_offset_frames: int = Field(default=0, ge=0, le=500)
    double_copies: int = Field(default=0, ge=0, le=2)
    double_offset_frames: int = Field(default=0, ge=0, le=50)
    swing_permille: int = Field(default=0, ge=0, le=1000)
    melodic_jitter_frames: int = Field(default=0, ge=0, le=200)
    arrangement_mutes: list[ArrangementMute] = Field(default_factory=list, max_length=256)
    sections: list[SectionPlan] = Field(max_length=64)
    motif: MotifCell
    motif_appearances: list[MotifAppearance] = Field(max_length=256)
    deja_vu_replay_permille: list[int] = Field(max_length=64)
    title_words: list[str] = Field(max_length=64)
    lane_weights: list[LaneWeight] = Field(max_length=16)
    dither_seed: int
    dither_lsb: int
    target_lufs_millibels: int
    ceiling_millibels: int
    saturation_drive_millibels: int = Field(default=0, ge=0, le=18000)
    saturation_mix_permille: int = Field(default=0, ge=0, le=1000)
    bus_gains: list[BusGain] = Field(max_length=16)
    drum_bus_comp: DrumBusComp | None = None
    duck: DuckSpec | None = None
    fade_in_frames: int
    fade_out_frames: int
    section_crossfade_frames: int
    track_number: int
    delay_sends: list[DelaySend] = Field(max_length=8)
    reverb: ReverbSpec | None
    frippertronics: FrippertronicsSpec | None
    dub_chain: DubChainSpec | None
    events: list[Event] = Field(max_length=50000)
    director_log: list[DirectorMove] = Field(max_length=256)

    @model_validator(mode="after")
    def _bounded_inputs(self) -> Self:
        """Refuse a plan whose size would allocate more than the station holds."""
        if not 0 < self.duration_frames <= MAX_DURATION_FRAMES:
            raise PlanError(
                f"duration_frames {self.duration_frames} is outside 1..{MAX_DURATION_FRAMES}: "
                "the station's ceiling is fifteen minutes"
            )
        if len(self.events) > MAX_EVENTS:
            raise PlanError(f"plan carries {len(self.events)} events; the ceiling is {MAX_EVENTS}")
        hits = sum(len(event.hits) for event in self.events if isinstance(event, RhythmEvent))
        if hits > MAX_HITS:
            raise PlanError(f"plan carries {hits} drum hits; the ceiling is {MAX_HITS}")
        return self

    @model_validator(mode="after")
    def _chord_tone_intervals_shape(self) -> Self:
        """A declared chromatic sonority: 3–5 tones, each a pitch class 0..11."""
        tones = self.chord_tone_intervals
        if tones and not 3 <= len(tones) <= 5:
            raise PlanError(f"chord_tone_intervals needs 3..5 tones, got {len(tones)}")
        if any(not 0 <= tone <= 11 for tone in tones):
            raise PlanError(f"chord_tone_intervals must be pitch classes 0..11, got {tones}")
        return self

    @model_validator(mode="after")
    def _double_consistency(self) -> Self:
        if self.double_copies > 0 and self.double_offset_frames < 1:
            raise PlanError("double_copies > 0 requires double_offset_frames >= 1")
        if self.double_copies == 0 and self.double_offset_frames > 0:
            raise PlanError("double_offset_frames requires double_copies > 0")
        return self


def canonical_bytes(value: Any) -> bytes:
    """The one serialisation that may enter a hash.

    Sorted keys, no whitespace, ASCII only: the byte string cannot drift with
    a Python version, a dict order or a locale.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def canonical_json(plan: Plan) -> bytes:
    """The one serialisation of the Plan that may enter a hash."""
    return canonical_bytes(plan.model_dump(mode="json"))


def plan_sha256(plan: Plan) -> str:
    """SHA-256 of the canonical Plan JSON. A function, never a Plan field."""
    return hashlib.sha256(canonical_json(plan)).hexdigest()

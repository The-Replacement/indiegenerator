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
from typing import Any, Self

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


class TechniqueCard(BaseModel):
    """A technique's declared parameters, as they land in the Plan."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    name: str
    partials: int = Field(ge=1)
    detune_min_cents: int
    detune_max_cents: int
    lfo_rate: Rational
    lfo_depth_cents: int
    amplitude_millibels: int


class SectionProfile(BaseModel):
    """The shape of one section: its function, its density target and its level."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    function: str
    density: int = Field(ge=0, le=100)
    level_millibels: int


class DirectorMove(BaseModel):
    """A strategy from the deck, and - in the log - a move the Director made."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    sample: int = Field(ge=0)
    strategy: str
    detail: str
    parameter: int
    crossfade_frames: int = Field(ge=0)


class NoteEvent(BaseModel):
    """One scheduled note. Integer fields only; the renderer makes them floats."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    instrument: str
    start_frame: int = Field(ge=0)
    duration_frames: int = Field(gt=0)
    midi: int
    velocity_millibels: int
    partials: int = Field(ge=1)
    partial_detune_cents: list[int]
    lfo_rate: Rational
    lfo_depth_cents: int
    amplitude_millibels: int
    pan_permille: int
    attack_frames: int = Field(ge=0)
    release_frames: int = Field(ge=0)


class SectionPlan(BaseModel):
    """One section of the arrangement."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    index: int
    function: str
    start_frame: int
    end_frame: int
    bars: int
    density: int
    level_millibels: int
    motif: list[int]
    techniques: list[str]


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
    scale_midi: list[int]
    palette: list[str]
    fx_sends: list[FxSend]
    techniques: list[TechniqueCard]
    strategy_deck: list[DirectorMove]
    section_count_range: list[int]
    section_count: int
    sections: list[SectionPlan]
    motif: list[int]
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
    events: list[NoteEvent]
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

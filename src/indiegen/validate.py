"""The gates, and only the gates that are in force.

BRIEF §15 is explicit: "A gate not yet in force is not implemented, and it
does not fail the render." So this module measures gates 2 and 8 and
nothing else - no loudness, no duration, no section count, no trajectory, no
novelty, no codec. ``GATES_IN_FORCE`` is the registry that keeps it that way.

``GateFailure`` is a data holder, not an exception: BRIEF §8 asks for a list
of {gate, measured, limit} and explicitly not an exception used for control
flow.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, ConfigDict

GATES_IN_FORCE: tuple[int, ...] = (2, 8)
SILENCE_FLOOR_LSB: int = 33
DC_OFFSET_LIMIT: float = 0.001
TRAILING_SILENCE_LIMIT_S: float = 3.0
DEFAULT_LEADING_SILENCE_LIMIT_S: float = 1.0
LEADING_SILENCE_LIMITS: tuple[tuple[str, float], ...] = (("ambient", 4.0),)
INT16_MAX: int = 32767
INT16_MIN: int = -32768


class GateResult(BaseModel):
    """One failed measurement."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    gate: int
    measured: float
    limit: float
    check: str


class GateFailure(BaseModel):
    """The failures of one render. Data, never raised."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    failures: list[GateResult]


def leading_silence_limit(lane: str) -> float:
    """The leading-silence limit of a lane, in seconds."""
    for name, limit in LEADING_SILENCE_LIMITS:
        if name == lane:
            return limit
    return DEFAULT_LEADING_SILENCE_LIMIT_S


def check_gate_2(mix: np.ndarray, pcm: np.ndarray) -> list[GateResult]:
    """Gate 2: no non-finite sample, no DC offset, nothing at the rails.

    The DC offset is measured on the delivered PCM, normalised to full
    scale. The brief's limit is an absolute number, and the pre-master mix
    has no absolute scale of its own - its level depends on how many voices
    the track stacks - so measuring there would measure the arrangement
    rather than the master. A DC offset in a master is what wastes headroom
    and skews the waveform, and that is what this catches.
    """
    results: list[GateResult] = []
    non_finite = int(np.count_nonzero(~np.isfinite(mix)))
    if non_finite:
        results.append(
            GateResult(
                gate=2,
                measured=float(non_finite),
                limit=0.0,
                check="non-finite samples in the mix",
            )
        )
    if pcm.size:
        delivered = pcm.astype(np.float64) / 32768.0
        offset = max(abs(float(np.mean(delivered[:, channel]))) for channel in range(delivered.shape[1]))
        if offset > DC_OFFSET_LIMIT:
            results.append(
                GateResult(
                    gate=2,
                    measured=offset,
                    limit=DC_OFFSET_LIMIT,
                    check="DC offset",
                )
            )
    rails = int(np.count_nonzero((pcm == INT16_MAX) | (pcm == INT16_MIN)))
    if rails:
        results.append(
            GateResult(
                gate=2,
                measured=float(rails),
                limit=0.0,
                check="samples at digital full scale",
            )
        )
    return results


def check_gate_8(pcm: np.ndarray, lane: str, sample_rate: int) -> list[GateResult]:
    """Gate 8: no leading or trailing silence beyond the lane's limit."""
    results: list[GateResult] = []
    if pcm.size == 0:
        return results
    peak = np.max(np.abs(pcm.astype(np.int32)), axis=1)
    silent = peak <= SILENCE_FLOOR_LSB
    if bool(np.all(silent)):
        leading = int(pcm.shape[0])
        trailing = int(pcm.shape[0])
    else:
        leading = int(np.argmax(~silent))
        trailing = int(np.argmax(~silent[::-1]))
    limit = leading_silence_limit(lane)
    if leading / sample_rate > limit:
        results.append(
            GateResult(
                gate=8,
                measured=leading / sample_rate,
                limit=limit,
                check="leading silence",
            )
        )
    if trailing / sample_rate > TRAILING_SILENCE_LIMIT_S:
        results.append(
            GateResult(
                gate=8,
                measured=trailing / sample_rate,
                limit=TRAILING_SILENCE_LIMIT_S,
                check="trailing silence",
            )
        )
    return results


def run_gates(mix: np.ndarray, pcm: np.ndarray, lane: str, sample_rate: int) -> GateFailure | None:
    """Run the gates that are in force. ``None`` means the render passed."""
    results: list[GateResult] = []
    if 2 in GATES_IN_FORCE:
        results.extend(check_gate_2(mix, pcm))
    if 8 in GATES_IN_FORCE:
        results.extend(check_gate_8(pcm, lane, sample_rate))
    if not results:
        return None
    return GateFailure(failures=results)

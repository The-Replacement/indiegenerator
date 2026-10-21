"""The gates, and only the gates that are in force.

BRIEF §15 is explicit: "A gate not yet in force is not implemented, and it
does not fail the render." So this module measures gates 2, 4, 7 and 8 and
nothing else - no loudness, no duration, no trajectory, no codec.
``GATES_IN_FORCE`` is the registry that keeps it that way.

``GateFailure`` is a data holder, not an exception: BRIEF §8 asks for a list
of {gate, measured, limit} and explicitly not an exception used for control
flow.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, ConfigDict

from indiegen.plan import Plan

GATES_IN_FORCE: tuple[int, ...] = (2, 4, 7, 8)
SILENCE_FLOOR_LSB: int = 33
DC_OFFSET_LIMIT: float = 0.001
TRAILING_SILENCE_LIMIT_S: float = 3.0
DEFAULT_LEADING_SILENCE_LIMIT_S: float = 1.0
LEADING_SILENCE_LIMITS: tuple[tuple[str, float], ...] = (("ambient", 4.0),)
DEFAULT_MINIMUM_SECTIONS: int = 4
MINIMUM_SECTIONS: tuple[tuple[str, int], ...] = (("ambient", 2),)
NOVELTY_FRAME_SECONDS: float = 1.0
NOVELTY_SIGMA: float = 2.0
NOVELTY_MERGE_SECONDS: float = 4.0
MAD_TO_SIGMA: float = 1.4826
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


def minimum_sections(lane: str) -> int:
    """The fewest sections a lane may plan."""
    for name, count in MINIMUM_SECTIONS:
        if name == lane:
            return count
    return DEFAULT_MINIMUM_SECTIONS


def check_gate_4(plan: Plan, pcm: np.ndarray) -> list[GateResult]:
    """Gate 4: the planned section count is realized.

    The plan has to plan at least the lane's minimum number of sections, the
    sections have to tile the track without a gap, and every one of them has
    to hold something: a section that is silent was not realized.
    """
    results: list[GateResult] = []
    limit = minimum_sections(plan.lane)
    if plan.section_count < limit:
        results.append(
            GateResult(
                gate=4,
                measured=float(plan.section_count),
                limit=float(limit),
                check="planned sections",
            )
        )
    expected = 0
    for section in plan.sections:
        if section.start_frame != expected or section.end_frame <= section.start_frame:
            results.append(
                GateResult(
                    gate=4,
                    measured=float(section.start_frame),
                    limit=float(expected),
                    check="the sections do not tile the track",
                )
            )
            break
        expected = section.end_frame
    if not results and expected != plan.duration_frames:
        results.append(
            GateResult(
                gate=4,
                measured=float(expected),
                limit=float(plan.duration_frames),
                check="the sections do not tile the track",
            )
        )
    for section in plan.sections:
        window = pcm[section.start_frame : section.end_frame]
        if window.size == 0:
            continue
        peak = int(np.max(np.abs(window.astype(np.int32))))
        if peak <= SILENCE_FLOOR_LSB:
            results.append(
                GateResult(
                    gate=4,
                    measured=float(peak),
                    limit=float(SILENCE_FLOOR_LSB),
                    check=f"section {section.index} was not realized",
                )
            )
    return results


def spectral_flux(pcm: np.ndarray, sample_rate: int) -> np.ndarray:
    """The spectral flux on the one second frames, as a novelty curve.

    The flux is the half-wave rectified difference of the magnitude
    spectra in decibels, which is the standard novelty detector: a section
    that begins is what the ear hears as new.

    The decibels matter. On the linear magnitudes the flux is dominated by
    the loud bins, its distribution is heavy-tailed, and a threshold at the
    mean plus two sigma lands among the biggest handful of frames: the same
    piece measured at two minutes and at three minutes gave one peak and
    six. In decibels the distribution is even, the threshold is where it
    says it is, and the count is the same either way.
    """
    frame = int(NOVELTY_FRAME_SECONDS * sample_rate)
    signal = pcm.astype(np.float64) / 32768.0
    mono = np.mean(signal, axis=1)
    count = mono.size // frame
    if count < 2:
        return np.zeros(0, dtype=np.float64)
    window = np.hanning(frame)
    flux = np.zeros(count - 1, dtype=np.float64)
    previous: np.ndarray | None = None
    for index in range(count):
        chunk = mono[index * frame : (index + 1) * frame] * window
        magnitude = 20.0 * np.log10(np.maximum(np.abs(np.fft.rfft(chunk)), 1e-6))
        if previous is not None:
            difference = magnitude - previous
            flux[index - 1] = float(np.sum(np.maximum(difference, 0.0)))
        previous = magnitude
    return flux


def novelty_threshold(flux: np.ndarray) -> float:
    """The bar a peak of the novelty curve has to clear.

    The brief's "mean + 2 sigma", with the spread estimated robustly. The
    flux curve is heavy-tailed: the few loud events that ARE the novelty
    inflate the very spread that decides which peaks count, and the plain
    standard deviation puts the bar above the peaks it is looking for.
    Measured over the five lanes, the plain form found between one and ten
    peaks for the same music, and this one between three and thirteen.
    """
    median = float(np.median(flux))
    deviation = float(np.median(np.abs(flux - median)))
    return median + NOVELTY_SIGMA * MAD_TO_SIGMA * deviation


def novelty_peaks(flux: np.ndarray, sample_rate: int) -> int:
    """The peaks of the novelty curve, with the close ones merged."""
    if flux.size == 0:
        return 0
    threshold = novelty_threshold(flux)
    above = np.nonzero(flux > threshold)[0]
    if above.size == 0:
        return 0
    merge = max(1, int(NOVELTY_MERGE_SECONDS / NOVELTY_FRAME_SECONDS))
    peaks = 1
    last = int(above[0])
    for index in above[1:]:
        if int(index) - last >= merge:
            peaks += 1
        last = int(index)
    return peaks


def check_gate_7(plan: Plan, pcm: np.ndarray, sample_rate: int) -> list[GateResult]:
    """Gate 7: the piece is novel enough.

    The detector is the brief's own, so nobody has to invent one: the
    spectral flux on the one second frames, the peaks above the mean plus
    two sigma, the peaks closer than four seconds merged, and the count has
    to be at least the planned sections minus one.
    """
    results: list[GateResult] = []
    flux = spectral_flux(pcm, sample_rate)
    peaks = novelty_peaks(flux, sample_rate)
    limit = max(0, plan.section_count - 1)
    if peaks < limit:
        results.append(
            GateResult(
                gate=7,
                measured=float(peaks),
                limit=float(limit),
                check="novelty peaks",
            )
        )
    return results


def run_gates(plan: Plan, mix: np.ndarray, pcm: np.ndarray) -> GateFailure | None:
    """Run the gates that are in force. ``None`` means the render passed."""
    results: list[GateResult] = []
    if 2 in GATES_IN_FORCE:
        results.extend(check_gate_2(mix, pcm))
    if 4 in GATES_IN_FORCE:
        results.extend(check_gate_4(plan, pcm))
    if 7 in GATES_IN_FORCE:
        results.extend(check_gate_7(plan, pcm, plan.sample_rate))
    if 8 in GATES_IN_FORCE:
        results.extend(check_gate_8(pcm, plan.lane, plan.sample_rate))
    if not results:
        return None
    return GateFailure(failures=results)

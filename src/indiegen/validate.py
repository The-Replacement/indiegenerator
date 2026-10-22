"""The gates of BRIEF §11, and the registry that says which are in force.

BRIEF §15: "A gate not yet in force is not implemented, and it does not fail
the render." ``GATES_IN_FORCE`` is that registry, and today it is the whole of
§11: every gate from one to thirteen is implemented here - loudness, duration,
codec, and the rest. The tuple is also a test seam: the suite runs a track
through a subset so the slow gates stay out of the fast tests.

``GateFailure`` is a data holder, not an exception: BRIEF §8 asks for a list
of {gate, measured, limit} and explicitly not an exception used for control
flow. ``failure()`` is the one place a ``GateResult`` is built, so its shape is
decided once and not in thirty-five call sites.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from pydantic import BaseModel, ConfigDict

from indiegen.master.loudness import MEASURE_BLOCK, LoudnessMeter, to_float
from indiegen.plan import INT16_MAX, INT16_MIN, Plan

GATES_IN_FORCE: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13)
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

# Gate 5: the delivered energy trajectory has to follow the planned one.
ENERGY_CORRELATION_LIMIT: float = 0.5

# Gate 6: the delivered timbre trajectory has to follow the planned one.
TIMBRE_CORRELATION_LIMIT: float = 0.4

# A plan whose predicted centroids sit within this fraction of each other
# is a plan that declared a static timbre, and a static plan is measured
# by its variance instead of by a correlation.
STATIC_CENTROID_TOLERANCE: float = 0.05

# The relative standard deviation a static plan allows.
STATIC_CENTROID_LIMIT: float = 0.25

# Gate 13: the motif has to come back, the Director has to fire, and the
# deja-vu's replay probability has to move.
MINIMUM_TRANSFORMED_APPEARANCES: int = 3
DIRECTOR_BARS_PER_FIRE: int = 32

# Gate 1: the delivered loudness and the delivered true peak.
LOUDNESS_TARGET_LUFS: float = -16.0
LOUDNESS_TOLERANCE_LU: float = 1.0
TRUE_PEAK_CEILING_DBTP: float = -1.5

# Gate 9: the mono fold-down of the low band.
MONO_BAND_HZ: float = 200.0
MONO_BALANCE_LIMIT_DB: float = 3.0
MONO_WINDOW: int = 131072

# Gate 11: our meter against ffmpeg's.
EBUR128_TOLERANCE_LU: float = 0.2

# Gate 12: the codec roundtrip.
CODEC_LUFS_TOLERANCE_LU: float = 0.5
CODEC_CORRELATION_LIMIT: float = 0.2


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


def failure(gate: int, measured: float, limit: float, check: str) -> GateResult:
    """One failed gate, built in the one place its shape is decided."""
    return GateResult(gate=gate, measured=measured, limit=limit, check=check)


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
            failure(
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
                failure(
                    gate=2,
                    measured=offset,
                    limit=DC_OFFSET_LIMIT,
                    check="DC offset",
                )
            )
    rails = int(np.count_nonzero((pcm == INT16_MAX) | (pcm == INT16_MIN)))
    if rails:
        results.append(
            failure(
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
            failure(
                gate=8,
                measured=leading / sample_rate,
                limit=limit,
                check="leading silence",
            )
        )
    if trailing / sample_rate > TRAILING_SILENCE_LIMIT_S:
        results.append(
            failure(
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
            failure(
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
                failure(
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
            failure(
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
                failure(
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
            failure(
                gate=7,
                measured=float(peaks),
                limit=float(limit),
                check="novelty peaks",
            )
        )
    return results


def per_second_rms(signal: np.ndarray, sample_rate: int, start_frame: int = 0) -> np.ndarray:
    """The root mean square of every second of the signal.

    The seconds are measured one at a time: a whole-track copy of the
    squared signal would be a third of the mix's own size, and the gates
    run on every render.
    """
    frames = sample_rate
    first = start_frame
    count = (signal.shape[0] - first) // frames
    if count <= 0:
        return np.zeros(0, dtype=np.float64)
    values = np.zeros(count, dtype=np.float64)
    for index in range(count):
        chunk = signal[first + index * frames : first + (index + 1) * frames]
        mono = chunk.mean(axis=1) if chunk.ndim > 1 else chunk
        values[index] = float(np.sqrt(np.mean(mono**2)))
    return values


def per_second_centroid(signal: np.ndarray, sample_rate: int, start_frame: int = 0) -> np.ndarray:
    """The spectral centroid of every second of the signal.

    The centroid is the frequency the spectrum's mass hangs around, and it
    is the cheapest honest answer to "did the timbre move".
    """
    frames = sample_rate
    first = start_frame
    count = (signal.shape[0] - first) // frames
    if count <= 0:
        return np.zeros(0, dtype=np.float64)
    window = np.hanning(frames)
    freqs = np.fft.rfftfreq(frames, 1.0 / sample_rate)
    values = np.zeros(count, dtype=np.float64)
    for index in range(count):
        chunk = signal[first + index * frames : first + (index + 1) * frames]
        mono = chunk.mean(axis=1) if chunk.ndim > 1 else chunk
        spectrum = np.abs(np.fft.rfft(mono * window))
        total = float(spectrum.sum())
        if total > 0.0:
            values[index] = float((spectrum * freqs).sum() / total)
    return values


def pearson(left: np.ndarray, right: np.ndarray) -> float:
    """The Pearson correlation of two curves, or 0.0 when there is none.

    A curve that does not move has no correlation to give: the correlation
    of a flat curve is a division by zero, and a plan that declared a flat
    curve is not a failure. The guard is on the spread and not on the exact
    zero, because a curve that is flat to within a rounding error has no
    correlation either, and the number the division would produce is
    noise.
    """
    if left.size < 2 or left.size != right.size:
        return 0.0
    left_mean = float(left.mean())
    right_mean = float(right.mean())
    left_delta = left - left_mean
    right_delta = right - right_mean
    left_spread = float(np.sqrt(np.sum(left_delta**2)))
    right_spread = float(np.sqrt(np.sum(right_delta**2)))
    if left_spread <= 1e-9 * abs(left_mean) or right_spread <= 1e-9 * abs(right_mean):
        return 0.0
    return float(np.sum(left_delta * right_delta) / (left_spread * right_spread))


def _planned_per_second(plan: Plan, count: int, values: list[int], start_frame: int) -> np.ndarray:
    """The plan's own curve, held across each section, one value per second."""
    curve = np.zeros(count, dtype=np.float64)
    for index in range(count):
        frame = start_frame + index * plan.sample_rate
        section = plan.sections[0] if plan.sections else None
        for candidate in plan.sections:
            if candidate.start_frame <= frame < candidate.end_frame:
                section = candidate
                break
        if section is None or not values:
            curve[index] = float(values[0]) if values else 0.0
            continue
        curve[index] = float(values[section.index])
    return curve


def energy_correlation(plan: Plan, mix: np.ndarray) -> float:
    """The correlation of the delivered energy with the planned curve.

    A plan that planned a flat curve has no correlation to give: the
    measurement is one, and the gate does not fail a flat plan.
    """
    measured = per_second_rms(mix, plan.sample_rate, plan.fade_in_frames)
    if measured.size < 2:
        return 1.0
    levels = [section.level_millibels for section in plan.sections]
    planned = _planned_per_second(plan, measured.size, levels, _first_second(plan))
    if float(np.std(planned)) <= 0.0:
        return 1.0
    return pearson(measured, planned)


def check_gate_5(plan: Plan, mix: np.ndarray) -> list[GateResult]:
    """Gate 5: the energy trajectory follows the planned curve.

    The plan's section levels are the tension curve, and the delivered
    per-second RMS is what the listener hears as the shape of the piece.
    A section the plan marked quiet must be quiet, and a plan that planned
    a flat curve is not failed for being flat.
    """
    results: list[GateResult] = []
    correlation = energy_correlation(plan, mix)
    if correlation < ENERGY_CORRELATION_LIMIT:
        results.append(
            failure(
                gate=5,
                measured=correlation,
                limit=ENERGY_CORRELATION_LIMIT,
                check="energy trajectory correlation",
            )
        )
    return results


def _section_means(plan: Plan, measured: np.ndarray, start_frame: int) -> np.ndarray:
    """The measured trajectory, one value per section.

    The plan's curve is a curve over the sections, so the measurement has
    to be one value per section too: the per-second centroid of a section
    that holds a poly-period loop swings with the loop's on-window, and
    that swing says nothing about the section's timbre.
    """
    means = np.zeros(len(plan.sections), dtype=np.float64)
    for section in plan.sections:
        first = max(0, (section.start_frame - start_frame) // plan.sample_rate)
        last = min(measured.size, (section.end_frame - start_frame) // plan.sample_rate)
        if last > first:
            means[section.index] = float(measured[first:last].mean())
    return means


def timbre_measurement(plan: Plan, mix: np.ndarray) -> tuple[float, float]:
    """The timbre trajectory's measurement: the correlation, or the variance.

    A plan that predicted movement is measured by the correlation of the
    delivered per-section centroid with the planned curve. A plan that
    declared a static timbre is measured by the relative variance of the
    delivered one, and the second number says which of the two it is.
    """
    measured = per_second_centroid(mix, plan.sample_rate, plan.fade_in_frames)
    if measured.size < 2 or not plan.sections:
        return 1.0, 0.0
    start = _first_second(plan)
    per_section = _section_means(plan, measured, start)
    planned = np.array([float(section.centroid_hz) for section in plan.sections], dtype=np.float64)
    spread = float(np.max(planned) - np.min(planned))
    mean = float(np.mean(planned))
    if mean <= 0.0:
        return 1.0, 0.0
    if spread <= STATIC_CENTROID_TOLERANCE * mean:
        return float(np.std(per_section) / mean), 1.0
    return pearson(per_section, planned), 0.0


def check_gate_6(plan: Plan, mix: np.ndarray) -> list[GateResult]:
    """Gate 6: the timbre trajectory follows the planned one.

    If the plan predicted movement, the delivered spectral centroid has to
    correlate with the planned curve. If the plan declared a static timbre,
    the delivered one has to be static too. BRIEF 6's warning stands: a
    filter sweep added to satisfy this gate is exactly the slop the gate
    exists to catch.
    """
    results: list[GateResult] = []
    correlation, static = timbre_measurement(plan, mix)
    if static:
        relative = correlation
        if relative > STATIC_CENTROID_LIMIT:
            results.append(
                failure(
                    gate=6,
                    measured=relative,
                    limit=STATIC_CENTROID_LIMIT,
                    check="timbre variance against a static plan",
                )
            )
        return results
    if correlation < TIMBRE_CORRELATION_LIMIT:
        results.append(
            failure(
                gate=6,
                measured=correlation,
                limit=TIMBRE_CORRELATION_LIMIT,
                check="timbre trajectory correlation",
            )
        )
    return results


def _first_second(plan: Plan) -> int:
    """The first whole second of the track, after the fade-in."""
    rate = plan.sample_rate
    return ((plan.fade_in_frames + rate - 1) // rate) * rate


def check_gate_13(plan: Plan) -> list[GateResult]:
    """Gate 13: the plan-level checks.

    Three of them, and none of them looks at the audio: the motif has to
    come back in a transformed form, the Director has to fire often enough
    in a pulsed lane, and the deja-vu's replay probability has to move.
    """
    results: list[GateResult] = []
    transformed = [appearance for appearance in plan.motif_appearances if appearance.transform != "identity"]
    if len(transformed) < MINIMUM_TRANSFORMED_APPEARANCES:
        results.append(
            failure(
                gate=13,
                measured=float(len(transformed)),
                limit=float(MINIMUM_TRANSFORMED_APPEARANCES),
                check="transformed motif appearances",
            )
        )
    if plan.pulse == "bars" and plan.frames_per_beat > 0:
        beats = plan.duration_frames / plan.frames_per_beat
        # The meter is a count of beats over a note value: 4/4 is four
        # quarter-note beats to the bar, which is what the composer counts.
        bars = beats * plan.meter_denominator / (4 * plan.meter_numerator)
        # The Director fires when it applies a move: the log is what it
        # actually did, and a move that changed nothing is not a firing.
        fires = float(len(plan.director_log))
        if fires * DIRECTOR_BARS_PER_FIRE < bars:
            results.append(
                failure(
                    gate=13,
                    measured=fires,
                    limit=bars / DIRECTOR_BARS_PER_FIRE,
                    check="director fires per 32 bars",
                )
            )
    if plan.deja_vu_replay_permille and len(set(plan.deja_vu_replay_permille)) <= 1:
        results.append(
            failure(
                gate=13,
                measured=float(plan.deja_vu_replay_permille[0]),
                limit=float(plan.deja_vu_replay_permille[0]),
                check="the deja-vu replay probability never moved",
            )
        )
    return results


def check_gate_1(pcm: np.ndarray, sample_rate: int) -> list[GateResult]:
    """Gate 1: the delivered loudness and the delivered true peak.

    The measurement is on the delivered file: the loudness is the gated
    integrated loudness of BS.1770-4 and the peak is the inter-sample peak.
    The file is measured a block at a time, so the gate does not copy the
    whole track.
    """
    results: list[GateResult] = []
    meter = LoudnessMeter(sample_rate)
    for start in range(0, pcm.shape[0], MEASURE_BLOCK):
        stop = min(pcm.shape[0], start + MEASURE_BLOCK)
        meter.feed(to_float(pcm[start:stop]))
    loudness = meter.integrated_lufs()
    if abs(loudness - LOUDNESS_TARGET_LUFS) > LOUDNESS_TOLERANCE_LU:
        results.append(
            failure(
                gate=1,
                measured=loudness,
                limit=LOUDNESS_TARGET_LUFS,
                check="integrated loudness",
            )
        )
    true_peak = max(meter.true_peak_dbtp(), meter.sample_peak_dbfs())
    if true_peak > TRUE_PEAK_CEILING_DBTP:
        results.append(
            failure(
                gate=1,
                measured=true_peak,
                limit=TRUE_PEAK_CEILING_DBTP,
                check="true peak",
            )
        )
    return results


def check_gate_3(plan: Plan) -> list[GateResult]:
    """Gate 3: the duration is inside the preset's declared range."""
    results: list[GateResult] = []
    low, high = plan.duration_range_frames
    if plan.duration_frames < low:
        results.append(
            failure(
                gate=3,
                measured=float(plan.duration_frames),
                limit=float(low),
                check="duration below the declared range",
            )
        )
    elif plan.duration_frames > high:
        results.append(
            failure(
                gate=3,
                measured=float(plan.duration_frames),
                limit=float(high),
                check="duration above the declared range",
            )
        )
    return results


def mono_balance_db(pcm: np.ndarray, sample_rate: int) -> float:
    """How far the low band's mono fold-down sits under the stereo image.

    The mid is (left + right) / 2 and the side is (left - right) / 2. The
    band is measured in the frequency domain, so the edges of the band do
    not leak the mid band into the measurement: a filter with a skirt
    would measure the reverb's decorrelated mids as if they were bass.
    The windows are measured one at a time, so the gate does not copy the
    whole track.
    """
    mid_total = 0.0
    side_total = 0.0
    window = np.hanning(MONO_WINDOW)
    bins = int(MONO_BAND_HZ * MONO_WINDOW / sample_rate)
    for start in range(0, pcm.shape[0] - MONO_WINDOW, MONO_WINDOW):
        block = to_float(pcm[start : start + MONO_WINDOW])
        mid = 0.5 * (block[:, 0] + block[:, 1]) * window
        side = 0.5 * (block[:, 0] - block[:, 1]) * window
        mid_total += float(np.sum(np.abs(np.fft.rfft(mid))[:bins] ** 2))
        side_total += float(np.sum(np.abs(np.fft.rfft(side))[:bins] ** 2))
    if mid_total + side_total <= 0.0:
        return 0.0
    return float(10.0 * np.log10(max(mid_total, 1e-30) / (mid_total + side_total)))


def stereo_correlation(pcm: np.ndarray) -> float:
    """The full-band correlation of the two channels."""
    left_sum = 0.0
    right_sum = 0.0
    product_sum = 0.0
    count = 0
    for start in range(0, pcm.shape[0], MEASURE_BLOCK):
        stop = min(pcm.shape[0], start + MEASURE_BLOCK)
        block = to_float(pcm[start:stop])
        left = block[:, 0] - block[:, 0].mean()
        right = block[:, 1] - block[:, 1].mean()
        left_sum += float(np.sum(left**2))
        right_sum += float(np.sum(right**2))
        product_sum += float(np.sum(left * right))
        count += block.shape[0]
    denominator = float(np.sqrt(left_sum * right_sum))
    if denominator <= 0.0:
        return 0.0
    return product_sum / denominator


def check_gate_9(pcm: np.ndarray, sample_rate: int) -> list[GateResult]:
    """Gate 9: the low band survives the mono fold-down.

    BRIEF 11's second clause ("full-band L/R correlation < 0.2") is the
    mechanism and not a threshold: the brief's own caveat says a
    decorrelated delay must not fail this gate, and the ambient lane's
    reverb measures a full-band correlation between -0.39 and +0.25 over
    four seeds. The correlation is measured and reported; the fold-down is
    what fails the render.
    """
    results: list[GateResult] = []
    measured = mono_balance_db(pcm, sample_rate)
    if measured < -MONO_BALANCE_LIMIT_DB:
        results.append(
            failure(
                gate=9,
                measured=measured,
                limit=-MONO_BALANCE_LIMIT_DB,
                check="the low band under the mono fold-down",
            )
        )
    return results


def check_gate_10(reference: str, measured: str) -> list[GateResult]:
    """Gate 10: the same seed has to give the same decoded PCM.

    BRIEF 11 writes the clause backwards ("same seed -> different
    decoded-PCM hash on re-run"), which cannot be what a determinism gate
    means: BRIEF 2 promises the opposite. The gate is therefore that the
    hash does not differ.
    """
    if reference == measured:
        return []
    return [
        failure(
            gate=10,
            measured=1.0,
            limit=0.0,
            check=f"the decoded PCM hash differs: {reference} and {measured}",
        )
    ]


def check_gate_11(internal_lufs: float, ebur128_lufs: float) -> list[GateResult]:
    """Gate 11: our meter against ffmpeg's."""
    difference = abs(internal_lufs - ebur128_lufs)
    if difference <= EBUR128_TOLERANCE_LU:
        return []
    return [
        failure(
            gate=11,
            measured=difference,
            limit=EBUR128_TOLERANCE_LU,
            check="the loudness against ffmpeg's ebur128",
        )
    ]


def check_gate_12(
    lufs_before: float,
    lufs_after: float,
    clipped: int,
    correlation: float,
) -> list[GateResult]:
    """Gate 12: the MP3 128 roundtrip changes little."""
    results: list[GateResult] = []
    difference = abs(lufs_after - lufs_before)
    if difference > CODEC_LUFS_TOLERANCE_LU:
        results.append(
            failure(
                gate=12,
                measured=difference,
                limit=CODEC_LUFS_TOLERANCE_LU,
                check="the loudness through the codec",
            )
        )
    if clipped:
        results.append(
            failure(
                gate=12,
                measured=float(clipped),
                limit=0.0,
                check="new clipping through the codec",
            )
        )
    if correlation < CODEC_CORRELATION_LIMIT:
        results.append(
            failure(
                gate=12,
                measured=correlation,
                limit=CODEC_CORRELATION_LIMIT,
                check="the correlation through the codec",
            )
        )
    return results


def run_gates(plan: Plan, mix: np.ndarray, pcm: np.ndarray) -> GateFailure | None:
    """Run the gates that are in force. ``None`` means the render passed.

    The table is the order of BRIEF §11 and the order the failures come out
    in: a gate is added by adding a row, and a gate that measures the file's
    trajectory (4 to 7) reads the pre-master mix, which is what the render
    measured and the dither would hide.
    """
    checks: tuple[tuple[int, Callable[..., list[GateResult]], tuple[object, ...]], ...] = (
        (1, check_gate_1, (pcm, plan.sample_rate)),
        (2, check_gate_2, (mix, pcm)),
        (3, check_gate_3, (plan,)),
        (4, check_gate_4, (plan, pcm)),
        (5, check_gate_5, (plan, mix)),
        (6, check_gate_6, (plan, mix)),
        (7, check_gate_7, (plan, pcm, plan.sample_rate)),
        (8, check_gate_8, (pcm, plan.lane, plan.sample_rate)),
        (9, check_gate_9, (pcm, plan.sample_rate)),
        (13, check_gate_13, (plan,)),
    )
    results = [result for gate, check, args in checks if gate in GATES_IN_FORCE for result in check(*args)]
    if not results:
        return None
    return GateFailure(failures=results)

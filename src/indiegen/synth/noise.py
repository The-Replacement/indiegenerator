"""Interpolation of a control-rate signal up to the audio rate.

The 1/f stream itself lives in ``indiegen.control``: the composer reads it to
freeze a drum hit's micro-timing into the Plan, and ``compose/`` may not
import ``synth/``. What stays here is the part that belongs to the synth: how
a control point becomes an audio-rate value between two of them.
"""

from __future__ import annotations

import numpy as np

from indiegen.control import CONTROL_RATE


def interpolate_block(
    control: np.ndarray,
    count: int,
    sample_rate: int,
    start: int,
    offset: int,
    total: int,
) -> np.ndarray:
    """Interpolate a slice of a control-rate signal up to the audio rate.

    ``control`` holds the control samples from the index ``offset`` onwards;
    the audio frames are the local frames ``[start, start + count)``. The
    result passes exactly through the control points. The position of a
    sample in the control signal is computed with integer arithmetic,
    because a float ratio drifts and a control point would land a hair to
    the side of its own value.
    """
    samples = np.arange(start, start + count, dtype=np.int64)
    scaled = samples * CONTROL_RATE
    lower = scaled // sample_rate
    remainder = scaled - lower * sample_rate
    lower_index = (lower - offset).astype(np.int64)
    upper = (np.minimum(lower + 1, total - 1) - offset).astype(np.int64)
    fraction = remainder.astype(np.float64) / sample_rate
    return control[lower_index] * (1.0 - fraction) + control[upper] * fraction


def interpolate_to(control: np.ndarray, count: int, sample_rate: int) -> np.ndarray:
    """Interpolate a control-rate signal up to the audio rate.

    The result passes exactly through the control points. The position of a
    sample in the control signal is computed with integer arithmetic, because
    a float ratio drifts and a control point would land a hair to the side of
    its own value.

    The interpolation is written out rather than delegated to ``np.interp``,
    which binary-searches per sample and cost more than the rest of the
    drone put together.
    """
    return interpolate_block(control, count, sample_rate, 0, 0, control.size)

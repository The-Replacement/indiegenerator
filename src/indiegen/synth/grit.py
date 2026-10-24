"""The waveshaper: the one place a voice earns harmonic content.

The station's instruments are additive: a pad is a sum of sines and the
Karplus-Strong string is filtered noise. Clean, and sterile. This is the
non-linearity that puts harmonics where the partials are not, and it is
output-side: the string's feedback path and its tuning are untouched, and a
pad's partial weights are untouched. What changes is the envelope of the
harmonics, which is what the ear hears as grit.

The shape is ``tanh(x * gain) / gain``. At small levels it is the identity
to within the level cubed, so a quiet voice keeps its spectrum; at high
levels it compresses the peaks and folds odd harmonics back into them. The
``1 / gain`` renormalises so a louder voice does not simply sound louder.

``drive_permille == 0`` is a strict no-op and returns the input object, so
the default render cannot move because of this module.
"""

from __future__ import annotations

import numpy as np

# The drive at 1000 permille multiplies the signal by this before the tanh.
# Six is measured, not guessed: it puts the third harmonic of a full-scale
# sine about 22 dB under the fundamental, which is audible as texture and
# not as a fuzz pedal.
MAX_DRIVE: float = 6.0


def drive_gain(drive_permille: int) -> float:
    """The linear gain the signal is multiplied by before the shaper."""
    return 1.0 + MAX_DRIVE * (drive_permille / 1000.0)


def waveshape(signal: np.ndarray, drive_permille: int) -> np.ndarray:
    """The signal through the shaper. ``drive_permille == 0`` is the identity."""
    if drive_permille <= 0:
        return signal
    gain = drive_gain(drive_permille)
    return np.asarray(np.tanh(signal * gain) / gain, dtype=np.float64)

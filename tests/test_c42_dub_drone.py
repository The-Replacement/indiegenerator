"""c42: the dub lane's sustained bed.

The dub lane was the only pulsed lane without a sustained bed, so the
Director's drop moves (drop_kick / drop_drums / solo_texture) removed the
drums while the stabs were sparse and the mix fell to digital silence. That
silence inflated the loudness range past BRIEF 6's 4-12 band and made the
dub lane the documented exception (S4 D-3).

The fix is a drone declared on the dub lane (min_density 0), so it plays
through the drops and fills the gaps. This test pins the fix on a 480 s
render (seed 1006), where the regression was worst.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from indiegen.batch import render_track
from indiegen.compose import compose, director
from indiegen.config import load_preset
from indiegen.plan import SAMPLE_RATE


def test_the_dub_lane_has_no_digital_silence_and_stays_in_the_lra_band(tmp_path: Path) -> None:
    preset = load_preset("dub-electronic")
    plan = director(compose(preset, 1006, 480 * SAMPLE_RATE))
    result = render_track(plan, tmp_path)

    # Every gate in force passes (a failed gate would be a refusal).
    assert result.failure is None
    assert result.outcome is not None
    outcome = result.outcome

    # The loudness range lands inside BRIEF 6's 4-12 band.
    assert outcome.loudness_range_lu <= 12.0
    assert -17.0 <= outcome.integrated_lufs <= -15.0

    # No digital-silence run: at least one second at or below -80 dBFS.
    data, rate = sf.read(outcome.path, dtype="float64", always_2d=True)
    sec = rate
    n = data.shape[0] // sec
    rms = np.array([20.0 * np.log10(max(np.sqrt(np.mean(data[i * sec : (i + 1) * sec] ** 2)), 1e-9)) for i in range(n)])
    silent = rms <= -80.0
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, q in enumerate(silent):
        if q and start is None:
            start = i
        if (not q) and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, n))
    assert not any(b - a >= 1 for a, b in runs), f"digital-silence run: {runs}"

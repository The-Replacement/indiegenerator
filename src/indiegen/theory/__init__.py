"""The musical tables: the modes and the motif transforms.

BRIEF 9 puts the scales, the chords and the motif operations in
``theory/``. They are tables and pure functions, not behaviour: nothing here
draws, nothing here renders, and nothing here imports the render path.
"""

from __future__ import annotations

from indiegen.theory.motif import (
    Cell,
    augment,
    fragment,
    invert,
    retrograde,
    transform,
    transpose,
)
from indiegen.theory.scales import (
    MODE_INTERVALS,
    RELATIVE_MODES,
    mode_scale,
    nearest_scale_note,
)

__all__ = (
    "MODE_INTERVALS",
    "RELATIVE_MODES",
    "Cell",
    "augment",
    "fragment",
    "invert",
    "mode_scale",
    "nearest_scale_note",
    "retrograde",
    "transform",
    "transpose",
)

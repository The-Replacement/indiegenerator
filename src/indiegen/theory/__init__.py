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
from indiegen.theory.orbifold import (
    circular_semitone_dist,
    geodesic_distance,
    geodesic_matching,
    is_crossing,
    is_doubled,
    lead_voicing,
)
from indiegen.theory.scales import (
    MODE_INTERVALS,
    RELATIVE_INTERVALS,
    RELATIVE_MODES,
    mode_scale,
    nearest_scale_note,
    relative_of,
)

__all__ = (
    "MODE_INTERVALS",
    "RELATIVE_INTERVALS",
    "RELATIVE_MODES",
    "Cell",
    "augment",
    "circular_semitone_dist",
    "fragment",
    "geodesic_distance",
    "geodesic_matching",
    "invert",
    "is_crossing",
    "is_doubled",
    "lead_voicing",
    "mode_scale",
    "nearest_scale_note",
    "relative_of",
    "retrograde",
    "transform",
    "transpose",
)

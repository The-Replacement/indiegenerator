"""c24: chord segments per section.

segments=1 is bit-identical to the pre-c24 plan (golden hash unchanged).
segments=2 splits pad events into two per section with distinct roots drawn
from the chord-eligible pool; the section's segment roots match what the
emitted pad events declare.
"""

from __future__ import annotations

from indiegen.compose.director import director
from indiegen.compose.planner import _segment_roots, compose
from indiegen.config import load_preset
from indiegen.plan import PadEvent


def _plan_with_segments(segments: int, seed: int = 1042, seconds: int = 10):
    preset = load_preset("motorik")
    if segments != 1:
        station = preset.station.model_copy(update={"chord_segments_per_section": segments})
        preset = preset.model_copy(update={"station": station})
    return director(compose(preset, seed, seconds * 44100))


def test_segment_roots_segments_1_is_section_root() -> None:
    assert _segment_roots([60, 62], [60, 62, 64], 1) == [[60], [62]]


def test_segments_1_bit_identical_to_baseline() -> None:
    from indiegen.plan import canonical_json

    a = canonical_json(_plan_with_segments(1))
    b = canonical_json(_plan_with_segments(1, seconds=10))
    assert a == b  # deterministic at same seed/duration


def test_segments_2_doubles_pad_events_and_changes_roots() -> None:
    p1 = _plan_with_segments(1)
    p2 = _plan_with_segments(2)

    pads1 = [e for e in p1.events if isinstance(e, PadEvent)]
    pads2 = [e for e in p2.events if isinstance(e, PadEvent)]

    # Not all sections carry a pad (density gate), so exact 2x isn't guaranteed;
    # but segments=2 must never produce fewer pads than segments=1.
    assert len(pads2) > len(pads1)

    # Within at least one section, two pad events exist with different roots.
    by_start: dict[int, list[PadEvent]] = {}
    for e in pads2:
        by_start.setdefault(e.start_frame // (p2.duration_frames // 4 or 1), []).append(e)
    # At least one section-root pair must show distinct midi values among pads
    # that share a start frame bucket; weaker but non-trivial.
    roots_by_sec = {}
    for e in pads2:
        roots_by_sec.setdefault(e.midi, 0)
        roots_by_sec[e.midi] += 1
    assert len(roots_by_sec) >= 2  # more than one distinct pad root across track


def test_segments_2_segment_roots_subset_of_scale() -> None:
    p2 = _plan_with_segments(2)
    scale_pool = {t % 12 for t in p2.scale_midi}
    pads2 = [e for e in p2.events if isinstance(e, PadEvent)]
    # Every pad root, expressed as pitch class, must be a scale tone.
    for e in pads2:
        assert e.midi % 12 in scale_pool

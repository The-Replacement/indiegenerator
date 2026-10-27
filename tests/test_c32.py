"""c32: the four-bar section floor, the density gate, and the wall's crest.

Three properties, each of which was broken and each of which is now pinned:

1. A pulsed section is never shorter than MINIMUM_SECTION_BARS. The floor is
   what the material needs: a section below it cannot carry the motif's
   recurrence, so the delivered timbre flattens (gate 6) and the section stops
   being distinguishable as a novelty peak (gate 7). The count of sections
   gives way instead.

2. A drum voice never sounds in a section whose density is below its
   min_density. The gate belongs to the hit's frame, not to the bar it was
   laid out in: a bar straddling a section boundary used to carry the denser
   section's material into the sparser one, which inverted dub-electronic's
   energy arc at 45 s and 90 s (gate 5) and smeared indie-noise's boundary
   (gate 7).

3. The wall's pulse count follows the section's density, so the crest the
   lane's preset has always claimed is a thing the arrangement can express.
"""

from __future__ import annotations

import pytest

from indiegen.compose import compose, director
from indiegen.compose.planner import MINIMUM_SECTION_BARS
from indiegen.compose.techniques.t6_drums import _pulses
from indiegen.config import BassCard, HatCard, KickCard, SnareCard, load_preset
from indiegen.plan import SAMPLE_RATE, HatEvent, Plan, RhythmEvent
from indiegen.render import schedule

SEED = 1042
RATE = SAMPLE_RATE
PULSED_LANES = ("motorik", "kosmische", "dub-electronic", "indie-noise")


def _plan(lane: str, seconds: int) -> Plan:
    return director(compose(load_preset(lane), SEED, seconds * RATE))


@pytest.mark.parametrize("lane", PULSED_LANES)
@pytest.mark.parametrize("seconds", [45, 60, 90, 120, 240])
def test_every_pulsed_section_reaches_the_four_bar_floor(lane: str, seconds: int) -> None:
    """The floor holds at every duration, not only the long ones."""
    plan = _plan(lane, seconds)
    frames_per_bar = plan.frames_per_beat * plan.meter_numerator
    for section in plan.sections:
        length = section.end_frame - section.start_frame
        # The last section carries the remainder, so it is the one that may
        # fall short of an exact bar count; the floor still applies to it.
        assert length >= MINIMUM_SECTION_BARS * frames_per_bar, (
            f"{lane} {seconds}s: {section.function} is "
            f"{length / frames_per_bar:.2f} bars, below the {MINIMUM_SECTION_BARS}-bar floor"
        )


@pytest.mark.parametrize("lane", PULSED_LANES)
@pytest.mark.parametrize("seconds", [45, 60, 90, 120])
def test_no_drum_hit_lands_in_a_section_that_has_not_reached_it(lane: str, seconds: int) -> None:
    """The density gate belongs to the hit's frame, not to its bar.

    c33 moved the micro-timing drift into the Plan, so a hit now carries two
    frames: the one it plays on and the grid frame the arrangement wrote.
    This gate is about the DENSITY of the section the hit was scheduled into,
    which is the grid frame - the drift can pull a hit up to
    ``micro_timing_frames`` across a section line, and it always could: before
    c33 the plan hid it, because the renderer added the offset after the gate
    had looked. Asking the grid frame keeps the assertion strict instead of
    widening it into a tolerance.
    """
    plan = _plan(lane, seconds)
    presets = load_preset(lane).lanes[0].parameters
    minimums = {
        card.kind: card.pattern.min_density
        for card in presets.techniques
        if isinstance(card, (KickCard, SnareCard, HatCard, BassCard))
    }
    events = schedule(plan)
    for section in plan.sections:
        for voice, minimum in minimums.items():
            if section.density >= minimum:
                continue
            stray = [
                hit
                for event in events
                if event.instrument == voice
                for hit in (event.hits if isinstance(event, RhythmEvent) else ())
                if section.start_frame <= hit.grid_frame() < section.end_frame
            ]
            assert not stray, (
                f"{lane} {seconds}s: {len(stray)} {voice} hit(s) in {section.function} "
                f"at density {section.density}, below its min_density {minimum}"
            )


def test_the_density_scale_is_a_strict_no_op_at_zero() -> None:
    """Every other voice in every other lane depends on this.

    The shipped wall sets the scale to 1000, so the no-op is pinned on a
    card that leaves it at the default - which is every other drum voice in
    the station.
    """
    from indiegen.config import PatternCard

    pattern = PatternCard(
        steps_per_bar=16,
        euclid_k=4,
        euclid_n=16,
        rotation=0,
        condition="always",
        condition_period=1,
        min_density=0,
        ghost_permille=0,
        velocity_millibels=0,
    )
    assert pattern.density_scale_permille == 0
    for density in (0, 20, 55, 80, 100):
        assert _pulses(pattern, density) == pattern.euclid_k


def test_the_wall_crests_because_its_density_follows_the_section() -> None:
    """The lane's own comment claims the crest; this pins that it exists.

    The assertion is on the COMPOSED plan, not the directed one: the crest is
    the composer's density-following, and the Director is allowed to halve a
    section's rhythm afterwards (c39 measured the same seed's deck placing a
    half_time over the plateau, which is a different, legal arrangement).
    """
    plan = compose(load_preset("indie-noise"), SEED, 60 * RATE)
    wall = next(event for event in schedule(plan) if event.instrument == "hat")
    assert isinstance(wall, HatEvent)
    rates: dict[str, float] = {}
    for section in plan.sections:
        seconds = (section.end_frame - section.start_frame) / RATE
        hits = sum(1 for hit in wall.hits if section.start_frame <= hit.frame < section.end_frame)
        rates[section.function] = hits / seconds
    # The build is density 55 and the plateau 80: the crest is the plateau
    # playing the wall denser than the build, which a fixed pattern cannot do.
    assert rates["plateau"] > rates["build"], (
        f"the wall does not crest: build {rates['build']:.2f} hits/s, plateau {rates['plateau']:.2f} hits/s"
    )
    # And the sections below the wall's min_density stay silent.
    assert rates["intro"] == 0.0
    assert rates["outro"] == 0.0

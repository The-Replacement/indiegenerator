"""c37: kosmische has a lead, and it enters where BRIEF 5 says.

The lane had no lead voice at all - six sections of drone and arpeggios, 25 % of
the catalogue with no third act (issue #36). The lead is the pad's additive
synth on its own palette, with its own event kind so the section's
instrumentation records that it arrived: that dimension had never moved in this
lane.
"""

from __future__ import annotations

import numpy as np
import pytest

from indiegen.compose import compose, director
from indiegen.config import LeadCard, load_preset
from indiegen.master.chain import master
from indiegen.master.loudness import measure
from indiegen.plan import LeadEvent, Partial, Plan, Rational
from indiegen.render import render_plan
from indiegen.synth.pad import render_pad
from indiegen.validate import run_gates

RATE: int = 44100
SEED: int = 1042
SECONDS: int = 480


@pytest.fixture(scope="module")
def kosmische_plan() -> Plan:
    return director(compose(load_preset("kosmische"), SEED, SECONDS * RATE))


@pytest.fixture(scope="module")
def card() -> LeadCard:
    preset = load_preset("kosmische")
    return next(item for item in preset.lanes[0].parameters.techniques if isinstance(item, LeadCard))


def _leads(plan: Plan) -> list[LeadEvent]:
    return [event for event in plan.events if isinstance(event, LeadEvent)]


def test_the_lead_enters_at_its_declared_section(kosmische_plan: Plan, card: LeadCard) -> None:
    """BRIEF 5: the lead enters at section 3+. Measured, section by section."""
    for section in kosmische_plan.sections:
        plays = "lead" in section.instrumentation
        expected = section.index >= card.entry_section and section.density >= card.min_density
        assert plays == expected, f"section {section.index} ({section.function}, density {section.density})"


def test_the_lead_leaves_when_the_section_is_too_sparse(kosmische_plan: Plan, card: LeadCard) -> None:
    """The outro is below the lead's density floor, so the line exits with it."""
    outro = next(section for section in kosmische_plan.sections if section.function == "outro")
    assert outro.density < card.min_density
    assert "lead" not in outro.instrumentation


def test_the_lead_is_the_detuned_pair_plus_colour(kosmische_plan: Plan, card: LeadCard) -> None:
    """BRIEF 5's "two-oscillator detuned lead": two unison partials, detuned."""
    leads = _leads(kosmische_plan)
    assert leads
    for event in leads:
        assert card.partials.min <= len(event.partials) <= card.partials.max
        first, second = event.partials[0], event.partials[1]
        assert (first.ratio.numerator, first.ratio.denominator) == (1, 1)
        assert (second.ratio.numerator, second.ratio.denominator) == (1, 1)
        for partial in (first, second):
            assert card.detune_min_cents <= partial.detune_cents <= card.detune_max_cents
        for partial in event.partials[2:]:
            assert partial.amplitude_millibels < 0


def test_the_lead_is_a_line_not_a_chord() -> None:
    """One lead per section: it does not restart on every chord segment.

    Read from compose(), not from the Director: a transposed lead is split into
    a head and a tail by the deck, on purpose, so the composed arrangement is
    the one that must carry exactly one lead per entered section.
    """
    plan = compose(load_preset("kosmische"), SEED, SECONDS * RATE)
    entered = [section for section in plan.sections if section.index >= 3 and section.density >= 40]
    leads = _leads(plan)
    assert len(leads) == len(entered)
    for event, section in zip(leads, entered, strict=True):
        assert event.start_frame == section.start_frame
        assert event.duration_frames == section.end_frame - section.start_frame


def test_the_fades_fit_inside_the_section(kosmische_plan: Plan) -> None:
    for event in _leads(kosmische_plan):
        assert event.attack_frames <= event.duration_frames // 4
        assert event.release_frames <= event.duration_frames // 4


def test_a_short_form_has_no_lead() -> None:
    """An interlude has no section 3+ to enter at, so it stays a two-voice piece."""
    for seconds in (45, 60):
        plan = director(compose(load_preset("kosmische"), SEED, seconds * RATE))
        assert _leads(plan) == []


def test_the_lead_is_opt_in_per_lane() -> None:
    """Only kosmische declares it: the other four lanes must be untouched."""
    for lane in ("motorik", "ambient", "dub-electronic", "indie-noise"):
        plan = director(compose(load_preset(lane), SEED, 120 * RATE))
        assert _leads(plan) == [], lane


def test_the_lead_moves_with_the_bed_it_sits_on() -> None:
    """A transposed drone under an untransposed lead would be in two keys.

    The station's deck transposes [pad, drone] up a fourth; c37 adds the lead to
    that list. Measured: 18 of 30 kosmische seeds draw that move, so this is the
    common case, not a corner.
    """
    transposed = 0
    for seed in range(1042, 1072):
        plain = compose(load_preset("kosmische"), seed, SECONDS * RATE)
        directed = director(plain)
        if not any(move.strategy == "transpose_up_fourth" for move in directed.director_log):
            continue
        if not _leads(plain) or not _leads(directed):
            continue
        if [event.midi for event in _leads(plain)] != [event.midi for event in _leads(directed)]:
            transposed += 1
    assert transposed > 0, "no seed moved the lead with the bed"


def test_the_lead_renders_through_the_pad_synth() -> None:
    """The voice is the pad's additive synth: no new DSP, no new dependency."""
    event = LeadEvent(
        kind="lead",
        instrument="lead",
        start_frame=0,
        duration_frames=RATE * 2,
        midi=60,
        pan_permille=0,
        amplitude_millibels=-14000,
        attack_frames=1000,
        release_frames=1000,
        partials=[Partial(ratio=Rational(numerator=1, denominator=1), amplitude_millibels=0, detune_cents=6)],
        lfo_rate=Rational(numerator=1, denominator=20),
        lfo_depth_cents=6,
    )
    audio = render_pad(event, RATE)
    assert audio.shape == (RATE * 2,)
    assert float(np.abs(audio).max()) > 0.0


@pytest.mark.slow
def test_kosmische_still_passes_every_gate_with_its_lead() -> None:
    """The lead adds a sustained voice; the band and the trajectory must hold."""
    plan = director(compose(load_preset("kosmische"), SEED, SECONDS * RATE))
    mix = render_plan(plan)
    pcm = master(plan, mix, 8192)
    assert run_gates(plan, mix, pcm) is None
    measured = measure(pcm, plan.sample_rate)
    assert 4.0 <= measured["loudness_range_lu"] <= 12.0, measured

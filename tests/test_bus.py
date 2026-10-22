"""S4: the mix bus - the trims, the send levels and the kick.

The bus is where the balance of a track is decided, and every level in it
is read: a send declared at -6 dB is a send at -6 dB and not at unity.
"""

from __future__ import annotations

import numpy as np
import pytest

from indiegen.compose import compose, director
from indiegen.config import load_preset
from indiegen.plan import SAMPLE_RATE, BusGain
from indiegen.render import render_plan


def _plan(lane: str = "motorik", seconds: int = 30, seed: int = 1042):
    return director(compose(load_preset(lane), seed, seconds * SAMPLE_RATE))


def test_a_trim_is_applied_to_the_voice_it_names() -> None:
    plan = _plan().model_copy(update={"bus_gains": []})
    trimmed = plan.model_copy(update={"bus_gains": [BusGain(kind="pad", gain_millibels=-600)]})
    plain = render_plan(plan)
    cut = render_plan(trimmed)
    # The pad is the loudest voice in the motorik lane, so the trim shows.
    assert float(np.sqrt(np.mean(cut**2))) < float(np.sqrt(np.mean(plain**2)))


def test_a_trim_of_zero_changes_nothing() -> None:
    plan = _plan().model_copy(update={"bus_gains": []})
    same = plan.model_copy(update={"bus_gains": [BusGain(kind="pad", gain_millibels=0)]})
    assert np.array_equal(render_plan(plan), render_plan(same))


def test_a_trim_of_the_wrong_kind_changes_nothing() -> None:
    plan = _plan().model_copy(update={"bus_gains": []})
    same = plan.model_copy(update={"bus_gains": [BusGain(kind="nothing_like_it", gain_millibels=-600)]})
    assert np.array_equal(render_plan(plan), render_plan(same))


def test_the_reverb_send_level_is_read() -> None:
    """The reverb is fed at the declared level, and its wet comes back at unity."""
    plan = _plan("ambient")
    assert plan.reverb is not None
    assert plan.reverb.send_millibels < 0
    louder = plan.model_copy(
        update={"reverb": plan.reverb.model_copy(update={"send_millibels": 0})},
    )
    quiet = render_plan(plan)
    full = render_plan(louder)
    assert float(np.sqrt(np.mean(full**2))) > float(np.sqrt(np.mean(quiet**2)))


def test_the_delay_send_level_is_read() -> None:
    plan = _plan()
    assert plan.delay_sends
    assert plan.delay_sends[0].send_millibels == 0
    louder = plan.model_copy(
        update={"delay_sends": [plan.delay_sends[0].model_copy(update={"send_millibels": 0})]},
    )
    assert np.array_equal(render_plan(plan), render_plan(louder))


def test_the_kick_is_in_the_mix_of_a_lane_without_a_dub_chain() -> None:
    """The kick is kept apart for the sidechain, and it is still summed."""
    plan = _plan()
    assert plan.dub_chain is None
    kick = [event for event in plan.events if event.kind == "kick"]
    assert kick
    alone = render_plan(plan.model_copy(update={"events": kick}))
    assert float(np.max(np.abs(alone))) > 0.0
    whole = render_plan(plan)
    assert float(np.max(np.abs(whole))) > float(np.max(np.abs(alone)))


def test_the_render_path_imports_nothing_from_compose() -> None:
    import ast
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "src" / "indiegen" / "render.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("indiegen.compose")
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("indiegen.compose")


@pytest.mark.parametrize("lane", ["motorik", "dub-electronic"])
def test_every_lane_with_a_kick_has_one_that_plays(lane: str) -> None:
    plan = _plan(lane)
    kicks = [event for event in plan.events if event.kind == "kick"]
    assert kicks
    assert any(hit.frame >= 0 for event in kicks for hit in event.hits)


def test_the_lanes_without_drums_have_no_kick() -> None:
    plan = _plan("indie-noise")
    assert not [event for event in plan.events if event.kind == "kick"]

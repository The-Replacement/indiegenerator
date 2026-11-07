"""S5: the batch, the catalog, the file check and the install.

The batch's mechanics are what these check: the seeds, the forms, the
refusal of a seed that is already in the library, the catalog's key and its
fields, and the install's order - validate first, then copy.

The batch's own renders are short, and the gates that need a track with a
length are off for them: the gates have their own tests, and a four second
track has no novelty in it to find. The file check and the install use a
real sixty second track, because a file check is exactly the thing that
has to work on a real track.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from indiegen.batch import TrackOutcome, batch, batch_forms, form_slots, render_track
from indiegen.catalog import build_catalog, write_catalog
from indiegen.compose import compose, director
from indiegen.config import FormCard, Preset, load_preset
from indiegen.errors import PlanError
from indiegen.filecheck import check_file
from indiegen.install import install
from indiegen.plan import SAMPLE_RATE

RATE: int = 44100


@pytest.fixture()
def short_preset() -> Preset:
    """A station whose forms are seconds long, so a test batch is quick."""
    preset = copy.deepcopy(load_preset("motorik"))
    station = preset.station.model_copy(
        update={
            "forms": [
                FormCard(form="full", weight=60, duration_range_seconds=[4, 6]),
                FormCard(form="longform", weight=25, duration_range_seconds=[7, 9]),
                FormCard(form="interlude", weight=15, duration_range_seconds=[2, 3]),
            ]
        }
    )
    lane = preset.lanes[0].parameters.model_copy(update={"duration_range_seconds": [2, 900]})
    preset.lanes[0] = preset.lanes[0].model_copy(update={"parameters": lane})
    return preset.model_copy(update={"station": station})


@pytest.fixture()
def no_trajectory_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    """The gates that need a track with a length, off for the short ones."""
    import indiegen.validate as validate

    monkeypatch.setattr(validate, "GATES_IN_FORCE", (1, 3, 8, 10))


@pytest.fixture(scope="session")
def real_track(tmp_path_factory: pytest.TempPathFactory) -> TrackOutcome:
    """A real sixty second track, with its sidecar, rendered once."""
    preset = load_preset("motorik")
    plan = director(compose(preset, 1042, 60 * RATE))
    out = tmp_path_factory.mktemp("track")
    result = render_track(plan, out)
    assert result.failure is None
    assert result.outcome is not None
    return result.outcome


def test_the_form_slots_follow_the_weights() -> None:
    forms = [
        FormCard(form="full", weight=60, duration_range_seconds=[360, 480]),
        FormCard(form="longform", weight=25, duration_range_seconds=[600, 900]),
        FormCard(form="interlude", weight=15, duration_range_seconds=[45, 120]),
    ]
    slots = form_slots(forms)
    assert len(slots) == 100
    assert slots.count("full") == 60
    assert slots.count("longform") == 25
    assert slots.count("interlude") == 15


def test_the_forms_are_spread_over_the_batch() -> None:
    forms = [
        FormCard(form="full", weight=60, duration_range_seconds=[360, 480]),
        FormCard(form="longform", weight=25, duration_range_seconds=[600, 900]),
        FormCard(form="interlude", weight=15, duration_range_seconds=[45, 120]),
    ]
    drawn = batch_forms(forms, 20)
    assert len(drawn) == 20
    assert drawn.count("full") == 12
    assert drawn.count("longform") == 5
    assert drawn.count("interlude") == 3
    # The forms are spread over the seeds, not in blocks.
    assert drawn[0] == "full"
    assert drawn[-1] == "interlude"
    assert "longform" in drawn[10:]


def test_a_batch_renders_the_tracks_and_writes_the_catalog(
    short_preset: Preset, no_trajectory_gates: None, tmp_path: Path
) -> None:
    result = batch(short_preset, 4, 2000, tmp_path)
    assert len(result.tracks) == 4
    assert [track.seed for track in result.tracks] == [2000, 2001, 2002, 2003]
    assert all(track.path.is_file() for track in result.tracks)
    assert all(track.sidecar.is_file() for track in result.tracks)
    catalog = build_catalog(tmp_path)
    assert len(catalog.entries) == 4
    assert catalog.total_bytes > 0


def test_a_batch_refuses_a_seed_that_is_already_in_the_library(
    short_preset: Preset, no_trajectory_gates: None, tmp_path: Path
) -> None:
    batch(short_preset, 2, 2000, tmp_path)
    with pytest.raises(PlanError) as failure:
        batch(short_preset, 2, 2000, tmp_path)
    assert "already in the library" in str(failure.value)


def test_a_batch_needs_at_least_one_track(short_preset: Preset, tmp_path: Path) -> None:
    with pytest.raises(PlanError):
        batch(short_preset, 0, 2000, tmp_path)


def test_the_catalog_is_keyed_by_the_decoded_hash(
    short_preset: Preset, no_trajectory_gates: None, tmp_path: Path
) -> None:
    result = batch(short_preset, 2, 2000, tmp_path)
    catalog = build_catalog(tmp_path)
    for track in result.tracks:
        assert track.pcm_sha256 in catalog.entries
        entry = catalog.entries[track.pcm_sha256]
        assert entry.seed == track.seed
        assert entry.preset == "motorik"
        assert entry.form in {"full", "longform", "interlude"}
        assert entry.duration_seconds > 0
        assert entry.techniques
        assert entry.sections
        assert entry.path.endswith(".flac")


def test_the_catalog_reports_a_hash_duplicate(short_preset: Preset, no_trajectory_gates: None, tmp_path: Path) -> None:
    """Two seeds that produce the same audio share a key, and the catalog says so."""
    result = batch(short_preset, 2, 2000, tmp_path)
    first = result.tracks[0]
    payload = json.loads(first.sidecar.read_text(encoding="utf-8"))
    payload["seed"] = 9999
    clone = tmp_path / "clone.json"
    clone.write_text(json.dumps(payload), encoding="utf-8")
    catalog = build_catalog(tmp_path)
    assert catalog.duplicate_hashes
    assert any(9999 in entry["seeds"] for entry in catalog.duplicate_hashes)
    # A different seed under the same audio is a hash duplicate, not a
    # seed duplicate.
    assert not catalog.duplicate_seeds


def test_the_catalog_reports_a_seed_duplicate(short_preset: Preset, no_trajectory_gates: None, tmp_path: Path) -> None:
    """Two files under one seed are a seed duplicate."""
    result = batch(short_preset, 2, 2000, tmp_path)
    first = result.tracks[0]
    payload = json.loads(first.sidecar.read_text(encoding="utf-8"))
    payload["pcm_sha256"] = "1" * 64
    clone = tmp_path / "clone.json"
    clone.write_text(json.dumps(payload), encoding="utf-8")
    catalog = build_catalog(tmp_path)
    assert catalog.duplicate_seeds
    assert any(entry["seed"] == first.seed for entry in catalog.duplicate_seeds)


def test_the_catalog_is_written_atomically(short_preset: Preset, no_trajectory_gates: None, tmp_path: Path) -> None:
    batch(short_preset, 1, 2000, tmp_path)
    path = write_catalog(tmp_path, build_catalog(tmp_path))
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema"] == "indiegen/catalog/1"
    assert payload["count"] == 1
    assert "tracks" in payload


def test_a_file_checks_against_its_sidecar(real_track: TrackOutcome) -> None:
    check = check_file(real_track.path, with_codec=False)
    assert check.ok
    assert not check.failures


def test_the_sidecar_records_the_shadow_tension_correlation(real_track: TrackOutcome) -> None:
    """AC-5.3: the sidecar shadows the predictor, beside energy and timbre."""
    from indiegen.validate import tension_correlation
    from indiegen.writer import read_pcm

    payload = json.loads(real_track.sidecar.read_text(encoding="utf-8"))
    recorded = payload["measurements"]["tension_shadow_correlation"]
    assert isinstance(recorded, float)
    assert -1.0 <= recorded <= 1.0
    # The recorded number is the direct call on the decoded PCM.
    from indiegen.plan import Plan

    plan = Plan.model_validate(payload["plan"])
    assert recorded == tension_correlation(plan, read_pcm(real_track.path))


def test_the_file_check_ignores_the_shadow_tension_correlation(real_track: TrackOutcome, tmp_path: Path) -> None:
    """AC-5.3: Phase 1 has no recorded gate-14 check, even at -1.0."""
    directory = tmp_path / "out"
    directory.mkdir()
    (directory / real_track.path.name).write_bytes(real_track.path.read_bytes())
    payload = json.loads(real_track.sidecar.read_text(encoding="utf-8"))
    payload["measurements"]["tension_shadow_correlation"] = -1.0
    (directory / real_track.sidecar.name).write_text(json.dumps(payload), encoding="utf-8")
    check = check_file(directory / real_track.path.name, with_codec=False)
    assert check.ok
    assert not [failure for failure in check.failures if failure.gate == 14]


def test_a_file_whose_sidecar_is_missing_is_unverifiable(real_track: TrackOutcome, tmp_path: Path) -> None:
    copy_of = tmp_path / "orphan.flac"
    copy_of.write_bytes(real_track.path.read_bytes())
    check = check_file(copy_of, with_codec=False)
    assert check.skipped
    assert not check.ok
    assert any(failure.gate == 10 for failure in check.failures)


def test_a_file_whose_sidecar_does_not_match_it_fails(real_track: TrackOutcome, tmp_path: Path) -> None:
    directory = tmp_path / "out"
    directory.mkdir()
    flac = directory / real_track.path.name
    flac.write_bytes(real_track.path.read_bytes())
    payload = json.loads(real_track.sidecar.read_text(encoding="utf-8"))
    payload["pcm_sha256"] = "0" * 64
    (directory / real_track.sidecar.name).write_text(json.dumps(payload), encoding="utf-8")
    check = check_file(flac, with_codec=False)
    assert not check.ok
    assert any(failure.gate == 10 for failure in check.failures)


def test_the_install_copies_the_valid_tracks(real_track: TrackOutcome, tmp_path: Path) -> None:
    directory = tmp_path / "out"
    directory.mkdir()
    (directory / real_track.path.name).write_bytes(real_track.path.read_bytes())
    (directory / real_track.sidecar.name).write_bytes(real_track.sidecar.read_bytes())
    target = tmp_path / "installed"
    installed = install(directory, target, with_codec=False)
    assert installed.ok
    assert len(installed.installed) == 1
    for path in installed.installed:
        assert path.is_file()
        assert path.parent == target
        # c36: the sidecar travels with the track, or the catalog cannot read
        # what was installed and reports a successful zero.
        assert path.with_suffix(".json").is_file()


def test_the_install_refuses_a_track_that_failed_the_gates(real_track: TrackOutcome, tmp_path: Path) -> None:
    directory = tmp_path / "out"
    directory.mkdir()
    (directory / real_track.path.name).write_bytes(real_track.path.read_bytes())
    payload = json.loads(real_track.sidecar.read_text(encoding="utf-8"))
    # The plan's declared range is what the duration gate reads, and the
    # file's own length is outside it now.
    payload["plan"]["duration_range_frames"] = [10, 20]
    (directory / real_track.sidecar.name).write_text(json.dumps(payload), encoding="utf-8")
    installed = install(directory, tmp_path / "installed", with_codec=False)
    assert not installed.ok
    assert installed.refused
    assert not list((tmp_path / "installed").glob("*.flac"))


def test_a_render_that_fails_the_gates_writes_nothing(short_preset: Preset, tmp_path: Path) -> None:
    plan = director(compose(short_preset, 4242, 4 * SAMPLE_RATE))
    result = render_track(plan, tmp_path)
    assert result.failure is not None
    assert result.outcome is None
    assert not list(tmp_path.glob("*.flac"))


def test_the_plan_declares_its_form() -> None:
    preset = load_preset("motorik")
    plan = director(compose(preset, 1042))
    assert plan.form == "full"
    short = director(compose(preset, 1042, 60 * SAMPLE_RATE))
    assert short.form == "interlude"


def test_the_batch_draws_the_form_it_is_given(short_preset: Preset, no_trajectory_gates: None, tmp_path: Path) -> None:
    plan = director(compose(short_preset, 2000, None, "longform"))
    assert plan.form == "longform"
    low, high = short_preset.station.forms[1].duration_range_seconds
    assert low <= plan.duration_frames / SAMPLE_RATE <= high

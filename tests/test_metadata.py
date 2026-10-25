"""AC-18, AC-20, AC-21: the tags and the filename."""

from __future__ import annotations

import re
from typing import Any

from mutagen.flac import FLAC

from indiegen.metadata import build_tags, filename_for, title_slug

FILENAME_PATTERN: re.Pattern[str] = re.compile(r"^[a-z0-9]+_[a-z0-9_]+_s\d+\.flac$")
COMMENT_PATTERN: re.Pattern[str] = re.compile(r"^seed=\d+; preset=[a-z-]+; v[0-9]+$")
DATE_PATTERN: re.Pattern[str] = re.compile(r"^[0-9]{4}$")


def test_the_slug_is_lowercase_ascii() -> None:
    assert title_slug("Low Tide") == "low_tide"
    assert title_slug("Salt & Iron") == "salt_iron"
    assert title_slug("  ...  ") == "untitled"


def test_the_filename_matches_the_contract(reference_plan: Any) -> None:
    name = filename_for(reference_plan)
    assert FILENAME_PATTERN.match(name), name
    assert f"_s{reference_plan.seed}" in name
    assert name.startswith(f"{reference_plan.file_token}_")


def test_the_filename_carries_no_date(reference_plan: Any) -> None:
    assert not re.search(r"(19|20)\d{2}", filename_for(reference_plan))


def test_the_tags_are_well_formed(reference_plan: Any) -> None:
    tags = build_tags(reference_plan)
    assert set(tags) == {"TITLE", "ARTIST", "ALBUM", "DATE", "GENRE", "COMMENT", "TRACKNUMBER"}
    assert tags["TITLE"]
    assert DATE_PATTERN.match(tags["DATE"])
    assert tags["GENRE"] == f"{reference_plan.lane} generative"
    assert COMMENT_PATTERN.match(tags["COMMENT"])
    assert int(tags["TRACKNUMBER"]) >= 1


def test_the_artist_and_album_come_from_the_lane(reference_plan: Any) -> None:
    tags = build_tags(reference_plan)
    assert tags["ARTIST"] == reference_plan.alias
    assert tags["ALBUM"] == reference_plan.album


def test_the_written_file_carries_the_tags(rendered: dict[str, Any]) -> None:
    flac = FLAC(rendered["flac"])  # type: ignore[no-untyped-call]  # mutagen ships untyped stubs
    # mutagen's FLAC is dict-like, not a dict: the attribute is the interface.
    keys = {key.lower() for key in flac.keys()}  # noqa: SIM118
    assert {"title", "artist", "album", "date", "genre", "comment", "tracknumber"} <= keys
    assert flac["artist"] == [reference_alias(rendered)]
    assert DATE_PATTERN.match(flac["date"][0])
    assert COMMENT_PATTERN.match(flac["comment"][0])


def reference_alias(rendered: dict[str, Any]) -> str:
    """The artist tag of the rendered file."""
    flac = FLAC(rendered["flac"])  # type: ignore[no-untyped-call]  # mutagen ships untyped stubs
    artist: list[str] = flac["artist"]
    return artist[0]

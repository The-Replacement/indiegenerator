"""Tags, the deterministic title and the filename.

The seed is the identity: the filename carries the seed and never today's
date. ``DATE`` is the only wall clock in the program and it is read here, at
tag write time, where it cannot leak into a plan, a hash or a filename.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from mutagen.flac import FLAC

from indiegen.plan import Plan

_CONTROL_CHARS: re.Pattern[str] = re.compile(r"[\x00-\x1f\x7f]")

TITLE_SLUG_PATTERN: re.Pattern[str] = re.compile(r"[^a-z0-9]+")
DATE_PATTERN: re.Pattern[str] = re.compile(r"^[0-9]{4}$")


def title_slug(title: str) -> str:
    """A lowercase ASCII slug of the title."""
    slug = TITLE_SLUG_PATTERN.sub("_", title.lower()).strip("_")
    return slug or "untitled"


def filename_for(plan: Plan) -> str:
    """The output filename: lane token, slug and seed. No date, ever.

    Both components are slugged: ``file_token`` and ``title`` reach a ``Plan``
    from preset YAML and from ``--from-plan`` JSON, and an unsanitised token is
    an arbitrary path (``Path("/out/.tmp") / "/etc/x"`` is ``/etc/x``). The
    filename is a name, never a path.
    """
    token = title_slug(plan.file_token)
    return f"{token}_{title_slug(plan.title)}_s{plan.seed}.flac"


def _clean_tag(value: str) -> str:
    """Strip control characters that could confuse downstream tag readers."""
    return _CONTROL_CHARS.sub("", value)


def build_tags(plan: Plan) -> dict[str, str]:
    """The seven tags of the output contract."""
    return {
        "TITLE": _clean_tag(plan.title),
        "ARTIST": _clean_tag(plan.alias),
        "ALBUM": _clean_tag(plan.album),
        "DATE": str(datetime.now(tz=UTC).year),
        "GENRE": _clean_tag(f"{plan.lane} generative"),
        "COMMENT": _clean_tag(f"seed={plan.seed}; preset={plan.preset}; v{plan.format_version}"),
        "TRACKNUMBER": str(plan.track_number),
    }


def apply_tags(path: Path, tags: dict[str, str]) -> None:
    """Write the tags into a FLAC file, in place."""
    flac = FLAC(path)  # type: ignore[no-untyped-call]  # mutagen ships untyped stubs
    for key, value in tags.items():
        flac[key] = [value]
    flac.save()

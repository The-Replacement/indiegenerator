"""The install: validate, then copy, atomically, into the watched directory.

Liquidsoap is watching the target: a half written file would be played. So
every track is validated first, and the ones that failed the gates are not
copied at all, and the ones that are copied land through the same temp
file, fsync and atomic rename the writer uses.

Nothing here starts or restarts the radio. The radio is a service that
somebody else owns, and a generator that reaches for it is a generator that
can take a station down.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from indiegen.filecheck import FileCheck, check_file
from indiegen.writer import publish_atomically, staging_dir


@dataclass
class InstallResult:
    """What the install did."""

    installed: list[Path] = field(default_factory=list)
    refused: list[tuple[Path, str]] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Did every track make it in?"""
        return not self.refused


def _copy_atomic(source: Path, target_dir: Path) -> Path:
    """Copy a file into a watched directory, atomically."""
    target = target_dir / source.name
    temp_path = staging_dir(target_dir) / source.name
    try:
        shutil.copyfile(source, temp_path, follow_symlinks=False)
        publish_atomically(temp_path, target)
    except OSError:
        temp_path.unlink(missing_ok=True)
        raise
    return target


def _copy_track(flac: Path, target_dir: Path) -> Path:
    """Copy a track: the audio and the sidecar that explains it.

    The sidecar is half the artifact, not an ornament. ``check_file`` has
    already refused a track without one (gate 10), so it is here; if it were
    dropped, the target directory would hold audio the catalog cannot read and
    ``catalog`` would quietly report fewer tracks than files (c36).
    """
    installed = _copy_atomic(flac, target_dir)
    _copy_atomic(flac.with_suffix(".json"), target_dir)
    return installed


def install(
    directory: Path,
    target_dir: Path,
    *,
    with_codec: bool = True,
) -> InstallResult:
    """Validate every track of a directory and copy the valid ones."""
    result = InstallResult()
    if not directory.is_dir():
        raise FileNotFoundError(f"{directory} is not a directory")
    for flac in sorted(directory.glob("*.flac")):
        check: FileCheck = check_file(flac, with_codec=with_codec)
        if not check.ok:
            reasons = ", ".join(f"gate {item.gate}: {item.check}" for item in check.failures)
            result.refused.append((flac, reasons))
            continue
        for reason in check.skipped:
            result.skipped.append((flac, reason))
        result.installed.append(_copy_track(flac, target_dir))
    return result

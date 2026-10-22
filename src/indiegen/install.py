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

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from indiegen.filecheck import FileCheck, check_file
from indiegen.writer import TEMP_DIR_NAME, _fsync_dir


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
    target_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = target_dir / TEMP_DIR_NAME
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / source.name
    target = target_dir / source.name
    try:
        shutil.copyfile(source, temp_path)
        with open(temp_path, "rb") as handle:
            os.fsync(handle.fileno())
        _fsync_dir(temp_dir)
        os.replace(temp_path, target)
        _fsync_dir(target_dir)
    except OSError:
        temp_path.unlink(missing_ok=True)
        raise
    return target


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
        result.installed.append(_copy_atomic(flac, target_dir))
    return result

"""Checking a track that is already on disk.

A track is a file and its sidecar: the sidecar carries the plan, the plan
hash, the PCM hash and the measurements. The two trajectory gates measure
the pre-master mix, and the mix is not on disk - the dither is a +-1 LSB of
white noise over the whole spectrum and it drags a measured spectral
centroid from 1308 Hz to 5952 Hz - so those two are answered by the numbers
the render recorded.

The codec gate and the ebur128 cross-check need ffmpeg, which is a tool on
this machine and not a runtime dependency of the generator: when it is not
there, those two are reported as skipped rather than passed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from indiegen.catalog import read_sidecar
from indiegen.errors import PlanError
from indiegen.master.codec import CodecError, ebur128, mp3_roundtrip
from indiegen.master.loudness import integrated_lufs
from indiegen.plan import Plan
from indiegen.validate import (
    ENERGY_CORRELATION_LIMIT,
    STATIC_CENTROID_LIMIT,
    TENSION_CORRELATION_LIMIT,
    TIMBRE_CORRELATION_LIMIT,
    GateResult,
    check_gate_1,
    check_gate_2_pcm,
    check_gate_3,
    check_gate_4,
    check_gate_7,
    check_gate_8,
    check_gate_9,
    check_gate_10,
    check_gate_11,
    check_gate_12,
    check_gate_13,
    energy_correlation_ok,
    failure,
    tension_ok,
    timbre_ok,
)
from indiegen.writer import pcm_sha256, read_pcm


@dataclass
class FileCheck:
    """What checking one file found."""

    path: Path
    failures: list[GateResult] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Did the file pass every gate it could be checked against?"""
        return not self.failures


def check_file(path: Path, *, with_codec: bool = True) -> FileCheck:
    """Run the gates a file on disk can answer."""
    check = FileCheck(path=path)
    sidecar_path = path.with_suffix(".json")
    payload = read_sidecar(sidecar_path)
    if payload is None:
        # A file with no sidecar cannot be matched to a plan, and a file
        # that cannot be matched is not a file that can be installed. A
        # sidecar that exists but will not read is a different story: the
        # operator has to fix that file, not go looking for it.
        if sidecar_path.is_file():
            reason = f"the sidecar of {path.name} is not a readable sidecar"
        else:
            reason = f"there is no sidecar next to {path.name}"
        check.failures.append(failure(10, 0.0, 1.0, reason))
        check.skipped.append(f"{reason}: the plan's gates cannot be checked")
        return check
    plan_payload = payload.get("plan")
    if not isinstance(plan_payload, dict):
        check.failures.append(failure(10, 0.0, 1.0, f"the sidecar of {path.name} carries no plan"))
        check.skipped.append(f"the sidecar of {path.name} carries no plan")
        return check
    try:
        plan = Plan.model_validate(plan_payload)
    except ValueError, PlanError:
        check.failures.append(failure(10, 0.0, 1.0, f"the sidecar of {path.name} does not validate as a plan"))
        check.skipped.append(f"the sidecar of {path.name} does not validate as a plan")
        return check

    pcm = read_pcm(path)
    check.failures.extend(check_gate_1(pcm, plan.sample_rate))
    check.failures.extend(_check_gate_2_file(pcm))
    check.failures.extend(check_gate_3(plan))
    check.failures.extend(check_gate_4(plan, pcm))
    check.failures.extend(_check_gate_5_recorded(payload))
    check.failures.extend(_check_gate_6_recorded(payload))
    check.failures.extend(_check_gate_14_recorded(payload))
    check.failures.extend(check_gate_7(plan, pcm, plan.sample_rate))
    check.failures.extend(check_gate_8(pcm, plan.lane, plan.sample_rate))
    check.failures.extend(check_gate_9(pcm, plan.sample_rate))
    check.failures.extend(check_gate_10(str(payload.get("pcm_sha256", "")), pcm_sha256(pcm)))
    check.failures.extend(check_gate_13(plan))

    if with_codec:
        try:
            measured = ebur128(path)
            check.failures.extend(
                check_gate_11(
                    integrated_lufs(pcm.astype(np.float64) / 32768.0, plan.sample_rate),
                    measured["integrated_lufs"],
                )
            )
            comparison = mp3_roundtrip(path)
            check.failures.extend(
                check_gate_12(
                    comparison.lufs_before,
                    comparison.lufs_after,
                    comparison.clipped,
                    comparison.correlation,
                )
            )
        except CodecError as exc:
            check.skipped.append(str(exc))
    else:
        check.skipped.append("the codec gates were not run")
    return check


def _check_gate_2_file(pcm: np.ndarray) -> list[GateResult]:
    """Gate 2 as a file can answer it: the DC offset and the rails.

    The non-finite half of gate 2 is about the mix, and a file of int16
    cannot hold a NaN. The PCM half is shared with ``validate.check_gate_2``.
    """
    return check_gate_2_pcm(pcm)


def _recorded(payload: dict[str, Any]) -> dict[str, Any]:
    measurements = payload.get("measurements")
    return measurements if isinstance(measurements, dict) else {}


def _check_gate_5_recorded(payload: dict[str, Any]) -> list[GateResult]:
    """Gate 5, answered by the number the render recorded."""
    value = _recorded(payload).get("energy_correlation")
    if value is None or energy_correlation_ok(float(value)):
        return []
    return [
        failure(
            gate=5,
            measured=float(value),
            limit=ENERGY_CORRELATION_LIMIT,
            check="energy trajectory correlation",
        )
    ]


def _check_gate_14_recorded(payload: dict[str, Any]) -> list[GateResult]:
    """Gate 14, answered by the number the render recorded.

    The sidecar field is still called ``tension_shadow_correlation``: the
    shadow name is retained for sidecar compatibility, and old sidecars
    carry the same key with the same meaning (the measured Pearson). Like
    gate 5, a sidecar that carries no such number is exempt, not failed.
    """
    value = _recorded(payload).get("tension_shadow_correlation")
    if value is None or tension_ok(float(value)):
        return []
    return [
        failure(
            gate=14,
            measured=float(value),
            limit=TENSION_CORRELATION_LIMIT,
            check="tension trajectory correlation",
        )
    ]


def _check_gate_6_recorded(payload: dict[str, Any]) -> list[GateResult]:
    """Gate 6, answered by the number the render recorded."""
    measurements = _recorded(payload)
    value = measurements.get("timbre_correlation")
    if value is None:
        return []
    static = bool(measurements.get("timbre_static"))
    if timbre_ok(float(value), static):
        return []
    limit = STATIC_CENTROID_LIMIT if static else TIMBRE_CORRELATION_LIMIT
    check = "timbre variance against a static plan" if static else "timbre trajectory correlation"
    return [
        failure(
            gate=6,
            measured=float(value),
            limit=limit,
            check=check,
        )
    ]

"""Library-relative outlier flag for candidate tracks (issue #16 reframe).

No models, no weights, no network: the "embedding" is the repo-native
measurement vector every sidecar already carries, and the reference is the
station's own catalog. A track far from the library distribution is flagged
for human rejection before ears are spent. Triage reports; it never fails.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.stats import chi2

from indiegen.catalog import CATALOG_NAME, read_sidecar

FEATURES: tuple[str, ...] = (
    "loudness_range_lu",
    "timbre_correlation",
    "stereo_correlation",
    "energy_correlation",
    "n_sections",
)

# Chi-square 0.99 cutoff is policy: a track further out than 99% of a
# Gaussian library is worth a human look. Computed, not magic.
DEFAULT_THRESHOLD_P = 0.99


@dataclass
class TriagedTrack:
    """One candidate track and its distance from the library."""

    path: str
    distance: float
    flagged: bool
    features: dict[str, float] = field(default_factory=dict)


@dataclass
class TriageReport:
    """The library distribution and every candidate's distance from it."""

    mean: list[float]
    skipped: list[str] = field(default_factory=list)
    tracks: list[TriagedTrack] = field(default_factory=list)
    method: str = "mahalanobis"


def _features_of(payload: dict[str, object]) -> dict[str, float] | None:
    """The repo-native feature vector of one sidecar, or None if incomplete."""
    measurements = payload.get("measurements")
    plan = payload.get("plan")
    if not isinstance(measurements, dict) or not isinstance(plan, dict):
        return None
    sections = plan.get("sections")
    values: dict[str, float] = {}
    for key in ("loudness_range_lu", "timbre_correlation", "stereo_correlation", "energy_correlation"):
        raw = measurements.get(key)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None
        values[key] = float(raw)
    if not isinstance(sections, list):
        return None
    values["n_sections"] = float(len(sections))
    return values


def _distances(matrix: np.ndarray) -> tuple[np.ndarray, str]:
    """Leave-one-out Mahalanobis distances, or standardized-Euclidean when degenerate.

    Each track is scored against the distribution of all the OTHERS, so one
    degenerate track cannot pull the mean and covariance toward itself and
    mask (in-sample Mahalanobis under-reports exactly the tracks a triage is
    for). Fewer tracks than features (or a constant column) makes the
    covariance singular; then the honest fallback is the diagonal —
    per-feature z-scores — said out loud in the method field.
    """
    n, p = matrix.shape
    if n == 1:
        # No distribution to be far from: a lone track scores zero, unflagged.
        return np.zeros(1), "standardized-euclidean"
    out = np.zeros(n)
    fallback = False
    for i in range(n):
        sub = np.delete(matrix, i, axis=0)
        center = matrix[i] - sub.mean(axis=0)
        precision: np.ndarray | None = None
        if len(sub) > p:
            try:
                precision = np.linalg.inv(np.cov(sub, rowvar=False))
            except np.linalg.LinAlgError:
                precision = None
        if precision is not None:
            out[i] = float(np.sqrt(center @ precision @ center))
        else:
            fallback = True
            variance = sub.var(axis=0)
            variance[variance == 0.0] = 1.0
            out[i] = float(np.sqrt(((center**2) / variance).sum()))
    return out, ("standardized-euclidean" if fallback else "mahalanobis")


def triage(directory: Path, threshold: float | None = None, top: int = 0) -> TriageReport:
    """Score every sidecarred track in a directory against its library."""
    names: list[str] = []
    rows: list[list[float]] = []
    skipped: list[str] = []
    for sidecar in sorted(directory.glob("*.json")):
        if sidecar.name == CATALOG_NAME:
            continue
        payload = read_sidecar(sidecar)
        if payload is None:
            skipped.append(str(sidecar))
            continue
        values = _features_of(payload)
        if values is None:
            skipped.append(str(sidecar))
            continue
        names.append(str(sidecar.with_suffix(".flac")))
        rows.append([values[key] for key in FEATURES])
    if not rows:
        return TriageReport(mean=[], skipped=skipped)
    matrix = np.asarray(rows, dtype=np.float64)
    distances, method = _distances(matrix)
    order = sorted(range(len(names)), key=lambda i: (float(distances[i]), names[i]), reverse=True)
    flagged = set(order[:top]) if top > 0 else set()
    # The chi-square cutoff is on the SQUARED Mahalanobis distance; on the
    # standardized-Euclidean fallback the same units apply by construction.
    limit_sq = threshold * threshold if threshold is not None else None
    default_sq = float(chi2.ppf(DEFAULT_THRESHOLD_P, len(FEATURES)))
    tracks = [
        TriagedTrack(
            path=names[i],
            distance=float(distances[i]),
            flagged=i in flagged or float(distances[i]) ** 2 > (limit_sq if limit_sq is not None else default_sq),
            features=dict(zip(FEATURES, rows[i], strict=True)),
        )
        for i in range(len(names))
    ]
    tracks.sort(key=lambda t: (-t.distance, t.path))
    return TriageReport(mean=[float(v) for v in matrix.mean(axis=0)], skipped=skipped, tracks=tracks, method=method)

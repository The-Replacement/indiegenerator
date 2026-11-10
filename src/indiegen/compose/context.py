"""What a compose-time technique needs to know about the track it is writing for.

It is data, not behaviour: a technique may not import the render path, and it
may not look at a clock.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from indiegen.errors import PlanError


class TechniqueContext(BaseModel):
    """The facts a technique draws against."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    preset: str
    seed: int
    lane: str
    scale_midi: list[int]
    root_midi: int
    sample_rate: int
    duration_frames: int
    frames_per_beat: int
    frames_per_bar: int
    attack_frames: int
    release_frames: int
    section_boundaries: list[int]
    section_densities: list[int]
    section_scales: list[list[int]]
    section_roots: list[int]
    section_functions: list[str]
    tuning_system: int = Field(default=0, ge=0, le=1)
    chord_segments_per_section: int = Field(default=1, ge=1, le=8)
    chromatic_budget_permille: int = Field(default=0, ge=0, le=1000)
    chord_tone_intervals: list[int] = []
    tension_admission_enabled: bool = False
    section_admission_modes: list[str] = []
    bed_instruments: list[str] = []
    section_ic_bands: list[list[int]] = Field(default_factory=list)

    def section_at(self, frame: int) -> int:
        """The section a frame falls in, from the boundaries alone."""
        index = 0
        for position, boundary in enumerate(self.section_boundaries):
            if frame >= boundary:
                index = position
        return index

    def section_index(self, frame: int) -> int:
        """The section a frame falls in, clamped to the declared sections."""
        return min(self.section_at(frame), max(0, len(self.section_densities) - 1))

    def admits(self, section: int, instrument: str, density: int, min_density: int) -> bool:
        """Whether a layer plays in a section under tension admission.

        Off (or no modes declared) falls back to density: the layer plays
        where the node's density reaches its threshold. ``all`` admits
        every instrument, ``density`` is the threshold, ``bed`` admits only
        the bed instruments and falls back to density when the lane declares
        no bed. An unknown mode is a preset bug and raises ``PlanError``.
        """
        density_ok = density >= min_density
        if not self.tension_admission_enabled or not self.section_admission_modes:
            return density_ok
        if not (0 <= section < len(self.section_admission_modes)):
            return density_ok
        mode = self.section_admission_modes[section]
        if mode == "density":
            return density_ok
        if mode == "all":
            return True
        if mode == "bed":
            if not self.bed_instruments:
                return density_ok
            return instrument in self.bed_instruments
        raise PlanError(
            f"unknown tension admission mode {mode!r}",
            preset=self.preset,
            seed=self.seed,
        )

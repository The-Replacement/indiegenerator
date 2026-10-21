"""What a compose-time technique needs to know about the track it is writing for.

It is data, not behaviour: a technique may not import the render path, and it
may not look at a clock.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


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

    def section_index(self, frame: int) -> int:
        """The section a frame falls in."""
        index = 0
        for position, boundary in enumerate(self.section_boundaries):
            if frame >= boundary:
                index = position
        return min(index, max(0, len(self.section_densities) - 1))

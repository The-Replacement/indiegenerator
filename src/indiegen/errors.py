"""Errors are data (BRIEF section 8).

``PlanError``  - bad preset, broken invariant. Raised before any audio exists.
``RenderError`` - NaN, disk failure. Names preset, seed and block index.

Both are plain exceptions so that pydantic propagates them out of a validator
unchanged instead of wrapping them into a ``ValidationError``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


class PlanError(Exception):
    """The plan cannot be built: bad preset, unknown name, broken invariant."""

    def __init__(self, message: str, *, preset: str | None = None, seed: int | None = None) -> None:
        self.base_message = message
        self.preset = preset
        self.seed = seed
        super().__init__(self._render())

    def _render(self) -> str:
        details: list[str] = [self.base_message]
        if self.preset is not None:
            details.append(f"preset={self.preset!r}")
        if self.seed is not None:
            details.append(f"seed={self.seed}")
        return "; ".join(details)

    def with_context(self, *, preset: str | None = None, seed: int | None = None) -> PlanError:
        """The same error, with the context completed."""
        return PlanError(
            self.base_message,
            preset=self.preset if preset is None else preset,
            seed=self.seed if seed is None else seed,
        )


class RenderError(Exception):
    """The render failed: NaN in the signal, or the disk refused the write."""

    def __init__(self, message: str, *, preset: str, seed: int, block_index: int) -> None:
        super().__init__(f"{message}; preset={preset!r}; seed={seed}; block={block_index}")
        self.preset = preset
        self.seed = seed
        self.block_index = block_index


def raise_if_nonfinite(arr: np.ndarray, message: str, *, preset: str, seed: int, block_index: int) -> None:
    """Raise :class:`RenderError` if ``arr`` contains any non-finite values."""

    import numpy as _np

    if not bool(_np.all(_np.isfinite(arr))):
        raise RenderError(message, preset=preset, seed=seed, block_index=block_index)


class DecodeError(Exception):
    """A file on disk could not be read as the audio it claims to be.

    Distinct from :class:`PlanError` (nothing to render) and from
    :class:`RenderError` (the render is ours and it broke): here the input is
    a file somebody else produced, and the operator needs to be told which
    file and why, not shown a library traceback.
    """

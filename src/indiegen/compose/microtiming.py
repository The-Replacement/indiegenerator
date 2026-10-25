"""The drum's micro-timing, decided when the Plan is frozen.

A drummer is never exactly on the grid, and a loop that is exactly on it
sounds like a machine. The drift is drawn here, at compose time, from the
pattern's own 1/f timing stream, and written into the hits: the frame the
renderer plays is the frame the Plan says.

It used to be a render-time decision, and that was a defect (c33). An offset
applied while the track is cut into blocks cannot be block-invariant: a hit
drifts out of the block that owns it, and both blocks refuse it - the one
that has gone by has already stopped at the next hit, and the one that holds
it sees a frame before its start. Measured at 10 of 200 block sizes between
4000 and 4199 frames, each one losing exactly the hit whose frame was a
multiple of the block size. The fix cannot live in the renderer: a hit that
drifts backwards would have to write into audio already written. So the drift
moves into the Plan, where BRIEF 6 puts it anyway - the audio is a pure
function of the Plan.

The stream is the same one the renderer read, so the frames are the ones the
renderer computed: the drift is a representation move, not a change to the
sound.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from indiegen.control import CONTROL_RATE, TIMING_STREAM, control_count, control_slice, pink_state, stream_key
from indiegen.plan import Event, HitBase, RhythmEvent

DRUM_KINDS: frozenset[str] = frozenset({"kick", "snare", "hat", "bass"})
"""The events whose hits are played at single frames, and so can drift."""


def _offset(control: np.ndarray, frame: int, depth: int, sample_rate: int) -> int:
    """The drift, in frames, for one hit.

    The control value is read at the hit's own frame, which is what the
    renderer used to do; the clamp and the rounding are the renderer's too,
    so the same stream gives the same frame.
    """
    index = (frame * CONTROL_RATE) // sample_rate
    value = max(-1.0, min(1.0, float(control[index])))
    return int(round(value * depth))


def _place(
    hits: Sequence[HitBase],
    control: np.ndarray,
    depth: int,
    sample_rate: int,
    duration_frames: int,
) -> list[HitBase]:
    """The hits, moved by the drift and kept in the order the renderer walks.

    ``render_drum_block`` advances a cursor and stops at the first hit past
    the block, so the list has to stay strictly increasing: a hit is pushed
    to one frame past its predecessor rather than allowed to land on it. At
    the depths the lanes declare (9 to 14 frames against a sixteenth note of
    about 1378) the push never fires; it is here because the invariant is
    what the cursor relies on.
    """
    placed: list[HitBase] = []
    previous = -1
    for hit in hits:
        frame = hit.frame + _offset(control, hit.frame, depth, sample_rate)
        frame = max(0, min(frame, duration_frames - 1))
        frame = max(frame, previous + 1)
        previous = frame
        placed.append(
            hit.model_copy(update={"frame": frame, "drift_frames": frame - hit.frame}) if frame != hit.frame else hit
        )
    return placed


def apply_micro_timing(events: list[Event], duration_frames: int, sample_rate: int) -> list[Event]:
    """Move every drum hit by its pattern's micro-timing drift.

    One whole-stream read per pattern, not one per block: the stream is
    cheap and the values are the ones the block-wise read produced, which is
    what keeps the audio unchanged. A pattern that declares no depth is
    returned untouched, so the pass is a strict no-op at
    ``micro_timing_frames = 0``.
    """
    high = control_count(duration_frames, sample_rate)
    out: list[Event] = []
    for event in events:
        if not isinstance(event, RhythmEvent) or event.kind not in DRUM_KINDS or event.micro_timing_frames <= 0:
            out.append(event)
            continue
        if not event.hits:
            out.append(event)
            continue
        control, _ = control_slice(pink_state(), stream_key(event.noise_seed, 2, TIMING_STREAM), 0, high, CONTROL_RATE)
        out.append(
            event.model_copy(
                update={"hits": _place(event.hits, control, event.micro_timing_frames, sample_rate, duration_frames)}
            )
        )
    return out

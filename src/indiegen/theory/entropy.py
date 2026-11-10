"""Entropy / information content over a plan's pitch sequence (IDyOM-lite).

A lightweight, deterministic, dependency-free stand-in for Pearce's IDyOM:
a variable-order n-gram model over pitch classes with backoff and Laplace
smoothing at the unigram level. Used by compose to target a per-section
information-content band and by validate's gate 15 to measure it.

Everything here is a pure function of its inputs: no RNG, no clock, no I/O.
The model is built from a corpus of pitch classes (typically the plan's
motif cell) and a statement is scored against it, so the same plan always
yields the same numbers.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from indiegen.plan import Plan
from collections import defaultdict

MAX_ORDER: int = 4
PITCH_CLASSES: int = 12
# One bit of surprise maps to this many permille. log2(12) ~ 3.585 bits is
# the ceiling for a 12-class alphabet, so 250 permille/bit keeps the scale
# inside 0..1000 with headroom.
PERMILLE_PER_BIT: float = 250.0


def pitch_classes(notes: list[int]) -> list[int]:
    """MIDI notes to pitch classes."""
    return [int(note) % PITCH_CLASSES for note in notes]


def _build_counts(corpus: list[int]) -> dict[int, dict[tuple[int, ...], dict[int, int]]]:
    """counts[order][context_tuple] = {token: count}."""
    counts: dict[int, dict[tuple[int, ...], dict[int, int]]] = {
        o: defaultdict(lambda: defaultdict(int)) for o in range(1, MAX_ORDER + 1)
    }
    n = len(corpus)
    for i in range(n):
        token = corpus[i]
        for order in range(1, MAX_ORDER + 1):
            ctx_len = order - 1
            start = max(0, i - ctx_len)
            ctx = tuple(corpus[start:i])
            counts[order][ctx][token] += 1
    # Convert defaultdicts to plain dicts for stable hashing/iteration.
    out: dict[int, dict[tuple[int, ...], dict[int, int]]] = {}
    for order in range(1, MAX_ORDER + 1):
        out[order] = {ctx: dict(tok_counts) for ctx, tok_counts in counts[order].items()}
    return out


def _context_total(counts_for_ctx: dict[int, int]) -> int:
    return sum(counts_for_ctx.values())


def statement_probability(
    model_counts: dict[int, dict[tuple[int, ...], dict[int, int]]],
    sequence: list[int],
    position: int,
) -> float:
    """Probability of sequence[position] given previous tokens, with backoff."""
    ctx_tokens = [sequence[j] % PITCH_CLASSES for j in range(max(0, position - (MAX_ORDER - 1)), position)]
    # Try highest order first.
    for order in range(MAX_ORDER, 0, -1):
        ctx_len = order - 1
        ctx = tuple(ctx_tokens[-ctx_len:]) if ctx_len > 0 else ()
        bucket = model_counts.get(order, {}).get(ctx)
        if bucket is not None and bucket.get(sequence[position] % PITCH_CLASSES, 0) > 0:
            total = _context_total(bucket)
            if total > 0:
                return bucket[sequence[position] % PITCH_CLASSES] / total
    # Unigram Laplace fallback.
    unigram_bucket = model_counts.get(1, {}).get((), {})
    total_unigram = sum(unigram_bucket.values())
    token = sequence[position] % PITCH_CLASSES
    return (unigram_bucket.get(token, 0) + 1) / (total_unigram + PITCH_CLASSES)


def statement_ic_permille(notes: list[int], corpus_notes: list[int] | None = None) -> int:
    """Information content of a statement in permille (0..1000).

    If corpus_notes is None, the statement is scored against itself (degenerate
    but defined). Callers should pass the plan's motif cell as corpus.
    """
    if not notes:
        return 0
    seq = [int(n) for n in notes]
    pcs = pitch_classes(seq)
    corpus = corpus_notes if corpus_notes is not None else seq
    corpus_pcs = pitch_classes(corpus)
    if not corpus_pcs:
        # No model: uniform -> max surprise per note.
        return 1000
    model_counts = _build_counts(corpus_pcs)
    total_ic = 0.0
    for i in range(len(pcs)):
        # Build the in-statement context from previous notes of THIS statement.
        prior = pcs[:i]
        # Temporarily prepend prior to a working copy for context lookup.
        # We score token pcs[i] with context = prior (within statement), but
        # counts come from the corpus model. Reuse statement_probability by
        # constructing a sequence where position i has context prior.
        working = prior + [seq[i]]
        p = statement_probability(model_counts, working, len(working) - 1)
        if p <= 0.0:
            p = 1.0 / PITCH_CLASSES
        total_ic += -math.log2(p)
    mean_ic = total_ic / len(pcs)
    permille = int(round(mean_ic * PERMILLE_PER_BIT))
    if permille < 0:
        permille = 0
    if permille > 1000:
        permille = 1000
    return permille


def section_ic_permille(plan: Plan, section_index: int) -> int:
    """Mean IC of motif statements whose start_frame falls in the section.

    Pure function of the Plan. Builds the model from plan.motif (the base
    cell), so compose and validate agree.
    """
    appearances = [a for a in getattr(plan, "motif_appearances", []) if a.section_index == section_index]
    if not appearances:
        return 0
    corpus_midis = [int(item.midi) for item in getattr(plan.motif, "notes", []) if hasattr(item, "midi")]
    if not corpus_midis:
        # Fallback: use all statement notes as corpus.
        corpus_midis = [n for a in appearances for n in a.notes]
    values = [statement_ic_permille(list(a.notes), corpus_midis) for a in appearances]
    if not values:
        return 0
    return int(round(sum(values) / len(values)))


def band_ok(measured: int, lo: int, hi: int) -> bool:
    """Whether a measured IC (permille) lies inside [lo, hi]."""
    return lo <= measured <= hi

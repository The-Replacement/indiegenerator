"""indiegen - batch, offline, deterministic music generation.

Importing this package must NOT import numpy: the thread caps below are only
effective if they are set before the numerical stack loads its BLAS backend.
Float summation is not associative, so a threaded BLAS changes the PCM hash and
breaks the reproducibility contract (BRIEF section 8).
"""

from __future__ import annotations

import os

os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

__version__ = "0.1.0"

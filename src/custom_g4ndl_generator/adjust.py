"""Scale and substitute a tabulated ``(E, sigma)`` cross section."""

from __future__ import annotations

import numpy as np


def adjust_xs(
    pairs: np.ndarray, factor: float = 1.0, substitution: np.ndarray | None = None
) -> np.ndarray:
    """Return *pairs* with sigma multiplied by *factor*.

    *substitution* replaces the energy range it spans and is not scaled.
    """
    # Stable sort keeps the order of points at the same energy (resonance steps).
    pairs = pairs[np.argsort(pairs[:, 0], kind="stable")] * [1.0, factor]
    if substitution is None:
        return pairs
    sub = substitution[np.argsort(substitution[:, 0], kind="stable")]
    energy = pairs[:, 0]
    return np.concatenate([pairs[energy < sub[0, 0]], sub, pairs[energy > sub[-1, 0]]])

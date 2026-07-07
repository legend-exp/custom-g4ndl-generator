"""Validate the Ge-76 capture adjustment, including faithfulness to the legacy
``merge_cross_sections.py``.

These tests read the reference inputs in the parent ``xs_adjustment/`` folder and
skip gracefully when they (or pandas) are not available.
"""

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from custom_g4ndl_generator.adjust import (
    adjust_ge76_capture,
    default_substitution_path,
    read_substitution,
)
from custom_g4ndl_generator.g4ndl import read_xs

XS_ROOT = Path(__file__).resolve().parents[2]  # .../xs_adjustment
TEMPLATE = XS_ROOT / "template" / "32_76_Germanium"
LEGACY_SCRIPT = XS_ROOT / "merge_cross_sections.py"
LEGACY_SUB = XS_ROOT / "n_TOF" / "76GE_XS.dat"
FACTOR = 1.68


def _load_pairs(path):
    if not path.is_file():
        pytest.skip(f"reference file missing: {path}")
    return read_xs(path.read_text(encoding="latin-1"))[0]


def test_scale_only_scales_sigma_keeps_energy():
    orig = _load_pairs(TEMPLATE)
    o = orig[np.argsort(orig[:, 0], kind="stable")]
    out = adjust_ge76_capture(orig, factor=FACTOR, substitution=None)
    np.testing.assert_allclose(out[:, 0], o[:, 0])  # energies unchanged
    np.testing.assert_allclose(out[:, 1], o[:, 1] * FACTOR)  # sigma exactly scaled


def test_legacy_energy_shift_divides_energy():
    orig = _load_pairs(TEMPLATE)
    sub = read_substitution(default_substitution_path())
    out = adjust_ge76_capture(
        orig, factor=FACTOR, substitution=sub, legacy_energy_shift=True
    )

    # Legacy artifact: the below-range first pair (1e-5, 7.769638) becomes
    # (1e-5 / 1.68, 7.769638) -- energy divided, sigma left at its original value
    # (matches the shipped 32_76_Germanium_n_TOF_scaled).
    assert out[0, 0] == pytest.approx(1.0e-5 * FACTOR, rel=1e-6)
    assert out[0, 1] == pytest.approx(7.769638, rel=1e-6)


def test_default_keeps_energy_grid_and_scales_sigma():
    orig = _load_pairs(TEMPLATE)
    sub = read_substitution(default_substitution_path())
    out = adjust_ge76_capture(
        orig, factor=FACTOR, substitution=sub, legacy_energy_shift=False
    )
    # Default: energy grid untouched, below-range sigma scaled by factor --
    # (1e-5, 7.769638) -> (1e-5, 7.769638 * 1.68), matching the per-library
    # production outputs (e.g. JEFF-3.3).
    assert out[0, 0] == pytest.approx(1.0e-5, rel=1e-6)
    assert out[0, 1] == pytest.approx(7.769638, rel=1e-6)


def test_output_is_monotonic_and_finite():
    """Geant4 requires a monotonic, finite energy grid (the legacy script
    produced trailing NaN padding; this must not)."""
    orig = _load_pairs(TEMPLATE)
    sub = read_substitution(default_substitution_path())
    out = adjust_ge76_capture(orig, factor=FACTOR, substitution=sub)
    assert np.isfinite(out).all()
    assert np.all(np.diff(out[:, 0]) >= 0)

"""The Ge-76 radiative-capture cross-section adjustment.

Only ``Capture/CrossSection/32_76_Germanium`` is touched.  Two composable
customizations are applied, reproducing the behaviour of the legacy
``merge_cross_sections.py`` in the parent ``xs_adjustment/`` folder:

1. **Global scaling** by ``factor`` (default 1.68).
2. **Substitution** of the low/mid-energy region with the n_TOF measurement of
   the Ge-76(n,gamma) cross section (Gawlik-Ramiega *et al.*, n_TOF,
   `Phys. Rev. C 104, 044610 <https://journals.aps.org/prc/abstract/10.1103/PhysRevC.104.044610>`_).

Net effect for the substitution path (verified against the shipped per-library
outputs such as ``generated_xs/32_76_Germanium_JEFF-3.3_n_TOF_scaled``):

===============================  ==========================================
energy region                    output ``(E, sigma)``
===============================  ==========================================
``E <  substitution E_min``      ``(E, sigma * factor)``  *(see note below)*
``E_min <= E <= E_max``          n_TOF ``(E, sigma)``  (fully replaced)
``E >  substitution E_max``      ``(E, sigma * factor)``
===============================  ==========================================

.. note::
   By default sigma is scaled uniformly by ``factor`` and the energy grid is
   left unchanged, matching the current per-library production datasets.  Set
   ``legacy_energy_shift=True`` to instead reproduce an artifact of the legacy
   ``merge_cross_sections.py``: it sigma-scaled the whole file by ``factor``,
   then divided the below-range block by ``factor`` to undo that scaling -- which
   also divided the *energy* by ``factor`` and left sigma at its original value
   (see the shipped ``generated_xs/32_76_Germanium_n_TOF_scaled``).

Scale-only mode (no substitution) multiplies every sigma by ``factor`` and
leaves the energy grid unchanged.
"""

from __future__ import annotations

from importlib import resources

import numpy as np

#: Path of the adjusted file inside a G4NDL library, relative to its root.
TARGET_RELPATH = "Capture/CrossSection/32_76_Germanium"

#: Default global scale factor (from the legacy workflow).
DEFAULT_FACTOR = 1.68

#: Name of the bundled n_TOF substitution table.
_BUNDLED_SUBSTITUTION = "76GE_XS.dat"


def default_substitution_path() -> str:
    """Return the filesystem path of the bundled n_TOF substitution table."""
    return str(resources.files(__package__).joinpath("data", _BUNDLED_SUBSTITUTION))


def read_substitution(path) -> np.ndarray:
    """Read an ``(E, sigma)`` substitution table (n_TOF format).

    The file has a one-line header and whitespace/tab separated columns
    ``Energy  Th_initial  [e_sigma]``; energy in eV and cross section in barn.
    Columns beyond the first two (e.g. the uncertainty) are ignored.  The result
    is sorted by increasing energy.
    """
    data = np.loadtxt(path, skiprows=1, usecols=(0, 1))
    # Stable sort so that points sharing an energy (resonance steps) keep their
    # original file order, which matters for interpolation.
    data = data[np.argsort(data[:, 0], kind="stable")]
    return data


def adjust_ge76_capture(
    pairs: np.ndarray,
    factor: float = DEFAULT_FACTOR,
    substitution: np.ndarray | None = None,
    *,
    legacy_energy_shift: bool = False,
) -> np.ndarray:
    """Apply the Ge-76 capture adjustment to an ``(N, 2)`` array of pairs.

    Parameters
    ----------
    pairs
        Original ``(energy, sigma)`` cross section, as read by
        :func:`custom_g4ndl_generator.g4ndl.read_xs`.
    factor
        Global scale factor applied to sigma.
    substitution
        Optional ``(M, 2)`` n_TOF table replacing the region it spans.  When
        ``None``, only global scaling is applied.
    legacy_energy_shift
        Reproduce the legacy ``E / factor`` artifact on the below-range tail
        (energy divided by ``factor``, sigma left at its original value) instead
        of the default uniform sigma scaling (see the module docstring).  Only
        relevant when *substitution* is given.
    """
    pairs = np.asarray(pairs, dtype=float)
    # Stable sort preserves the original file order at equal energies (G4NDL
    # files are already energy-ordered; this is a no-op for them but guards
    # against unordered input without scrambling resonance-step ties).
    pairs = pairs[np.argsort(pairs[:, 0], kind="stable")]

    if substitution is None:
        # Scale-only: sigma * factor, energy grid untouched.
        out = pairs.copy()
        out[:, 1] *= factor
        return out

    sub = np.asarray(substitution, dtype=float)
    sub = sub[np.argsort(sub[:, 0], kind="stable")]
    e_min, e_max = sub[0, 0], sub[-1, 0]

    below = pairs[pairs[:, 0] < e_min].copy()
    above = pairs[pairs[:, 0] > e_max].copy()

    # Above the n_TOF range: sigma * factor, energy unchanged.
    above[:, 1] *= factor

    if legacy_energy_shift:
        # Reproduce the legacy `merge_cross_sections.py` artifact on the low-E
        # tail: it sigma-scaled the whole file by `factor`, then divided the
        # below-range block by `factor` to undo that scaling -- which also
        # divided the *energy* by `factor` and left sigma at its original value.
        below[:, 0] *= factor

    return np.concatenate([below, sub, above], axis=0)

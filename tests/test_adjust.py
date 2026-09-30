from pathlib import Path

import numpy as np

from custom_g4ndl_generator.adjust import adjust_xs
from custom_g4ndl_generator.config import read_substitute
from custom_g4ndl_generator.g4ndl import load_target, read_xs

TESTS = Path(__file__).parent
XS = TESTS / "data/mini_lib/TESTLIB/Capture/CrossSection/32_76_Germanium"
NTOF = TESTS.parent / "examples/76GE_XS.yaml"


def test_scale_only():
    pairs, _ = read_xs(load_target(XS))
    result = adjust_xs(pairs, factor=2.0)
    np.testing.assert_allclose(result, pairs * [1.0, 2.0])


def test_substitution():
    pairs, _ = read_xs(load_target(XS))
    sub = read_substitute(NTOF.name, NTOF.parent)
    result = adjust_xs(pairs, factor=1.68, substitution=sub)
    # The table spans 1e-5 eV - 52 keV: it replaces the first 3 test pairs,
    # the 3 pairs above it are scaled.
    np.testing.assert_allclose(result[:-3], sub)
    np.testing.assert_allclose(result[-3:], pairs[-3:] * [1.0, 1.68])
    assert np.all(np.diff(result[:, 0]) >= 0)

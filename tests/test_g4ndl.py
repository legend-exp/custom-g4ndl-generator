"""Round-trip tests for the three G4NDL cross-section header families."""

import zlib

import numpy as np
import pytest

from custom_g4ndl_generator.g4ndl import (
    dump_target,
    is_compressed,
    load_target,
    read_xs,
    write_xs,
)

# One header line, leading-tab tab-separated data (IAEA / Geant4 >= 10.6).
TAB_FAMILY = (
    " \t6071300 \t0 \t3\n"
    " \t1.000000e-05 \t7.769638e+00 \t1.077190e-05 \t7.486084e+00 \t1.154369e-05 \t7.231501e+00\n"
)

# Five-line header, two-space-separated data (Geant4 10.5 bundled).
STRING_FAMILY = (
    "G4NDL\n"
    "ENDF/B-VII.1\n"
    "           102\n"
    "             0\n"
    "             3\n"
    "  1.000000e-05  7.775803e+00  1.031250e-05  7.657082e+00  1.062500e-05  7.543637e+00\n"
)

# Three-line bare header (Geant4 9.6).
BARE_FAMILY = (
    "           102\n"
    "             0\n"
    "             3\n"
    "  1.000000e-05  7.775803e+00  1.031250e-05  7.657082e+00  1.062500e-05  7.543637e+00\n"
)


@pytest.mark.parametrize("text", [TAB_FAMILY, STRING_FAMILY, BARE_FAMILY])
def test_read_parses_three_pairs(text):
    pairs, style = read_xs(text)
    assert pairs.shape == (3, 2)
    assert pairs[0, 0] == pytest.approx(1.0e-5)
    # N in the reconstructed header equals the number of pairs.
    assert str(len(pairs)) in write_xs(pairs, style)


@pytest.mark.parametrize("text", [TAB_FAMILY, STRING_FAMILY, BARE_FAMILY])
def test_roundtrip_preserves_values(text):
    pairs, style = read_xs(text)
    pairs2, _ = read_xs(write_xs(pairs, style))
    np.testing.assert_allclose(pairs, pairs2, rtol=0, atol=0)


def test_write_updates_entry_count():
    pairs, style = read_xs(TAB_FAMILY)
    grown = np.vstack([pairs, [[2.0e-5, 1.0], [3.0e-5, 2.0]]])  # 3 -> 5 pairs
    out = write_xs(grown, style)
    reparsed, _ = read_xs(out)
    assert reparsed.shape == (5, 2)


def test_load_dump_plain_and_compressed(tmp_path):
    plain = tmp_path / "32_76_Germanium"
    dump_target(plain, TAB_FAMILY, compress=False)
    assert not is_compressed(plain)
    assert load_target(plain) == TAB_FAMILY

    comp = tmp_path / "32_76_Germanium.z"
    dump_target(comp, TAB_FAMILY, compress=True)
    assert is_compressed(comp)
    # Really zlib-compressed on disk, and transparently read back.
    assert zlib.decompress(comp.read_bytes()).decode("latin-1") == TAB_FAMILY
    assert load_target(comp) == TAB_FAMILY

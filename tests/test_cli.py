"""End-to-end CLI test on a tiny fake library fixture."""

import tarfile
from pathlib import Path

import numpy as np
import pytest

from custom_g4ndl_generator.adjust import TARGET_RELPATH
from custom_g4ndl_generator.cli import main
from custom_g4ndl_generator.g4ndl import read_xs

MINI_LIB = Path(__file__).resolve().parent / "data" / "mini_lib" / "TESTLIB"


SUPPLEMENTS = ("IsotopeProduction", "JENDL_HE", "ThermalScattering", "Inelastic/Gammas")


def _make_base_library(tmp_path):
    """A minimal but *complete* G4NDL: a Capture/ root plus the four supplements."""
    base = tmp_path / "BASE"
    (base / "Capture" / "CrossSection").mkdir(parents=True)
    (base / "Capture" / "CrossSection" / "1_1_Hydrogen").write_text("h\n")
    for rel in SUPPLEMENTS:
        (base / rel).mkdir(parents=True)
        (base / rel / "marker").write_text(rel + "\n")
    return base


def test_cli_generates_tree_and_tarball(tmp_path):
    out = tmp_path / "out"
    rc = main(
        [
            "--source",
            str(MINI_LIB),
            "--output",
            str(out),
            "--allow-incomplete",
            "-vv",
        ]
    )
    assert rc == 0

    lib = out / "TESTLIB"
    assert (lib / TARGET_RELPATH).is_file()
    assert (out / "TESTLIB.tar.gz").is_file()

    # Sibling files copied through byte-for-byte.
    assert (lib / "README").read_text() == (MINI_LIB / "README").read_text()
    assert (lib / "Elastic" / "CrossSection" / "32_74_Germanium").read_bytes() == (
        MINI_LIB / "Elastic" / "CrossSection" / "32_74_Germanium"
    ).read_bytes()

    # Target file actually changed and grew (n_TOF points inserted).
    src_pairs, _ = read_xs((MINI_LIB / TARGET_RELPATH).read_text())
    out_pairs, _ = read_xs((lib / TARGET_RELPATH).read_text())
    assert len(out_pairs) > len(src_pairs)

    # Default low-E tail: below-range pair left untouched -> (1e-5, 7.0).
    assert out_pairs[0, 0] == pytest.approx(1e-5, rel=1e-6)
    assert out_pairs[0, 1] == pytest.approx(7.0, rel=1e-6)
    # High-E tail scaled by 1.68: last source pair (1e7, 0.1) -> (1e7, 0.168).
    assert out_pairs[-1, 0] == pytest.approx(1e7, rel=1e-6)
    assert out_pairs[-1, 1] == pytest.approx(0.1 * 1.68, rel=1e-6)

    # The tarball unpacks to TESTLIB/.
    with tarfile.open(out / "TESTLIB.tar.gz") as tar:
        assert any(m.name.startswith("TESTLIB/") for m in tar.getmembers())


def test_cli_scale_only_and_rename(tmp_path):
    out = tmp_path / "out"
    rc = main(
        [
            "--source",
            str(MINI_LIB),
            "--output",
            str(out),
            "--no-substitution",
            "--scale",
            "2.0",
            "--rename",
            "MYLIB",
            "--no-tarball",
            "--allow-incomplete",
        ]
    )
    assert rc == 0
    lib = out / "MYLIB"
    assert lib.is_dir()
    assert not (out / "MYLIB.tar.gz").exists()

    src_pairs, _ = read_xs((MINI_LIB / TARGET_RELPATH).read_text())
    out_pairs, _ = read_xs((lib / TARGET_RELPATH).read_text())
    # Scale-only: same count, energies unchanged, sigma x2.
    assert len(out_pairs) == len(src_pairs)
    s = src_pairs[np.argsort(src_pairs[:, 0])]
    np.testing.assert_allclose(out_pairs[:, 0], s[:, 0])
    np.testing.assert_allclose(out_pairs[:, 1], s[:, 1] * 2.0)


def test_cli_missing_target_fails_cleanly(tmp_path):
    # A library directory that lacks the Ge-76 capture file.
    lib = tmp_path / "NOGE"
    (lib / "Capture" / "CrossSection").mkdir(parents=True)
    (lib / "Capture" / "CrossSection" / "1_1_Hydrogen").write_text("x\n")
    out = tmp_path / "out"

    rc = main(["--source", str(lib), "--output", str(out), "--no-tarball"])
    assert rc == 2
    # Aborted before copying anything.
    assert not (out / "NOGE").exists()


def test_cli_refuses_existing_output_without_force(tmp_path):
    out = tmp_path / "out"
    base = [
        "--source",
        str(MINI_LIB),
        "--output",
        str(out),
        "--no-tarball",
        "--allow-incomplete",
    ]
    assert main(base) == 0
    # Second run without --force fails.
    assert main(base) == 1
    # With --force it succeeds.
    assert main(base + ["--force"]) == 0


def test_cli_supplements_missing_folders_from_base(tmp_path):
    base = _make_base_library(tmp_path)
    out = tmp_path / "out"
    rc = main(
        [
            "--source",
            str(MINI_LIB),
            "--output",
            str(out),
            "--base-library",
            str(base),
            "--no-tarball",
        ]
    )
    assert rc == 0
    lib = out / "TESTLIB"
    # The four omitted folders were overlaid from the base library.
    for rel in SUPPLEMENTS:
        assert (lib / rel).is_dir()
        assert (lib / rel / "marker").read_text() == rel + "\n"
    # The source's own data is untouched (target still adjusted).
    assert (lib / TARGET_RELPATH).is_file()


def test_cli_errors_when_incomplete_and_base_lacks_folders(tmp_path):
    out = tmp_path / "out"
    # MINI_LIB as its own base still lacks every supplement -> fail fast (rc 3),
    # before writing any output.
    rc = main(
        [
            "--source",
            str(MINI_LIB),
            "--output",
            str(out),
            "--base-library",
            str(MINI_LIB),
            "--no-tarball",
        ]
    )
    assert rc == 3
    assert not (out / "TESTLIB").exists()


def test_cli_allow_incomplete_writes_partial_library(tmp_path):
    out = tmp_path / "out"
    rc = main(
        [
            "--source",
            str(MINI_LIB),
            "--output",
            str(out),
            "--allow-incomplete",
            "--no-tarball",
        ]
    )
    assert rc == 0
    lib = out / "TESTLIB"
    assert (lib / TARGET_RELPATH).is_file()
    for rel in SUPPLEMENTS:
        assert not (lib / rel).exists()

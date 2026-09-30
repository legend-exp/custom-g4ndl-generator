"""End-to-end CLI tests on a tiny library."""

import tarfile
from pathlib import Path

import numpy as np
import pytest

from custom_g4ndl_generator.cli import SUPPLEMENTS, main
from custom_g4ndl_generator.g4ndl import load_target, read_xs

TESTS = Path(__file__).parent
MINI_LIB = TESTS / "data/mini_lib/TESTLIB"
TARGET_RELPATH = "Capture/CrossSection/32_76_Germanium"
CONFIG = TESTS.parent / "examples/ge76_ntof.yaml"


def _run(out, *extra, config=CONFIG, source=MINI_LIB):
    return main([str(config), "--source", str(source), "--output", str(out), *extra])


def _write_config(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return path


def _pairs(path):
    return read_xs(load_target(path))[0]


def test_cli_generates_tree_and_tarball(tmp_path):
    out = tmp_path / "out"
    assert _run(out, "--allow-incomplete", "--tarball", "-vv") == 0

    lib = out / "TESTLIB"
    assert (lib / TARGET_RELPATH).is_file()
    assert (out / "TESTLIB.tar.gz").is_file()

    # Sibling files copied through byte-for-byte.
    assert (lib / "README").read_text() == (MINI_LIB / "README").read_text()
    assert (lib / "Elastic" / "CrossSection" / "32_74_Germanium").read_bytes() == (
        MINI_LIB / "Elastic" / "CrossSection" / "32_74_Germanium"
    ).read_bytes()

    # Target file actually changed and grew (n_TOF points inserted).
    assert len(_pairs(lib / TARGET_RELPATH)) > len(_pairs(MINI_LIB / TARGET_RELPATH))
    out_pairs = _pairs(lib / TARGET_RELPATH)

    # Low-E end: first point of the table (1/v extrapolation of n_TOF).
    assert out_pairs[0, 0] == pytest.approx(1e-5, rel=1e-6)
    assert out_pairs[0, 1] == pytest.approx(7.82428424, rel=1e-6)
    # High-E tail scaled by 1.68: last source pair (1e7, 0.1) -> (1e7, 0.168).
    assert out_pairs[-1, 0] == pytest.approx(1e7, rel=1e-6)
    assert out_pairs[-1, 1] == pytest.approx(0.1 * 1.68, rel=1e-6)

    # The tarball unpacks to TESTLIB/.
    with tarfile.open(out / "TESTLIB.tar.gz") as tar:
        assert any(m.name.startswith("TESTLIB/") for m in tar.getmembers())


def test_cli_scale_only_and_rename(tmp_path):
    out = tmp_path / "out"
    config = _write_config(
        tmp_path,
        "customization: {Capture: {CrossSection: {32_76_Germanium: {scale: 2.0}}}}\n",
    )
    rc = _run(out, "--rename", "MYLIB", "--allow-incomplete", config=config)
    assert rc == 0
    lib = out / "MYLIB"
    assert lib.is_dir()
    assert not (out / "MYLIB.tar.gz").exists()

    src_pairs = _pairs(MINI_LIB / TARGET_RELPATH)
    np.testing.assert_allclose(_pairs(lib / TARGET_RELPATH), src_pairs * [1.0, 2.0])


def test_cli_missing_target_fails_cleanly(tmp_path):
    # A library without the file named in the config.
    lib = tmp_path / "NOGE"
    (lib / "Capture" / "CrossSection").mkdir(parents=True)
    (lib / "Capture" / "CrossSection" / "1_1_Hydrogen").write_text("x\n")
    out = tmp_path / "out"

    assert _run(out, source=lib) == 2
    # Aborted before copying anything.
    assert not (out / "NOGE").exists()


def test_cli_refuses_existing_output_without_force(tmp_path):
    out = tmp_path / "out"
    assert _run(out, "--allow-incomplete") == 0
    assert _run(out, "--allow-incomplete") == 1
    assert _run(out, "--allow-incomplete", "--force") == 0


def test_cli_supplements_missing_folders_from_base(tmp_path):
    # A complete base library: Capture/ plus the omitted folders.
    base = tmp_path / "BASE"
    (base / "Capture").mkdir(parents=True)
    for rel in SUPPLEMENTS:
        (base / rel).mkdir(parents=True)
        (base / rel / "marker").write_text(rel + "\n")
    out = tmp_path / "out"
    assert _run(out, "--base-library", str(base)) == 0
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
    assert _run(out, "--base-library", str(MINI_LIB)) == 3
    assert not (out / "TESTLIB").exists()


def test_cli_allow_incomplete_writes_partial_library(tmp_path):
    out = tmp_path / "out"
    assert _run(out, "--allow-incomplete") == 0
    lib = out / "TESTLIB"
    assert (lib / TARGET_RELPATH).is_file()
    for rel in SUPPLEMENTS:
        assert not (lib / rel).exists()


def test_cli_overrides_config(tmp_path):
    out = tmp_path / "out"
    config = _write_config(
        tmp_path,
        f"source: /does/not/exist\noutput: {out}\n"
        "allow-incomplete: true\nrename: FROMCONFIG\n"
        "customization: {Capture: {CrossSection: {32_76_Germanium: {scale: 3.0}}}}\n",
    )
    rc = main([str(config), "--source", str(MINI_LIB), "--rename", "FROMCLI"])
    assert rc == 0
    assert (out / "FROMCLI").is_dir()
    assert not (out / "FROMCONFIG").exists()
    assert not (out / "FROMCLI.tar.gz").exists()


def test_cli_inline_substitution(tmp_path):
    out = tmp_path / "out"
    config = _write_config(
        tmp_path,
        "customization:\n  Capture:\n    CrossSection:\n      32_76_Germanium.z:\n"
        "        scale: 2.0\n        substitute: [[1.0e-2, 4.0], [1.0e2, 2.0]]\n",
    )
    assert _run(out, "--allow-incomplete", config=config) == 0
    out_pairs = _pairs(out / "TESTLIB" / TARGET_RELPATH)
    expected = [
        [1e-5, 14.0],
        [1e-4, 12.0],
        [1e-3, 10.0],
        [1e-2, 4.0],
        [1e2, 2.0],
        [1e5, 2.0],
        [1e6, 1.0],
        [1e7, 0.2],
    ]
    np.testing.assert_allclose(out_pairs, expected)


def test_cli_unknown_config_key_fails(tmp_path):
    config = _write_config(tmp_path, "sorce: JEFF-3.3\n")
    with pytest.raises(SystemExit):
        main([str(config), "--output", str(tmp_path)])

import numpy as np
import pytest

from custom_g4ndl_generator.config import load_config, read_substitute


def test_load_config(tmp_path):
    (tmp_path / "sub.yaml").write_text("- [1.0, 10.0]\n- [2.0, 20.0]\n")
    config = tmp_path / "config.yaml"
    config.write_text(
        "source: JEFF-3.3\n"
        "base-library: G4NDL.4.7.1\n"
        "customization:\n"
        "  Capture:\n"
        "    CrossSection:\n"
        "      32_76_Germanium: {scale: 1.68, substitute: sub.yaml}\n"
        "  Elastic:\n"
        "    CrossSection:\n"
        "      32_74_Germanium.z: {substitute: [[5.0, 1.0], [3.0, 2.0]]}\n"
    )
    options, customizations = load_config(config)

    assert options == {"source": "JEFF-3.3", "base_library": "G4NDL.4.7.1"}
    ge76, ge74 = customizations
    assert ge76.relpath == "Capture/CrossSection/32_76_Germanium"
    assert ge76.scale == 1.68
    np.testing.assert_allclose(ge76.substitution, [[1.0, 10.0], [2.0, 20.0]])
    assert ge74.relpath == "Elastic/CrossSection/32_74_Germanium"
    assert ge74.scale == 1.0
    np.testing.assert_allclose(ge74.substitution, [[5.0, 1.0], [3.0, 2.0]])


def test_load_config_bad_key(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        "customization: {Capture: {CrossSection: {32_76_Germanium: {scal: 2}}}}\n"
    )
    with pytest.raises(ValueError):
        load_config(config)


def test_read_substitute_rejects_extra_columns(tmp_path):
    (tmp_path / "sub.yaml").write_text("- [1.0, 10.0]\n- [2.0, 20.0, 0.5]\n")
    with pytest.raises(ValueError, match="entry 1"):
        read_substitute("sub.yaml", tmp_path)
    with pytest.raises(ValueError, match="in-line"):
        read_substitute([[1.0, 10.0, 0.5]], tmp_path)

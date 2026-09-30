import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from custom_g4ndl_generator.cli import main
from custom_g4ndl_generator.g4ndl import load_target, read_xs
from custom_g4ndl_generator.sources import resolve_source

HERE = Path(__file__).parent
XS = "Capture/CrossSection/32_76_Germanium.z"

# Bhike et al., Phys. Lett. B 741 (2015) 150, EXFOR 14469002-14469004:
# 76Ge(n,g) incl. 77Ge isomer. Columns: E (MeV), sigma (mb), total error (mb).
BHIKE = np.array(
    [
        [0.38, 6.68, 0.44],
        [0.86, 2.80, 0.22],
        [1.32, 2.30, 0.17],
        [1.87, 1.75, 0.31],
        [2.77, 1.89, 0.36],
        [3.39, 1.22, 0.22],
        [4.39, 0.88, 0.07],
        [5.33, 0.61, 0.09],
        [6.64, 0.44, 0.08],
        [7.36, 0.37, 0.06],
        [14.81, 0.62, 0.04],
    ]
)

with tempfile.TemporaryDirectory() as tmpdir:
    main(
        [
            str(HERE.parents[1] / "examples/ge76_ntof.yaml"),
            "--source",
            "G4NDL.4.7.1",
            "--output",
            tmpdir,
            "--cache-dir",
            tmpdir,
            "--rename",
            "adjusted",
            "-v",
        ]
    )
    original, _ = read_xs(load_target(resolve_source("G4NDL.4.7.1", tmpdir) / XS))
    adjusted, _ = read_xs(load_target(Path(tmpdir) / "adjusted" / XS))

substituted = adjusted[(adjusted[:, 0] > 0.026) & (adjusted[:, 0] < 56e3)]

plt.plot(original[:, 0], original[:, 1], label="original (G4NDL.4.7.1)")
plt.plot(adjusted[:, 0], adjusted[:, 1], label="adjusted (G4NDL.4.7.1)")
plt.plot(substituted[:, 0], substituted[:, 1], label="substituted (n_TOF)")
plt.errorbar(
    BHIKE[:, 0] * 1e6,
    BHIKE[:, 1] * 1e-3,
    yerr=BHIKE[:, 2] * 1e-3,
    fmt="o",
    color="black",
    markersize=3,
    label="Bhike et al. (2015)",
)
plt.text(1e-4, 1e-4, r"$^{76}$Ge(n,$\gamma$)", size=16, weight="bold")
plt.xlabel("Energy (eV)")
plt.ylabel("Cross Section (barn)")
plt.yscale("log")
plt.xscale("log")
plt.xlim(1e-5, 2e7)
plt.legend()
plt.savefig(HERE / "comparison_plot.png", bbox_inches="tight", dpi=300)

import matplotlib.pyplot as plt
from custom_g4ndl_generator.g4ndl import read_xs, load_target
from custom_g4ndl_generator.cli import main
import tempfile
import os

with tempfile.TemporaryDirectory() as tmpdir:

    argv_adjust = [
        "--source",
        "G4NDL.4.7.1",
        "--output",
        tmpdir.name,
        "--cache-dir",
        tmpdir.name,
        "--rename",
        "G4NDL.4.7.1_adjusted",
        "-v",
    ]

    main(argv_adjust)

    adjusted = read_xs(
        load_target(
            f"{tmpdir.name}/G4NDL.4.7.1_adjusted/Capture/CrossSection/32_76_Germanium.z"
        )
    )
    original = read_xs(
        load_target(
            f"{tmpdir.name}/extracted/G4NDL.4.7.1/G4NDL4.7.1/Capture/CrossSection/32_76_Germanium.z"
        )
    )

    original_data = original[0]
    adjusted_data = adjusted[0]

    plt.plot(original_data[:, 0], original_data[:, 1], label="original (G4NDL.4.7.1)")
    plt.plot(adjusted_data[:, 0], adjusted_data[:, 1], label="adjusted (G4NDL.4.7.1)")
    plt.text(1e-4, 1e-4, r"$^{76}$Ge(n,$\gamma$)", size=16, weight="bold")
    plt.xlabel("Energy (eV)")
    plt.ylabel("Cross Section (barn)")
    plt.yscale("log")
    plt.xscale("log")
    plt.xlim(1e-5, 2e7)
    plt.legend()
    here = os.path.dirname(os.path.abspath(__file__))
    plt.savefig(os.path.join(here, "comparison_plot.png"), bbox_inches="tight", dpi=300)

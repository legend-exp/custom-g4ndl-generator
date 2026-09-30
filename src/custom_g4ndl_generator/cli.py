"""Command-line entry point: ``custom-g4ndl CONFIG [options]``."""

from __future__ import annotations

import argparse
import logging
import shutil
import tarfile
from pathlib import Path

from . import __version__
from .adjust import adjust_xs
from .config import load_config
from .g4ndl import dump_target, load_target, read_xs, write_xs
from .sources import resolve_source

log = logging.getLogger("custom_g4ndl_generator")

# Folders of a full G4NDL that the IAEA-translated libraries (JEFF-3.3,
# ENDF-VIII.0, JENDL-*) omit. IsotopeProduction drives neutron-HP isotope production.
SUPPLEMENTS = ("IsotopeProduction", "JENDL_HE", "ThermalScattering", "Inelastic/Gammas")


def _parse_args(argv: list[str] | None):
    """Return the arguments and the customizations. The command line overrides the config."""
    p = argparse.ArgumentParser(
        prog="custom-g4ndl",
        description="Generate a custom G4NDL neutron-data library. The config file "
        "sets the adjustments. Options given on the command line override the "
        "same options in the config file.",
    )
    p.add_argument(
        "config",
        type=Path,
        help="YAML config file with the 'customization' block and optional "
        "defaults for the options below.",
    )
    p.add_argument(
        "--source",
        help="library source: a local directory, a local .tar.gz archive, an "
        "IAEA library name (e.g. JEFF-3.3, ENDF-VIII.0, JENDL-4.0u), a G4NDL "
        "library name (e.g. G4NDL.4.5, G4NDL.4.7.1, ...), or a URL.",
    )
    p.add_argument("--output", type=Path, help="output folder for the library.")
    p.add_argument(
        "--base-library",
        metavar="SOURCE",
        default="https://cern.ch/geant4-data/datasets/G4NDL.4.7.1.tar.gz",
        help="full G4NDL library (same forms as --source) that fills in the "
        f"folders translated libraries omit ({', '.join(SUPPLEMENTS)}). "
        "Default: %(default)s.",
    )
    p.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="write the library even if the source omits these folders "
        "(Geant4 neutron-HP will not work correctly).",
    )
    p.add_argument(
        "--cache-dir", type=Path, help="directory for downloads and extractions."
    )
    p.add_argument(
        "--rename",
        metavar="NAME",
        help="name of the output library directory (default: source library name).",
    )
    p.add_argument("--tarball", action="store_true", help="also write <name>.tar.gz.")
    p.add_argument("--force", action="store_true", help="overwrite an existing output.")
    p.add_argument(
        "-v", "--verbose", action="count", default=0, help="-v, -vv: more output."
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    args = p.parse_args(argv)
    options, customizations = load_config(args.config)
    unknown = sorted(set(options) - set(vars(args)))
    if unknown:
        p.error(f"unknown option(s) in {args.config}: {', '.join(unknown)}")
    p.set_defaults(**options)
    args = p.parse_args(argv)
    for name in ("source", "output"):
        if getattr(args, name) is None:
            p.error(f"--{name} is not set on the command line or in the config")
    return args, customizations


def main(argv: list[str] | None = None) -> int:
    """Generate the custom library. Return 0 on success."""
    args, customizations = _parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING - 10 * min(args.verbose, 2), format="%(message)s"
    )

    root = resolve_source(args.source, cache_dir=args.cache_dir)
    log.info("library root: %s", root)

    # Check everything before the large copy, so that a failure leaves no partial output.
    targets = []
    for custom in customizations:
        path = root / custom.relpath
        if not path.is_file():
            path = path.with_name(path.name + ".z")
        if not path.is_file():
            log.error("%s[.z] not found in %s", custom.relpath, root)
            return 2
        targets.append(path.relative_to(root))

    out_lib = args.output / (args.rename or root.name)
    if out_lib.exists():
        if not args.force:
            log.error("output %s already exists (use --force to overwrite)", out_lib)
            return 1
        shutil.rmtree(out_lib)

    missing = [rel for rel in SUPPLEMENTS if not (root / rel).is_dir()]
    base_root = None
    if missing and args.allow_incomplete:
        log.warning(
            "%s is missing %s. Writing an INCOMPLETE library (--allow-incomplete). "
            "Geant4 neutron-HP will not work correctly.",
            root.name,
            ", ".join(missing),
        )
    elif missing:
        log.info(
            "%s is missing %s. Take them from %s",
            root.name,
            ", ".join(missing),
            args.base_library,
        )
        try:
            base_root = resolve_source(args.base_library, cache_dir=args.cache_dir)
        except Exception as exc:  # noqa: BLE001
            log.error(
                "%s is missing %s and the base library %s could not be resolved: %s\n"
                "Supply --base-library with a full G4NDL, or pass --allow-incomplete.",
                root.name,
                ", ".join(missing),
                args.base_library,
                exc,
            )
            return 3
        base_missing = [rel for rel in missing if not (base_root / rel).is_dir()]
        if base_missing:
            log.error(
                "base library %s does not have %s.\n"
                "Supply a --base-library that has them, or pass --allow-incomplete.",
                base_root.name,
                ", ".join(base_missing),
            )
            return 3

    log.info("copying library to %s", out_lib)
    shutil.copytree(root, out_lib)
    if base_root is not None:
        for rel in missing:
            shutil.copytree(base_root / rel, out_lib / rel)

    for custom, rel in zip(customizations, targets):
        path = out_lib / rel
        pairs, style = read_xs(load_target(path))
        adjusted = adjust_xs(pairs, custom.scale, custom.substitution)
        log.info(
            "%s: scale %s, %d -> %d points",
            rel,
            custom.scale,
            len(pairs),
            len(adjusted),
        )
        dump_target(path, write_xs(adjusted, style))

    print(f"wrote modified library: {out_lib}")
    if base_root is not None:
        print(f"supplemented folders:   {', '.join(missing)} (from {base_root.name})")
    if args.tarball:
        tar_path = out_lib.with_name(out_lib.name + ".tar.gz")
        # .z files are already compressed. A high gzip level only costs time.
        with tarfile.open(tar_path, "w:gz", compresslevel=6) as tar:
            tar.add(out_lib, arcname=out_lib.name)
        print(f"wrote tarball:          {tar_path}")
    return 0

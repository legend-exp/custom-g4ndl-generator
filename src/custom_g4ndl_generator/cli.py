"""Command-line entry point for generating a custom G4NDL library.

The flow mirrors the four steps described in legend-simflow issue #265:

1. resolve + unpack the source library and load the Ge-76 capture file
   (decompressing it if it is a ``.z`` file),
2. apply the adjustment (global scaling and/or n_TOF substitution),
3. serialize it back to the G4NDL format (re-compressing if the source was),
4. write the full modified library to the output folder (directory + tarball).
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import tarfile
from pathlib import Path

from . import __version__
from .adjust import (
    DEFAULT_FACTOR,
    TARGET_RELPATH,
    adjust_ge76_capture,
    default_substitution_path,
    read_substitution,
)
from .g4ndl import dump_target, is_compressed, load_target, read_xs, write_xs
from .sources import (
    DEFAULT_BASE_G4NDL,
    locate_target,
    missing_supplements,
    resolve_source,
    supplement_library,
)

log = logging.getLogger("custom_g4ndl_generator")


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    p = argparse.ArgumentParser(
        prog="custom-g4ndl",
        description=(
            "Generate a custom G4NDL neutron-data library with an adjusted "
            "Ge-76(n,gamma) capture cross section."
        ),
    )
    p.add_argument(
        "--source",
        required=True,
        help="library source: a local directory, a local .tar.gz archive, an "
        "IAEA library name (e.g. JEFF-3.3, ENDF-VIII.0, JENDL-4.0u), a G4NDL library name (e.g. G4NDL.4.5, G4NDL.4.7.1, ...), or a URL.",
    )
    p.add_argument(
        "--output",
        required=True,
        type=Path,
        help="output folder to write the modified library into.",
    )
    p.add_argument(
        "--scale",
        type=float,
        default=DEFAULT_FACTOR,
        metavar="FACTOR",
        help="global scale factor applied to the capture cross section "
        f"(default: {DEFAULT_FACTOR}).",
    )

    sub = p.add_mutually_exclusive_group()
    sub.add_argument(
        "--substitution",
        type=Path,
        metavar="FILE",
        help="n_TOF (E, sigma) table to substitute (default: the bundled "
        "76GE_XS.dat).",
    )
    sub.add_argument(
        "--no-substitution",
        action="store_true",
        help="apply global scaling only, without n_TOF substitution.",
    )

    p.add_argument(
        "--legacy-energy-shift",
        action="store_true",
        help="reproduce the legacy E*factor artifact on the below-range tail "
        "(energy multiplied by the scale factor, sigma left at its original value) "
        "instead of the default uniform sigma scaling.",
    )
    p.add_argument(
        "--base-library",
        metavar="SOURCE",
        default=None,
        help="full G4NDL library (dir, .tar.gz, IAEA name, or URL) used to fill "
        "in the folders that translated libraries such as JEFF-3.3 omit "
        f"(IsotopeProduction, JENDL_HE, ThermalScattering, Inelastic/Gammas). "
        f"Defaults to a pinned download ({DEFAULT_BASE_G4NDL}).",
    )
    p.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="write the library even if the source omits the supplementary "
        "folders and no base library fills them in (Geant4 neutron-HP, "
        "including IsotopeProduction, will not work correctly).",
    )
    p.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="directory for downloads and extractions.",
    )
    p.add_argument(
        "--rename",
        metavar="NAME",
        default=None,
        help="name for the output library directory (default: same "
        "as the source library).",
    )
    p.add_argument(
        "--no-tarball",
        action="store_true",
        help="do not also produce a .tar.gz of the output library.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="overwrite the output library directory if it exists.",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="increase logging verbosity (-v, -vv).",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _make_tarball(lib_dir: Path) -> Path:
    """Create ``<lib_dir>.tar.gz`` next to *lib_dir* (extracts to its basename)."""
    tar_path = lib_dir.with_name(lib_dir.name + ".tar.gz")
    log.info("writing tarball %s", tar_path)
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(lib_dir, arcname=lib_dir.name)
    return tar_path


def main(argv: list[str] | None = None) -> int:
    """Generate a custom G4NDL library with an adjusted Ge-76 capture cross section."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING - 10 * min(args.verbose, 2),
        format="%(message)s",
    )

    # Step 1: resolve + unpack the source library.
    log.info("resolving source %s", args.source)
    root = resolve_source(args.source, cache_dir=args.cache_dir)
    log.info("library root: %s", root)

    # Validate the target exists in the source *before* copying the whole tree.
    try:
        src_target = locate_target(root, TARGET_RELPATH)
    except FileNotFoundError:
        log.error("%s has no %s; nothing to adjust.", root.name, TARGET_RELPATH)
        return 2

    lib_name = args.rename or root.name
    out_lib = args.output / lib_name

    if out_lib.exists():
        if not args.force:
            log.error("output %s already exists (use --force to overwrite)", out_lib)
            return 1
        shutil.rmtree(out_lib)

    # Translated libraries (JEFF-3.3, ENDF-VIII.0, JENDL-*) omit four folders that
    # a full G4NDL provides; resolve/validate the base before copying so we fail
    # fast without leaving a partial output behind.
    missing = missing_supplements(root)
    base_root = None
    if missing:
        if args.allow_incomplete:
            log.warning(
                "source library %s is missing %s; writing an INCOMPLETE library "
                "(--allow-incomplete). Geant4 neutron-HP, including "
                "IsotopeProduction, will not work correctly until these folders "
                "are overlaid from a full G4NDL.",
                root.name,
                ", ".join(missing),
            )
        else:
            base_source = args.base_library or DEFAULT_BASE_G4NDL
            log.info(
                "source missing %s; supplementing from base %s",
                ", ".join(missing),
                base_source,
            )
            try:
                base_root = resolve_source(base_source, cache_dir=args.cache_dir)
            except Exception as exc:  # noqa: BLE001 (report any resolution failure)
                log.error(
                    "%s is incomplete (missing %s) and the base library %s could "
                    "not be resolved: %s\nSupply --base-library pointing at a full "
                    "G4NDL, or pass --allow-incomplete to write it anyway.",
                    root.name,
                    ", ".join(missing),
                    base_source,
                    exc,
                )
                return 3
            base_missing = [rel for rel in missing if not (base_root / rel).is_dir()]
            if base_missing:
                log.error(
                    "base library %s does not provide %s needed to complete %s.\n"
                    "Supply a --base-library that has them, or pass "
                    "--allow-incomplete.",
                    base_root.name,
                    ", ".join(base_missing),
                    root.name,
                )
                return 3

    # Copy the whole library through; only the target file will be modified.
    args.output.mkdir(parents=True, exist_ok=True)
    log.info("copying library to %s", out_lib)
    shutil.copytree(root, out_lib)

    # Fill in the folders the source omitted from the base library.
    if base_root is not None:
        supplement_library(out_lib, base_root, missing)

    # Step 1 (cont.): load + decompress the target cross-section file.
    target = out_lib / src_target.relative_to(root)
    log.info("adjusting %s", target.relative_to(out_lib))
    pairs, style = read_xs(load_target(target))

    # Step 2: apply the adjustment.
    if args.no_substitution:
        substitution = None
        log.info("scale-only mode (factor=%s)", args.scale)
    else:
        sub_path = args.substitution or default_substitution_path()
        substitution = read_substitution(sub_path)
        log.info(
            "substitution from %s (%d points, factor=%s)",
            sub_path,
            len(substitution),
            args.scale,
        )

    adjusted = adjust_ge76_capture(
        pairs,
        factor=args.scale,
        substitution=substitution,
        legacy_energy_shift=args.legacy_energy_shift,
    )
    log.info("cross section: %d -> %d points", len(pairs), len(adjusted))

    # Step 3: serialize back (re-compressing if the source file was compressed).
    dump_target(target, write_xs(adjusted, style), compress=is_compressed(target))

    # Step 4: package.
    print(f"wrote modified library: {out_lib}")
    if base_root is not None:
        print(f"supplemented folders:   {', '.join(missing)} (from {base_root.name})")
    if not args.no_tarball:
        tar_path = _make_tarball(out_lib)
        print(f"wrote tarball:          {tar_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

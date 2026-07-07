"""Resolve a G4NDL library source to an extracted directory on disk.

A source may be:

* a local directory that already contains an extracted library,
* a local ``.tar.gz`` / ``.tgz`` / ``.tar`` archive,
* an IAEA library *name* (e.g. ``JEFF-3.3``, ``ENDF-VIII.0``, ``JENDL-4.0u``),
  downloaded from ``https://nds.iaea.org/geant4/libraries/<NAME>.tar.gz``,
* a full ``http(s)://`` URL to such an archive.

Downloads and extractions are cached so repeated runs are cheap.
"""

from __future__ import annotations

import logging
import os
import shutil
import tarfile
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

IAEA_BASE = "https://nds.iaea.org/geant4/libraries/"

#: Default base G4NDL library used to fill in the folders that the IAEA-translated
#: libraries (JEFF-3.3, ENDF-VIII.0, JENDL-*) deliberately omit.  These libraries
#: ship only the ENDF-derived reactions and, per their own README, must have four
#: folders overlaid from a full G4NDL distribution before Geant4 can use them.
#: Pinned for reproducibility; override with ``--base-library``.
DEFAULT_BASE_G4NDL = "https://cern.ch/geant4-data/datasets/G4NDL.4.7.1.tar.gz"

#: Folders a full G4NDL provides that the translated libraries do not.  Missing
#: ones are copied in from the base library.  ``IsotopeProduction`` in particular
#: is what drives neutron-HP isotope production (e.g. Ge-77m).
SUPPLEMENT_RELPATHS = (
    "IsotopeProduction",
    "JENDL_HE",
    "ThermalScattering",
    "Inelastic/Gammas",
)

_ARCHIVE_SUFFIXES = (".tar.gz", ".tgz", ".tar")

# The IAEA server returns HTTP 403 for the default urllib User-Agent.
_USER_AGENT = (
    "custom-g4ndl-generator (https://github.com/legend-exp/custom-g4ndl-generator)"
)


def default_cache_dir() -> Path:
    """Return the default download/extraction cache directory."""
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(Path.home(), ".cache")
    return Path(base) / "custom-g4ndl-generator"


def _is_archive(name: str) -> bool:
    return any(name.endswith(s) for s in _ARCHIVE_SUFFIXES)


def _archive_stem(name: str) -> str:
    for suffix in _ARCHIVE_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _download(url: str, dest: Path) -> Path:
    """Download *url* to *dest* (atomically), unless *dest* already exists."""
    if dest.exists():
        log.info("using cached download %s", dest)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    log.info("downloading %s", url)
    # A browser-like User-Agent is required: the IAEA server rejects the
    # default urllib agent with HTTP 403.
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req) as resp:  # noqa: S310 (trusted IAEA/user URL)
        total = int(resp.headers.get("Content-Length", 0))
        read = 0
        with open(tmp, "wb") as out:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                read += len(chunk)
                if total:
                    log.info(
                        "  %5.1f%% (%d/%d MB)",
                        100 * read / total,
                        read >> 20,
                        total >> 20,
                    )
    tmp.replace(dest)
    return dest


def _safe_extract(archive: Path, dest: Path) -> None:
    """Extract *archive* into *dest*, guarding against path traversal."""
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as tar:
        try:
            tar.extractall(dest, filter="data")  # Python >= 3.12
        except TypeError:
            _members_within(tar, dest)
            tar.extractall(dest)


def _members_within(tar: tarfile.TarFile, dest: Path) -> None:
    dest = dest.resolve()
    for member in tar.getmembers():
        target = (dest / member.name).resolve()
        if not str(target).startswith(str(dest)):
            raise RuntimeError(f"unsafe path in archive: {member.name}")


def _find_library_root(path: Path) -> Path:
    """Return the directory that is the library root (contains ``Capture/``)."""
    if (path / "Capture").is_dir():
        return path
    subdirs = [p for p in path.iterdir() if p.is_dir()]
    for sub in subdirs:
        if (sub / "Capture").is_dir():
            return sub
    # Fall back to a lone subdirectory (typical single top-level tar member).
    if len(subdirs) == 1:
        return subdirs[0]
    return path


def resolve_source(source: str, cache_dir: Path | None = None) -> Path:
    """Resolve *source* to the root directory of an extracted G4NDL library."""
    cache_dir = Path(cache_dir) if cache_dir else default_cache_dir()
    src_path = Path(source)

    if src_path.is_dir():
        return _find_library_root(src_path)

    if src_path.is_file() and _is_archive(src_path.name):
        dest = cache_dir / "extracted" / _archive_stem(src_path.name)
        if not dest.exists():
            _safe_extract(src_path, dest)
        return _find_library_root(dest)

    # Otherwise: a URL or an IAEA library name.
    if source.startswith(("http://", "https://")):
        url = source
        name = _archive_stem(Path(source).name)
    else:
        name = source
        url = f"{IAEA_BASE}{name}.tar.gz"

    archive = _download(url, cache_dir / "downloads" / f"{name}.tar.gz")
    dest = cache_dir / "extracted" / name
    if not dest.exists():
        _safe_extract(archive, dest)
    return _find_library_root(dest)


def locate_target(root: Path, relpath: str) -> Path:
    """Locate the target data file under *root*, allowing a ``.z`` variant.

    *relpath* is e.g. ``Capture/CrossSection/32_76_Germanium``.  Returns the
    plain file if present, otherwise the zlib-compressed ``.z`` variant.
    """
    root = Path(root)
    plain = root / relpath
    if plain.is_file():
        return plain
    compressed = root / (relpath + ".z")
    if compressed.is_file():
        return compressed
    # Last resort: search the tree (handles unexpected nesting).
    for candidate in root.rglob(Path(relpath).name + "*"):
        if candidate.name in (Path(relpath).name, Path(relpath).name + ".z"):
            if candidate.parent.name == "CrossSection":
                return candidate
    raise FileNotFoundError(f"{relpath} not found under {root}")


def missing_supplements(root: Path) -> list[str]:
    """Return the :data:`SUPPLEMENT_RELPATHS` that *root* does not provide.

    The IAEA-translated libraries omit these; an empty list means the library
    already carries everything a full G4NDL does.
    """
    root = Path(root)
    return [rel for rel in SUPPLEMENT_RELPATHS if not (root / rel).is_dir()]


def supplement_library(out_lib: Path, base_root: Path, relpaths: list[str]) -> None:
    """Copy each of *relpaths* from *base_root* into *out_lib*.

    Only fills the given (missing) folders; existing library data is never
    overwritten.  Raises :class:`FileNotFoundError` if the base library does not
    provide one of them.
    """
    out_lib = Path(out_lib)
    base_root = Path(base_root)
    for rel in relpaths:
        src = base_root / rel
        if not src.is_dir():
            raise FileNotFoundError(
                f"base library {base_root} has no {rel} to supplement with"
            )
        dst = out_lib / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        log.info("supplementing %s from %s", rel, base_root.name)
        shutil.copytree(src, dst)

"""Resolve a library source (directory, archive, IAEA or G4NDL name, URL) to a directory."""

from __future__ import annotations

import logging
import os
import shutil
import tarfile
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)


def _download(url: str, dest: Path) -> None:
    """Download *url* to *dest*, unless *dest* already exists."""
    if dest.exists():
        log.info("using cached download %s", dest)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    log.info("downloading %s", url)
    # The IAEA server returns HTTP 403 for the default urllib User-Agent.
    agent = (
        "custom-g4ndl-generator (https://github.com/legend-exp/custom-g4ndl-generator)"
    )
    req = urllib.request.Request(url, headers={"User-Agent": agent})
    with urllib.request.urlopen(req) as resp, open(tmp, "wb") as out:  # noqa: S310
        shutil.copyfileobj(resp, out)
    tmp.replace(dest)


def _safe_extract(archive: Path, dest: Path) -> None:
    """Extract *archive* into *dest*. Refuse members that point outside *dest*."""
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as tar:
        try:
            tar.extractall(dest, filter="data")  # Python >= 3.12
        except TypeError:
            for member in tar.getmembers():
                if not (dest / member.name).resolve().is_relative_to(dest.resolve()):
                    msg = f"unsafe path in archive: {member.name}"
                    raise RuntimeError(msg)
            tar.extractall(dest)


def _find_library_root(path: Path) -> Path:
    """Return the directory that contains ``Capture/``, *path* or one level below."""
    if (path / "Capture").is_dir():
        return path
    subdirs = [p for p in path.iterdir() if p.is_dir()]
    for sub in subdirs:
        if (sub / "Capture").is_dir():
            return sub
    # Fall back to a lone subdirectory (typical single top-level tar member).
    return subdirs[0] if len(subdirs) == 1 else path


def resolve_source(source: str, cache_dir: Path | None = None) -> Path:
    """Return the root directory of the library *source*. Download and extract it if needed."""
    if cache_dir is None:
        cache_home = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
        cache_dir = Path(cache_home) / "custom-g4ndl-generator"
    path = Path(source)
    if path.is_dir():
        return _find_library_root(path)

    name = path.name
    for suffix in (".tar.gz", ".tgz", ".tar"):
        name = name.removesuffix(suffix)

    if path.is_file():
        archive = path
    else:
        if source.startswith(("http://", "https://")):
            url = source
        elif "G4" in source:
            url = f"https://cern.ch/geant4-data/datasets/{source}.tar.gz"
        else:
            url = f"https://nds.iaea.org/geant4/libraries/{source}.tar.gz"
        archive = Path(cache_dir) / "downloads" / f"{name}.tar.gz"
        _download(url, archive)

    dest = Path(cache_dir) / "extracted" / name
    if not dest.exists():
        _safe_extract(archive, dest)
    return _find_library_root(dest)

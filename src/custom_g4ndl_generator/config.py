"""Read the YAML config file: command-line options and the ``customization`` tree."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

# The C reader is ~7x faster on large substitution tables.
_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


@dataclass
class Customization:
    """Adjustment of one data file."""

    relpath: str  # e.g. "Capture/CrossSection/32_76_Germanium", without ".z"
    scale: float
    substitution: np.ndarray | None


def read_substitute(value, config_dir: Path) -> np.ndarray:
    """Return the ``[E, sigma]`` pairs, in-line or from a YAML file in *config_dir*."""
    source = "in-line substitute"
    if isinstance(value, str):
        path = Path(config_dir) / value
        source = str(path)
        value = yaml.load(path.read_text(), Loader=_LOADER)
    for i, row in enumerate(value):
        if len(row) != 2:
            msg = (
                f"{source}: entry {i} is {row}, but each entry must be one "
                "[E, sigma] pair (E in eV, sigma in barn). Write the table as a "
                "YAML list:\n  - [0.0257, 0.1543]\n  - [0.0258, 0.1542]"
            )
            raise ValueError(msg)
    return np.asarray(value, dtype=float)


def _walk(node: dict, folders: list[str], config_dir: Path) -> list[Customization]:
    out = []
    for key, value in node.items():
        if not isinstance(value, dict):
            msg = f"unexpected entry {key!r} in customization block"
            raise ValueError(msg)
        if set(value) <= {"scale", "substitute"}:
            sub = value.get("substitute")
            out.append(
                Customization(
                    relpath="/".join([*folders, key.removesuffix(".z")]),
                    scale=float(value.get("scale", 1.0)),
                    substitution=(
                        None if sub is None else read_substitute(sub, config_dir)
                    ),
                )
            )
        else:
            out += _walk(value, [*folders, key], config_dir)
    return out


def load_config(path: Path) -> tuple[dict, list[Customization]]:
    """Return the command-line options (argparse names) and the customizations."""
    raw = yaml.load(path.read_text(), Loader=_LOADER) or {}
    tree = raw.pop("customization", None) or {}
    options = {key.replace("-", "_"): value for key, value in raw.items()}
    return options, _walk(tree, [], path.parent)

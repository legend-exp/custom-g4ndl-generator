"""Read and write G4NDL ``CrossSection`` data files.

The header is the leading lines without floats. Its last integer is N. Then
2*N floats follow, the ``(E, sigma)`` pairs.
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class XSStyle:
    """Layout of a file, so that `write_xs` can reproduce it."""

    header_lines: list[str]
    n_line: int  # index of the header line that holds N
    n_token: str  # N as written in the file
    sep: str  # whitespace before each value on a data line


def read_xs(text: str) -> tuple[np.ndarray, XSStyle]:
    """Return the ``(N, 2)`` pairs and the file layout."""
    lines = text.splitlines()
    # A data token is a float with a "." or an exponent. Header integers are not.
    data = re.compile(r"[+-]?(\d*\.\d*([eE][+-]?\d+)?|\d+[eE][+-]?\d+)")
    first = next(
        (
            i
            for i, line in enumerate(lines)
            if any(data.fullmatch(t) for t in line.split())
        ),
        None,
    )
    if first is None:
        msg = "no tabulated data found in cross-section file"
        raise ValueError(msg)
    header = lines[:first]

    ints = [
        (i, tok)
        for i, line in enumerate(header)
        for tok in line.split()
        if tok.lstrip("+-").isdigit()
    ]
    if not ints:
        msg = "could not find the entry-count integer in the header"
        raise ValueError(msg)
    n_line, n_token = ints[-1]
    n_pairs = int(n_token)

    values = np.array(" ".join(lines[first:]).split(), dtype=float)
    if values.size < 2 * n_pairs:
        msg = (
            f"header declares {n_pairs} pairs but only {values.size} values are present"
        )
        raise ValueError(msg)
    pairs = values[: 2 * n_pairs].reshape(n_pairs, 2)

    sep = " \t" if "\t" in lines[first] else "  "
    return pairs, XSStyle(header, n_line, n_token, sep)


def write_xs(pairs: np.ndarray, style: XSStyle) -> str:
    """Return the file text for *pairs*, with N in the header updated."""
    out = list(style.header_lines)
    head, tail = out[style.n_line].rsplit(style.n_token, 1)
    out[style.n_line] = head + str(len(pairs)).rjust(len(style.n_token)) + tail

    flat = np.asarray(pairs, dtype=float).ravel()
    for start in range(0, flat.size, 6):  # three pairs per line
        out.append(
            style.sep + style.sep.join("%.6e" % v for v in flat[start : start + 6])
        )
    return "\n".join(out) + "\n"


def load_target(path: Path) -> str:
    """Read a data file as text. Decompress it if the name ends in ``.z``."""
    raw = Path(path).read_bytes()
    if str(path).endswith(".z"):
        raw = zlib.decompress(raw)
    return raw.decode("latin-1")


def dump_target(path: Path, text: str) -> None:
    """Write *text* to a data file. Compress it if the name ends in ``.z``."""
    raw = text.encode("latin-1")
    if str(path).endswith(".z"):
        raw = zlib.compress(raw)
    Path(path).write_bytes(raw)

"""Read and write G4NDL ``Capture/CrossSection`` data files.

A G4NDL cross-section file is *not* literal ENDF-6: it is G4NDL's own internal
representation, a small header followed by a flat stream of ``(energy,
cross-section)`` pairs laid out three pairs per line.  Geant4 parses the data
with ``std::istream::operator>>``, so whitespace is not significant to it; this
module nonetheless preserves the input header verbatim and reproduces the
detected delimiter style so the output stays faithful to the source.

Three header families occur in the wild (all reproduced round-trip by this
module):

* **Tab family** (IAEA libraries, Geant4 >= 10.6) -- one header line
  ``\\t<code> \\t0 \\t<Npairs>``, data lines leading-tab and tab-separated.
* **G4-string family** (Geant4 10.5 bundled) -- ``G4NDL`` / ``ENDF/B-VII.1`` /
  ``102`` / ``0`` / ``<Npairs>``, data lines two-leading-spaces, space-separated.
* **Bare family** (Geant4 9.6) -- ``102`` / ``0`` / ``<Npairs>`` then the pairs.

The single robust rule that parses all three: the header is the run of leading
lines that contain no scientific-notation float; the **last integer in the
header is N, the number of pairs**; everything after is ``2*N`` floats.
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field

import numpy as np

# A token that belongs to the numeric data stream: a float written in
# scientific / decimal notation (contains a '.' or an exponent marker).
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")
_INT_RE = re.compile(r"^[+-]?\d+$")


def _is_data_token(tok: str) -> bool:
    """True for a token that looks like tabulated data (has a '.' or exponent)."""
    if not _FLOAT_RE.match(tok):
        return False
    return ("." in tok) or ("e" in tok) or ("E" in tok)


@dataclass
class XSStyle:
    """Captures how a cross-section file was formatted, for faithful rewriting."""

    header_lines: list[str] = field(default_factory=list)
    n_line_idx: int = -1  # index into header_lines of the line holding N
    n_token: str = ""  # original text of the N token (for width-preserving replace)
    data_leading: str = "\t"  # whitespace before the first value on a data line
    data_sep: str = "\t"  # whitespace between values on a data line
    pairs_per_line: int = 3
    float_fmt: str = "%.6e"


def read_xs(text: str) -> tuple[np.ndarray, XSStyle]:
    """Parse a G4NDL cross-section file body into an ``(N, 2)`` array of pairs.

    Returns the ``(energy, sigma)`` array and an :class:`XSStyle` describing the
    original layout so :func:`write_xs` can reproduce it.
    """
    lines = text.splitlines()

    header_lines: list[str] = []
    first_data_line = None
    for i, line in enumerate(lines):
        toks = line.split()
        if toks and any(_is_data_token(t) for t in toks):
            first_data_line = i
            break
        header_lines.append(line)

    if first_data_line is None:
        raise ValueError("no tabulated data found in cross-section file")

    # N = the last integer token appearing in the header lines.
    n_pairs = None
    n_line_idx = -1
    n_token = ""
    for idx, line in enumerate(header_lines):
        for tok in line.split():
            if _INT_RE.match(tok):
                n_pairs = int(tok)
                n_line_idx = idx
                n_token = tok
    if n_pairs is None:
        raise ValueError("could not find the entry-count integer in the header")

    # All remaining tokens are the flat (E, sigma) stream.
    data_toks: list[str] = []
    for line in lines[first_data_line:]:
        data_toks.extend(line.split())
    values = np.array([float(t) for t in data_toks], dtype=float)

    if values.size < 2 * n_pairs:
        raise ValueError(
            f"header declares {n_pairs} pairs ({2 * n_pairs} values) but only "
            f"{values.size} values are present"
        )
    # Trust the header count; ignore any trailing tokens beyond 2*N.
    pairs = values[: 2 * n_pairs].reshape(n_pairs, 2)

    # Detect the data delimiter style from the first data line.
    raw = lines[first_data_line]
    if "\t" in raw:
        data_leading, data_sep = " \t", " \t"
    else:
        data_leading, data_sep = "  ", "  "

    style = XSStyle(
        header_lines=header_lines,
        n_line_idx=n_line_idx,
        n_token=n_token,
        data_leading=data_leading,
        data_sep=data_sep,
    )
    return pairs, style


def write_xs(pairs: np.ndarray, style: XSStyle) -> str:
    """Serialize an ``(N, 2)`` array back to a G4NDL cross-section file body.

    The header is reproduced verbatim except for the entry-count integer, which
    is set to ``len(pairs)`` (right-justified to at least the original width).
    """
    pairs = np.asarray(pairs, dtype=float)
    n_pairs = pairs.shape[0]

    # Rebuild the header, replacing the entry count on its line.
    header_lines = list(style.header_lines)
    if style.n_line_idx >= 0:
        line = header_lines[style.n_line_idx]
        width = max(len(style.n_token), len(str(n_pairs)))
        new_token = str(n_pairs).rjust(width)
        # Replace only the rightmost occurrence of the original N token.
        pos = line.rfind(style.n_token)
        if pos != -1:
            line = line[:pos] + new_token + line[pos + len(style.n_token):]
        header_lines[style.n_line_idx] = line

    out: list[str] = list(header_lines)

    per_row = style.pairs_per_line * 2
    flat = pairs.reshape(-1)
    for start in range(0, flat.size, per_row):
        row = flat[start:start + per_row]
        cells = style.data_sep.join(style.float_fmt % v for v in row)
        out.append(style.data_leading + cells)

    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- #
# Transparent zlib (.z) handling for individual data files
# --------------------------------------------------------------------------- #

def is_compressed(path) -> bool:
    """True if *path* is a zlib-compressed G4NDL data file (``.z`` suffix)."""
    return str(path).endswith(".z")


def load_target(path) -> str:
    """Read a G4NDL data file as text, transparently decompressing ``.z`` files."""
    with open(path, "rb") as fh:
        raw = fh.read()
    if is_compressed(path):
        raw = zlib.decompress(raw)
    return raw.decode("latin-1")


def dump_target(path, text: str, compress: bool) -> None:
    """Write *text* to *path*, zlib-compressing it when *compress* is True."""
    data = text.encode("latin-1")
    if compress:
        data = zlib.compress(data)
    with open(path, "wb") as fh:
        fh.write(data)

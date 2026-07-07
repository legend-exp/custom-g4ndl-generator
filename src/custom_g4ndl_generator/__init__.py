"""Generate custom G4NDL libraries with an adjusted Ge-76(n,gamma) capture cross section.

See :mod:`custom_g4ndl_generator.cli` for the command-line entry point.
"""

__version__ = "0.1.0"

from .adjust import TARGET_RELPATH, adjust_ge76_capture, read_substitution
from .g4ndl import dump_target, load_target, read_xs, write_xs

__all__ = [
    "__version__",
    "TARGET_RELPATH",
    "adjust_ge76_capture",
    "read_substitution",
    "read_xs",
    "write_xs",
    "load_target",
    "dump_target",
]

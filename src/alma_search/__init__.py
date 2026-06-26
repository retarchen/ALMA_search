"""Top-level package for ALMA Search.

This package exposes a small command-line workflow for querying the ALMA
archive near a list of target coordinates. Most users will interact with the
``alma_search`` command, while Python users can import helpers from the
submodules documented in the API reference.
"""

from __future__ import annotations

__all__ = ["main"]
__version__ = "0.1.0"


def main(argv=None):
    """Run the package CLI entry point.

    Parameters
    ----------
    argv : sequence[str] | None, optional
        Optional argument list to parse instead of reading from
        :data:`sys.argv`.

    Returns
    -------
    int
        Process-style exit code returned by :func:`alma_search.cli.main`.
    """
    from .cli import main as cli_main

    return cli_main(argv)

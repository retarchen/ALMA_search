"""ALMA archive search package."""

from __future__ import annotations

__all__ = ["main"]
__version__ = "0.1.0"


def main(argv=None):
    """Lazily dispatch to the package CLI entry point."""
    from .cli import main as cli_main

    return cli_main(argv)

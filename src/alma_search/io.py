"""Input/output helpers exposed from the current implementation."""

from __future__ import annotations

from .search import _load_legacy_module


def read_input_table(*args, **kwargs):
    """Proxy to the current input reader implementation."""
    return _load_legacy_module().read_input_table(*args, **kwargs)


def write_csv(*args, **kwargs):
    """Proxy to the current CSV writer implementation."""
    return _load_legacy_module().write_csv(*args, **kwargs)

__all__ = ["read_input_table", "write_csv"]

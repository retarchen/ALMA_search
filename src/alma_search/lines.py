"""Line catalog exposed from the current implementation."""

from __future__ import annotations

from .search import _load_legacy_module


def load_line_catalog() -> dict[str, float]:
    """Return the current built-in line catalog."""
    return dict(_load_legacy_module().LINE_CATALOG_GHZ)


__all__ = ["load_line_catalog"]

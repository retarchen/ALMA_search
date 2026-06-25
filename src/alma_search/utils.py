"""Selected utility helpers exposed from the current implementation."""

from __future__ import annotations

from .search import _load_legacy_module


def is_blank(*args, **kwargs):
    """Proxy to the blank-value helper."""
    return _load_legacy_module().is_blank(*args, **kwargs)


def normalize_whitespace(*args, **kwargs):
    """Proxy to the whitespace normalizer."""
    return _load_legacy_module().normalize_whitespace(*args, **kwargs)


def parse_ra_dec_to_degrees(*args, **kwargs):
    """Proxy to the coordinate parser."""
    return _load_legacy_module().parse_ra_dec_to_degrees(*args, **kwargs)


def unique_preserve_order(*args, **kwargs):
    """Proxy to the order-preserving unique filter."""
    return _load_legacy_module().unique_preserve_order(*args, **kwargs)

__all__ = [
    "is_blank",
    "normalize_whitespace",
    "parse_ra_dec_to_degrees",
    "unique_preserve_order",
]

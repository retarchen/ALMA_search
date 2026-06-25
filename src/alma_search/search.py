"""Transitional package wrapper around the current ALMA search script.

This keeps the new package layout moving while the original implementation
still lives in the repository root as ``alma_nearby_search.py``.
"""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Sequence


def _legacy_path() -> Path:
    """Return the location of the current top-level implementation."""
    return Path(__file__).resolve().parents[2] / "alma_nearby_search.py"


@lru_cache(maxsize=1)
def _load_legacy_module() -> ModuleType:
    """Load the current top-level implementation from the repository root."""
    legacy_path = _legacy_path()
    if not legacy_path.exists():
        raise ImportError(
            "Could not find alma_nearby_search.py. Move the implementation into "
            "src/alma_search/ before building a distributable package."
        )

    spec = importlib.util.spec_from_file_location("alma_nearby_search_legacy", legacy_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load legacy module from {legacy_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: Sequence[str] | None = None) -> int:
    """Run the current command-line implementation."""
    return _load_legacy_module().main(argv)

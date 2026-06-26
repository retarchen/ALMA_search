"""Sphinx configuration for ALMA Search."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

project = "ALMA Search"
author = "Hongxing Chen, Joyeeta Kundu Aishi"
release = "0.1.2"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
autodoc_typehints = "description"
napoleon_google_docstring = True
napoleon_numpy_docstring = True

"""Line-catalog and observed-species helpers."""

from __future__ import annotations

import re
from typing import Any

from .utils import is_blank, normalize_whitespace

DEFAULT_OBSERVED_SPECIES = "CO"
INTERNAL_OBSERVED_COLUMN = "observed_species_in_alma_flag"

LINE_CATALOG_GHZ: dict[str, float] = {
    "12CO(1-0)": 115.2712018,
    "12CO(2-1)": 230.5380000,
    "12CO(3-2)": 345.7959899,
    "12CO(4-3)": 461.0407682,
    "12CO(6-5)": 691.4730763,
    "12CO(7-6)": 806.6518060,
    "13CO(1-0)": 110.2013543,
    "13CO(2-1)": 220.3986842,
    "13CO(3-2)": 330.5879653,
    "13CO(4-3)": 440.7651668,
    "C18O(1-0)": 109.7821734,
    "C18O(2-1)": 219.5603541,
    "C18O(3-2)": 329.3305525,
    "C18O(4-3)": 439.0887658,
    "C17O(1-0)": 112.3589880,
    "C17O(2-1)": 224.7141990,
    "C17O(3-2)": 337.0611040,
    "HCN(1-0)": 88.6318470,
    "HCN(3-2)": 265.8864340,
    "HCN(4-3)": 354.5054770,
    "HCO+(1-0)": 89.1885250,
    "HCO+(3-2)": 267.5576250,
    "HCO+(4-3)": 356.7342880,
    "HNC(1-0)": 90.6635680,
    "HNC(3-2)": 271.9811420,
    "HNC(4-3)": 362.6303030,
    "N2H+(1-0)": 93.1737000,
    "N2H+(3-2)": 279.5118620,
    "CS(2-1)": 97.9809530,
    "CS(3-2)": 146.9690290,
    "CS(5-4)": 244.9355565,
    "CS(7-6)": 342.8828500,
    "CN(1-0)": 113.4909700,
    "CN(2-1)": 226.8740000,
    "CCH(1-0)": 87.3168980,
    "CCH(3-2)": 262.0042600,
    "[CI](1-0)": 492.1606510,
    "[CI](2-1)": 809.3419700,
    "SiO(2-1)": 86.8469600,
    "SiO(5-4)": 217.1049800,
    "SiO(8-7)": 347.3306310,
    "SO(5_6-4_5)": 219.9494420,
    "SO(6_5-5_4)": 251.8257700,
    "SO2(11_1,11-10_0,10)": 221.9652200,
    "H2CO(3_03-2_02)": 218.2221920,
    "H2CO(3_22-2_21)": 218.4756320,
    "H2CO(3_21-2_20)": 218.7600660,
    "H2CO(2_12-1_11)": 140.8395020,
    "NH2D(1_11-1_01)": 85.9262630,
    "CH3OH(5_0-4_0)": 241.7914310,
    "CH3OH(2_k-1_k)": 96.7413750,
    "CH3CN(12_0-11_0)": 220.7472610,
    "H30alpha": 231.9009280,
    "H40alpha": 99.0229500,
}


def normalize_observed_species_label(species: Any) -> str:
    """Normalize the user-facing observed-species label."""
    text = normalize_whitespace(species)
    return text if text else DEFAULT_OBSERVED_SPECIES


def observed_species_column_name(species: Any) -> str:
    """Return the output column label for the observed-species flag."""
    return f"Observed {normalize_observed_species_label(species)} in ALMA?"


def extract_line_species_token(line_name: str) -> str:
    """Extract the species token from a line label like 'HCN(1-0)'."""
    return line_name.split("(", 1)[0].strip()


def normalize_species_token(token: str) -> str:
    """Normalize a species token for exact comparison."""
    return re.sub(r"[\s\[\]]+", "", token).upper()


def line_matches_observed_species(line_name: str, observed_species: Any) -> bool:
    """Return True when a line label matches the selected observed-species query."""
    line_token = extract_line_species_token(line_name)
    query_token = extract_line_species_token(normalize_observed_species_label(observed_species))
    normalized_line = normalize_species_token(line_token)
    normalized_query = normalize_species_token(query_token)

    if normalized_query == "CO":
        return normalized_line in {"CO", "12CO", "13CO", "C18O", "C17O"}

    return normalized_line == normalized_query


def has_observed_species_line(target_lines: Any, observed_species: Any) -> bool:
    """Return True when inferred target lines include the selected observed species."""
    if is_blank(target_lines):
        return False

    return any(
        line_matches_observed_species(line_name=piece.strip(), observed_species=observed_species)
        for piece in str(target_lines).split(",")
        if piece.strip()
    )

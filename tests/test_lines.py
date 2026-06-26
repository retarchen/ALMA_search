from __future__ import annotations

from alma_search.lines import (
    DEFAULT_OBSERVED_SPECIES,
    has_observed_species_line,
    line_matches_observed_species,
    normalize_observed_species_label,
    observed_species_column_name,
)


def test_normalize_observed_species_label_defaults_to_co():
    assert normalize_observed_species_label("   ") == DEFAULT_OBSERVED_SPECIES


def test_line_matches_observed_species_for_co_family_only():
    assert line_matches_observed_species("12CO(2-1)", "CO") is True
    assert line_matches_observed_species("13CO(1-0)", "CO") is True
    assert line_matches_observed_species("H2CO(3_03-2_02)", "CO") is False


def test_has_observed_species_line_handles_comma_separated_lines():
    target_lines = "HCN(1-0), 12CO(2-1), [CI](1-0)"
    assert has_observed_species_line(target_lines, "CO") is True
    assert has_observed_species_line(target_lines, "HCN") is True
    assert has_observed_species_line(target_lines, "CS") is False


def test_observed_species_column_name_uses_requested_species():
    assert observed_species_column_name("HCN") == "Observed HCN in ALMA?"

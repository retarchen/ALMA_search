from __future__ import annotations

import math

import pandas as pd
import pytest

from alma_search.search import (
    classify_array_from_metadata,
    coarse_frequency_interval_from_em,
    infer_lines,
    parse_frequency_support,
    rows_from_query_results,
)


def test_parse_frequency_support_parses_multiple_units():
    intervals = parse_frequency_support(
        "[87.30..89.17GHz,foo] 1.23456E+11..1.24567E+11Hz 230.1 .. 232.0 GHz"
    )
    assert intervals[0] == (87.3, 89.17)
    assert intervals[1] == pytest.approx((123.456, 124.567))
    assert intervals[2] == (230.1, 232.0)


def test_coarse_frequency_interval_from_em_converts_wavelength_bounds():
    intervals = coarse_frequency_interval_from_em(1.3e-3, 1.2e-3)
    assert len(intervals) == 1
    low, high = intervals[0]
    assert 230 < low < 260
    assert 230 < high < 260


def test_infer_lines_finds_expected_line_from_frequency_support():
    result = infer_lines(
        frequency_support="[229.5..231.0GHz]",
        em_min="",
        em_max="",
        line_velocity_tolerance_kms=350.0,
    )
    assert "12CO(2-1)" in result


def test_classify_array_from_metadata_combines_arrays_in_expected_order():
    result = classify_array_from_metadata(
        instrument_name="ACA 7m + Total Power + Main Array",
        antenna_arrays="DV01 CM02 PM03",
    )
    assert result == "12m,7m,TP"


def test_rows_from_query_results_builds_expected_output_row():
    query_df = pd.DataFrame(
        [
            {
                "s_ra": 83.6331,
                "s_dec": -5.3911,
                "s_fov": 0.05,
                "proposal_id": "2019.1.00001.S",
                "target_name": "Orion KL",
                "band_list": "6",
                "frequency_support": "[229.5..231.0GHz]",
                "obs_title": "Example project",
                "instrument_name": "12m Array",
                "antenna_arrays": "DV01 DV02",
                "spectral_resolution": 15.2,
                "velocity_resolution": 2000.0,
                "sensitivity_10kms": 0.45,
                "em_min": 1.0e-3,
                "em_max": 1.5e-3,
            }
        ]
    )

    rows = rows_from_query_results(
        input_name="TargetA",
        input_ra_deg=83.6331,
        input_dec_deg=-5.3911,
        query_df=query_df,
        line_velocity_tolerance_kms=350.0,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["Name"] == "TargetA"
    assert row["project_code"] == "2019.1.00001.S"
    assert row["alma_target_name"] == "Orion KL"
    assert row["observing_band"] == "6"
    assert row["telescope"] == "12m"
    assert "12CO(2-1)" in row["target_lines"]
    assert math.isclose(row["distance_arcsec"], 0.0, abs_tol=1e-6)

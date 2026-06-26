from __future__ import annotations

import pandas as pd

from alma_search.io import (
    INTERNAL_OBSERVED_COLUMN,
    combine_arrays,
    combine_bands,
    combine_lines,
    deduplicate_results,
    load_targets_from_table,
    select_cleaner_rows,
)


def test_load_targets_from_table_converts_sexagesimal_coordinates():
    df = pd.DataFrame(
        [{"Name": "TargetA", "ra": "04:49:26.41", "dec": "-69:12:03.77"}]
    )
    targets = load_targets_from_table(df)
    assert list(targets.columns) == ["Name", "ra_deg", "dec_deg"]
    assert targets.loc[0, "Name"] == "TargetA"
    assert 72.0 < targets.loc[0, "ra_deg"] < 73.0
    assert -70.0 < targets.loc[0, "dec_deg"] < -69.0


def test_combine_helpers_keep_unique_stable_values():
    assert combine_arrays(["7m", "12m,TP", "7m"]) == "12m,7m,TP"
    assert combine_bands(["7 6", "6,3", "7"]) == "3,6,7"
    assert combine_lines(["Unknown", "HCN(1-0),12CO(2-1)", "HCN(1-0)"]) == "HCN(1-0),12CO(2-1)"


def test_deduplicate_results_combines_rows_and_uses_best_distance():
    df = pd.DataFrame(
        [
            {
                "Name": "SourceA",
                "ra": "01:00:00.00",
                "dec": "-01:00:00.00",
                "project_code": "2019.1.00001.S",
                "alma_target_name": "Core",
                "alma_ra": "01:00:00.00",
                "alma_dec": "-01:00:00.00",
                "distance_arcsec": 5.0,
                "fov_arcsec": 90.0,
                "observing_band": "6",
                "telescope": "12m",
                "target_lines": "12CO(2-1)",
                "spectral_resolution_khz": 10.0,
                "velocity_resolution_kms": 2.0,
                "sensitivity_10kms_mjy_beam": 0.4,
                "proposal_title": "Title A",
                INTERNAL_OBSERVED_COLUMN: pd.NA,
            },
            {
                "Name": "SourceA",
                "ra": "01:00:00.00",
                "dec": "-01:00:00.00",
                "project_code": "2019.1.00001.S",
                "alma_target_name": "Core",
                "alma_ra": "01:00:00.10",
                "alma_dec": "-01:00:00.10",
                "distance_arcsec": 2.0,
                "fov_arcsec": 120.0,
                "observing_band": "7",
                "telescope": "7m",
                "target_lines": "HCN(1-0)",
                "spectral_resolution_khz": 20.0,
                "velocity_resolution_kms": 3.0,
                "sensitivity_10kms_mjy_beam": 0.5,
                "proposal_title": "",
                INTERNAL_OBSERVED_COLUMN: pd.NA,
            },
        ]
    )

    result = deduplicate_results(df, "project_target", observed_species="CO")
    assert len(result) == 1
    row = result.iloc[0]
    assert row["distance_arcsec"] == 2.0
    assert row["fov_arcsec"] == 120.0
    assert row["observing_band"] == "6,7"
    assert row["telescope"] == "12m,7m"
    assert row["target_lines"] == "12CO(2-1),HCN(1-0)"
    assert row["spectral_resolution_khz"] == "10,20"
    assert row[INTERNAL_OBSERVED_COLUMN] == 1.0


def test_select_cleaner_rows_keeps_species_matches_and_unmatched_rows():
    df = pd.DataFrame(
        [
            {
                "Name": "NoMatch",
                "ra": "01:00:00.00",
                "dec": "-01:00:00.00",
                "project_code": pd.NA,
                "alma_target_name": pd.NA,
                "alma_ra": pd.NA,
                "alma_dec": pd.NA,
                "distance_arcsec": pd.NA,
                "fov_arcsec": pd.NA,
                "observing_band": pd.NA,
                "telescope": pd.NA,
                "target_lines": pd.NA,
                "spectral_resolution_khz": pd.NA,
                "velocity_resolution_kms": pd.NA,
                "sensitivity_10kms_mjy_beam": pd.NA,
                "proposal_title": pd.NA,
                INTERNAL_OBSERVED_COLUMN: 0.0,
            },
            {
                "Name": "Match",
                "ra": "02:00:00.00",
                "dec": "-02:00:00.00",
                "project_code": "2019.1.00002.S",
                "alma_target_name": "A",
                "alma_ra": "02:00:00.00",
                "alma_dec": "-02:00:00.00",
                "distance_arcsec": 10.0,
                "fov_arcsec": 150.0,
                "observing_band": "6",
                "telescope": "12m",
                "target_lines": "HCN(1-0)",
                "spectral_resolution_khz": "10",
                "velocity_resolution_kms": "2",
                "sensitivity_10kms_mjy_beam": "0.3",
                "proposal_title": "T1",
                INTERNAL_OBSERVED_COLUMN: 0.0,
            },
            {
                "Name": "Match",
                "ra": "02:00:00.00",
                "dec": "-02:00:00.00",
                "project_code": "2019.1.00002.S",
                "alma_target_name": "B",
                "alma_ra": "02:00:00.01",
                "alma_dec": "-02:00:00.01",
                "distance_arcsec": 5.0,
                "fov_arcsec": 150.0,
                "observing_band": "6",
                "telescope": "12m",
                "target_lines": "12CO(2-1)",
                "spectral_resolution_khz": "10",
                "velocity_resolution_kms": "2",
                "sensitivity_10kms_mjy_beam": "0.3",
                "proposal_title": "T2",
                INTERNAL_OBSERVED_COLUMN: 1.0,
            },
        ]
    )

    result = select_cleaner_rows(df, observed_species="CO", max_observed_rows_per_name=2)
    assert list(result["Name"]) == ["Match", "NoMatch"]
    assert result.iloc[0]["target_lines"] == "12CO(2-1)"

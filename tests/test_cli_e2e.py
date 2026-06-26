from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

from alma_search import cli


def _mock_query_df() -> pd.DataFrame:
    return pd.DataFrame(
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


def test_cli_main_end_to_end_with_mocked_archive(tmp_path, monkeypatch):
    input_csv = tmp_path / "targets.csv"
    output_csv = tmp_path / "results.csv"
    input_csv.write_text("Name,ra_deg,dec_deg\nTargetA,83.6331,-5.3911\n", encoding="utf-8")

    monkeypatch.setattr(cli, "create_tap_service", lambda: object())
    monkeypatch.setattr(cli, "query_alma_cone", lambda **kwargs: _mock_query_df())

    exit_code = cli.main([str(input_csv), str(output_csv), "--observed-species", "CO"])

    assert exit_code == 0
    result = pd.read_csv(output_csv)
    assert list(result["Name"]) == ["TargetA"]
    assert result.loc[0, "project_code"] == "2019.1.00001.S"
    assert result.loc[0, "Observed CO in ALMA?"] == "Yes"


def test_cli_main_returns_error_when_all_queries_fail(tmp_path, monkeypatch):
    input_csv = tmp_path / "targets.csv"
    output_csv = tmp_path / "results.csv"
    input_csv.write_text("Name,ra_deg,dec_deg\nTargetA,83.6331,-5.3911\n", encoding="utf-8")

    monkeypatch.setattr(cli, "create_tap_service", lambda: object())

    def _raise_query_failure(**kwargs):
        raise RuntimeError("simulated network failure")

    monkeypatch.setattr(cli, "query_alma_cone", _raise_query_failure)

    exit_code = cli.main([str(input_csv), str(output_csv)])

    assert exit_code == 2
    assert not output_csv.exists()


def test_compatibility_script_end_to_end_in_subprocess(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    fake_site = tmp_path / "fake_site"
    pyvo_pkg = fake_site / "pyvo"
    pyvo_pkg.mkdir(parents=True)

    (pyvo_pkg / "__init__.py").write_text("from . import dal\n", encoding="utf-8")
    (pyvo_pkg / "dal.py").write_text(
        """
from __future__ import annotations

import pandas as pd


class _FakeTable:
    def __init__(self, df):
        self._df = df

    def __len__(self):
        return len(self._df)

    def to_pandas(self):
        return self._df.copy()


class _FakeResult:
    def __init__(self, df):
        self._df = df

    def to_table(self):
        return _FakeTable(self._df)


class TAPService:
    def __init__(self, url):
        self.url = url

    def search(self, adql):
        df = pd.DataFrame(
            [
                {
                    "proposal_id": "2019.1.00003.S",
                    "target_name": "Mock Source",
                    "s_ra": 83.6331,
                    "s_dec": -5.3911,
                    "s_fov": 0.05,
                    "band_list": "6",
                    "frequency_support": "[229.5..231.0GHz]",
                    "obs_title": "Mock proposal",
                    "obs_creator_name": "Tester",
                    "instrument_name": "12m Array",
                    "antenna_arrays": "DV01 DV02",
                    "spectral_resolution": 15.2,
                    "velocity_resolution": 2000.0,
                    "sensitivity_10kms": 0.45,
                    "em_min": 1.0e-3,
                    "em_max": 1.5e-3,
                    "obs_id": "uid://A001",
                    "member_ous_uid": "uid://B001",
                }
            ]
        )
        return _FakeResult(df)
""".strip()
        + "\n",
        encoding="utf-8",
    )

    input_csv = tmp_path / "targets.csv"
    output_csv = tmp_path / "results.csv"
    input_csv.write_text("Name,ra_deg,dec_deg\nTargetA,83.6331,-5.3911\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(fake_site) + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [sys.executable, "alma_nearby_search.py", str(input_csv), str(output_csv)],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    output_df = pd.read_csv(output_csv)
    assert output_df.loc[0, "project_code"] == "2019.1.00003.S"
    assert output_df.loc[0, "Observed CO in ALMA?"] == "Yes"

"""ALMA archive querying and result-row construction."""

from __future__ import annotations

import logging
import re
from typing import Any

import pandas as pd

from .io import INTERNAL_OBSERVED_COLUMN, combine_bands
from .lines import LINE_CATALOG_GHZ
from .utils import (
    format_ra_dec_strings,
    is_blank,
    normalize_whitespace,
    safe_get,
    to_optional_float,
    unique_preserve_order,
)

LOGGER = logging.getLogger("alma_nearby_search")
ALMA_TAP_URL = "https://almascience.eso.org/tap"
DEFAULT_RADIUS_ARCMIN = 5.0
DEFAULT_LINE_TOLERANCE_KMS = 350.0
ARRAY_ORDER = ("12m", "7m", "TP")


def create_tap_service(tap_url: str = ALMA_TAP_URL) -> Any:
    """Create the ALMA TAP service client."""
    try:
        import pyvo
    except ImportError as exc:
        raise ImportError("pyvo is not installed. Install it with: pip install pyvo") from exc
    return pyvo.dal.TAPService(tap_url)


def build_adql_query(ra_deg: float, dec_deg: float, radius_deg: float) -> str:
    """Build the ALMA ObsCore cone-search ADQL query."""
    return f"""
SELECT
    proposal_id,
    target_name,
    s_ra,
    s_dec,
    s_fov,
    band_list,
    frequency_support,
    obs_title,
    obs_creator_name,
    instrument_name,
    antenna_arrays,
    spectral_resolution,
    velocity_resolution,
    sensitivity_10kms,
    em_min,
    em_max,
    obs_id,
    member_ous_uid
FROM ivoa.obscore
WHERE
    1 = CONTAINS(
        POINT('ICRS', s_ra, s_dec),
        CIRCLE('ICRS', {ra_deg:.10f}, {dec_deg:.10f}, {radius_deg:.10f})
    )
"""


def query_alma_cone(
    service: Any,
    ra_deg: float,
    dec_deg: float,
    radius_arcmin: float,
) -> pd.DataFrame:
    """Query ALMA ObsCore for a cone around a target position."""
    radius_deg = radius_arcmin / 60.0
    adql = build_adql_query(ra_deg=ra_deg, dec_deg=dec_deg, radius_deg=radius_deg)
    LOGGER.debug("Submitting ADQL query for RA=%.6f Dec=%.6f", ra_deg, dec_deg)
    result = service.search(adql)
    table = result.to_table()
    if len(table) == 0:
        return pd.DataFrame()

    df = table.to_pandas()
    df.columns = [str(col) for col in df.columns]
    return df


def parse_frequency_support(frequency_support: Any) -> list[tuple[float, float]]:
    """
    Parse the ALMA frequency_support metadata string into GHz intervals.

    The field often contains text fragments like:
        [87.30..89.17GHz, ...]
        1.23456E+11..1.24567E+11Hz
        230.1 .. 232.0 GHz U 234.0 .. 236.0 GHz

    The parser is intentionally permissive and extracts every interval that
    looks like "number .. number unit".
    """
    if is_blank(frequency_support):
        return []

    text = str(frequency_support)
    interval_pattern = re.compile(
        r"([0-9]+(?:\.[0-9]+)?(?:[eE][+\-]?[0-9]+)?)\s*\.\.\s*"
        r"([0-9]+(?:\.[0-9]+)?(?:[eE][+\-]?[0-9]+)?)\s*"
        r"(GHz|MHz|kHz|Hz)",
        flags=re.IGNORECASE,
    )

    factor_by_unit = {
        "ghz": 1.0,
        "mhz": 1e-3,
        "khz": 1e-6,
        "hz": 1e-9,
    }

    intervals: list[tuple[float, float]] = []
    for match in interval_pattern.finditer(text):
        low = float(match.group(1))
        high = float(match.group(2))
        unit = match.group(3).lower()
        factor = factor_by_unit[unit]
        low_ghz = low * factor
        high_ghz = high * factor
        intervals.append((min(low_ghz, high_ghz), max(low_ghz, high_ghz)))

    return intervals


def coarse_frequency_interval_from_em(em_min: Any, em_max: Any) -> list[tuple[float, float]]:
    """Convert em_min/em_max wavelength bounds in meters into a coarse GHz interval."""
    if is_blank(em_min) or is_blank(em_max):
        return []

    try:
        lam_min_m = float(em_min)
        lam_max_m = float(em_max)
    except (TypeError, ValueError):
        return []

    if lam_min_m <= 0 or lam_max_m <= 0:
        return []

    c_m_s = 299792458.0
    f1_ghz = (c_m_s / lam_min_m) / 1e9
    f2_ghz = (c_m_s / lam_max_m) / 1e9
    return [(min(f1_ghz, f2_ghz), max(f1_ghz, f2_ghz))]


def infer_lines(
    frequency_support: Any,
    em_min: Any,
    em_max: Any,
    line_velocity_tolerance_kms: float,
    line_catalog_ghz: dict[str, float] | None = None,
) -> str:
    """Infer likely spectral lines from spectral coverage."""
    catalog = line_catalog_ghz or LINE_CATALOG_GHZ
    intervals = parse_frequency_support(frequency_support)
    if not intervals:
        intervals = coarse_frequency_interval_from_em(em_min, em_max)
    if not intervals:
        return "Unknown"

    c_kms = 299792.458
    matched: list[str] = []
    for line_name, rest_ghz in catalog.items():
        tol_ghz = rest_ghz * line_velocity_tolerance_kms / c_kms
        for low_ghz, high_ghz in intervals:
            if (low_ghz - tol_ghz) <= rest_ghz <= (high_ghz + tol_ghz):
                matched.append(line_name)
                break

    matches = unique_preserve_order(matched)
    return ",".join(matches) if matches else "Unknown"


def classify_array(instrument_name: Any) -> str:
    """Map ALMA metadata values onto 12m, 7m, and TP array classes."""
    return classify_array_from_metadata(instrument_name=instrument_name, antenna_arrays="")


def classify_array_from_metadata(instrument_name: Any, antenna_arrays: Any) -> str:
    """Classify ALMA array usage from instrument and antenna metadata."""
    instrument_text = "" if is_blank(instrument_name) else str(instrument_name).lower()
    antenna_text = "" if is_blank(antenna_arrays) else str(antenna_arrays)
    found: list[str] = []

    tp_patterns = ("total power", "tp array", "tp-", " tp", "aca tp")
    if any(pattern in instrument_text for pattern in tp_patterns) or re.search(r":PM\d+\b", antenna_text):
        found.append("TP")

    seven_m_patterns = ("7m", "7-m", "morita", "aca", "compact array")
    if any(pattern in instrument_text for pattern in seven_m_patterns) or re.search(r":CM\d+\b", antenna_text):
        found.append("7m")

    twelve_m_patterns = ("12m", "12-m", "main array")
    if any(pattern in instrument_text for pattern in twelve_m_patterns) or re.search(r":(?:DA|DV)\d+\b", antenna_text):
        found.append("12m")

    ordered = [array for array in ARRAY_ORDER if array in found]
    return ",".join(ordered)


def rows_from_query_results(
    input_name: str,
    input_ra_deg: float,
    input_dec_deg: float,
    query_df: pd.DataFrame,
    line_velocity_tolerance_kms: float,
) -> list[dict[str, Any]]:
    """Transform raw query rows into output rows."""
    if query_df.empty:
        return []

    import astropy.units as u
    from astropy.coordinates import SkyCoord

    origin = SkyCoord(input_ra_deg * u.deg, input_dec_deg * u.deg, frame="icrs")
    input_ra_text, input_dec_text = format_ra_dec_strings(input_ra_deg, input_dec_deg)
    output_rows: list[dict[str, Any]] = []

    for _, row in query_df.iterrows():
        alma_ra = safe_get(row, "s_ra", "")
        alma_dec = safe_get(row, "s_dec", "")
        try:
            alma_ra_float = float(alma_ra)
            alma_dec_float = float(alma_dec)
        except (TypeError, ValueError):
            LOGGER.debug("Skipping row with invalid ALMA position: %s", row.to_dict())
            continue

        alma_coord = SkyCoord(alma_ra_float * u.deg, alma_dec_float * u.deg, frame="icrs")
        distance_arcsec = origin.separation(alma_coord).arcsecond
        alma_ra_text, alma_dec_text = format_ra_dec_strings(alma_ra_float, alma_dec_float)

        s_fov = safe_get(row, "s_fov", "")
        fov_arcsec = to_optional_float(s_fov, scale=3600.0, digits=3)

        project_code = normalize_whitespace(safe_get(row, "proposal_id", ""))
        alma_target_name = normalize_whitespace(safe_get(row, "target_name", ""))
        observing_band = combine_bands([safe_get(row, "band_list", "")])
        telescope = classify_array_from_metadata(
            instrument_name=safe_get(row, "instrument_name", ""),
            antenna_arrays=safe_get(row, "antenna_arrays", ""),
        )
        target_lines = infer_lines(
            frequency_support=safe_get(row, "frequency_support", ""),
            em_min=safe_get(row, "em_min", ""),
            em_max=safe_get(row, "em_max", ""),
            line_velocity_tolerance_kms=line_velocity_tolerance_kms,
        )

        output_rows.append(
            {
                "Name": input_name,
                "ra": input_ra_text,
                "dec": input_dec_text,
                "project_code": project_code,
                "alma_target_name": alma_target_name,
                "alma_ra": alma_ra_text,
                "alma_dec": alma_dec_text,
                "distance_arcsec": round(distance_arcsec, 3),
                "fov_arcsec": fov_arcsec,
                "observing_band": observing_band,
                "telescope": telescope,
                "target_lines": target_lines,
                "spectral_resolution_khz": to_optional_float(safe_get(row, "spectral_resolution", "")),
                "velocity_resolution_kms": to_optional_float(
                    safe_get(row, "velocity_resolution", ""),
                    scale=1e-3,
                ),
                "sensitivity_10kms_mjy_beam": to_optional_float(safe_get(row, "sensitivity_10kms", "")),
                "proposal_title": normalize_whitespace(safe_get(row, "obs_title", "")),
                INTERNAL_OBSERVED_COLUMN: pd.NA,
            }
        )

    return output_rows

#!/usr/bin/env python3
"""
ALMA nearby archive search tool.

README
Install dependencies:
    pip install pyvo astropy pandas

Usage:
    python alma_nearby_search.py input.csv output.csv --radius-arcmin 5 --dedup-level project_target

This script reads an input CSV/text file with either:
    Name, ra_deg, dec_deg
or:
    Name, ra, dec

It queries the ALMA TAP service through the ObsCore table, finds observations
within a cone around each target position, computes angular separations in
Python, infers likely spectral lines from the returned spectral coverage, and
writes the results to a CSV.

Example input CSV:
    Name,ra_deg,dec_deg
    TargetA,83.6331,-5.3911
    TargetB,150.025,-34.433

Example command:
    python alma_nearby_search.py targets.csv alma_matches.csv --radius-arcmin 5 --dedup-level project_target
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

import astropy.units as u
import pandas as pd
from astropy.coordinates import SkyCoord

try:
    import pyvo
except ImportError:  # pragma: no cover - exercised only in under-provisioned environments.
    pyvo = None

LOGGER = logging.getLogger("alma_nearby_search")
ALMA_TAP_URL = "https://almascience.eso.org/tap"
DEFAULT_RADIUS_ARCMIN = 5.0
DEFAULT_LINE_TOLERANCE_KMS = 350.0
ARRAY_ORDER = ("12m", "7m", "TP")
DEFAULT_OBSERVED_SPECIES = "CO"
INTERNAL_OBSERVED_COLUMN = "observed_species_in_alma_flag"

LINE_CATALOG_GHZ: dict[str, float] = {
# =======================
# CO ladder (CRITICAL)
# =======================
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

# =======================
# Dense gas tracers
# =======================
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

# =======================
# Diffuse / PDR tracers
# =======================
# These CN and CCH entries are effective group centers for hyperfine complexes,
# used here as practical spectral-coverage proxies rather than unique components.
"CN(1-0)": 113.4909700,
"CN(2-1)": 226.8740000,

"CCH(1-0)": 87.3168980,
"CCH(3-2)": 262.0042600,

# =======================
# Carbon / key transition lines
# =======================
"[CI](1-0)": 492.1606510,
"[CI](2-1)": 809.3419700,

# =======================
# Shock tracers
# =======================
"SiO(2-1)": 86.8469600,
"SiO(5-4)": 217.1049800,
"SiO(8-7)": 347.3306310,

"SO(5_6-4_5)": 219.9494420,
"SO(6_5-5_4)": 251.8257700,

"SO2(11_1,11-10_0,10)": 221.9652200,

# =======================
# Chemistry / cold gas
# =======================
"H2CO(3_03-2_02)": 218.2221920,
"H2CO(3_22-2_21)": 218.4756320,
"H2CO(3_21-2_20)": 218.7600660,

"H2CO(2_12-1_11)": 140.8395020,

"NH2D(1_11-1_01)": 85.9262630,

# =======================
# Complex / star-forming tracers (limited)
# =======================
"CH3OH(5_0-4_0)": 241.7914310,
# Group center for the 2_k-1_k methanol complex near 96.741 GHz.
"CH3OH(2_k-1_k)": 96.7413750,

"CH3CN(12_0-11_0)": 220.7472610,

# =======================
# Recombination lines (few key ones)
# =======================
"H30alpha": 231.9009280,
"H40alpha": 99.0229500,

}

INTERNAL_OUTPUT_COLUMNS = [
    "Name",
    "ra",
    "dec",
    "project_code",
    "alma_target_name",
    "alma_ra",
    "alma_dec",
    "distance_arcsec",
    "fov_arcsec",
    "observing_band",
    "telescope",
    "target_lines",
    "spectral_resolution_khz",
    "velocity_resolution_kms",
    "sensitivity_10kms_mjy_beam",
    "proposal_title",
    INTERNAL_OBSERVED_COLUMN,
]


def configure_logging(verbose: bool) -> None:
    """Configure process logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def safe_get(record: dict[str, Any], key: str, default: Any = "") -> Any:
    """Return a dictionary value while normalizing missing and null-like values."""
    value = record.get(key, default)
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    return value


def is_blank(value: Any) -> bool:
    """Return True when a value should be treated as blank."""
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    if isinstance(value, str) and not value.strip():
        return True
    return False


def normalize_whitespace(value: Any) -> str:
    """Collapse arbitrary whitespace in a string value."""
    if is_blank(value):
        return ""
    return " ".join(str(value).split())


def unique_preserve_order(items: Iterable[str]) -> list[str]:
    """Return unique non-blank strings while preserving first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if not item:
            continue
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def stable_sort_numeric_strings(values: Iterable[str]) -> list[str]:
    """Sort string values numerically when possible, otherwise lexically."""
    unique_values = unique_preserve_order(str(v) for v in values if str(v).strip())

    def sort_key(item: str) -> tuple[int, float | str]:
        try:
            return (0, float(item))
        except ValueError:
            return (1, item)

    return sorted(unique_values, key=sort_key)


def parse_ra_dec_to_degrees(ra_value: Any, dec_value: Any) -> tuple[float, float]:
    """Parse RA/Dec values supplied either in degrees or sexagesimal strings."""
    if is_blank(ra_value) or is_blank(dec_value):
        raise ValueError("RA/Dec values must not be blank")

    ra_text = str(ra_value).strip()
    dec_text = str(dec_value).strip()

    try:
        return float(ra_text), float(dec_text)
    except ValueError:
        pass

    coord = SkyCoord(ra_text, dec_text, unit=(u.hourangle, u.deg), frame="icrs")
    return float(coord.ra.deg), float(coord.dec.deg)


def format_ra_dec_strings(ra_deg: float, dec_deg: float) -> tuple[str, str]:
    """Format RA/Dec in sexagesimal strings using colon separators."""
    coord = SkyCoord(ra_deg * u.deg, dec_deg * u.deg, frame="icrs")
    ra_text = coord.ra.to_string(unit=u.hour, sep=":", precision=2, pad=True)
    dec_text = coord.dec.to_string(unit=u.deg, sep=":", precision=2, pad=True, alwayssign=True)
    return str(ra_text), str(dec_text)


def to_optional_float(value: Any, scale: float = 1.0, digits: int = 3) -> float | pd.NA:
    """Convert a value to a rounded float or pandas NA."""
    if is_blank(value):
        return pd.NA
    try:
        return round(float(value) * scale, digits)
    except (TypeError, ValueError):
        return pd.NA


def format_float_text(value: Any, digits: int = 3) -> str:
    """Format a scalar value compactly for CSV string columns."""
    if is_blank(value):
        return ""
    try:
        number = round(float(value), digits)
    except (TypeError, ValueError):
        return normalize_whitespace(value)
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def normalize_observed_species_label(species: Any) -> str:
    """Normalize the user-facing observed-species label."""
    text = normalize_whitespace(species)
    return text if text else DEFAULT_OBSERVED_SPECIES


def observed_species_column_name(species: Any) -> str:
    """Return the output column label for the observed-species flag."""
    return f"Observed {normalize_observed_species_label(species)} in ALMA?"


def get_output_columns(species: Any) -> list[str]:
    """Return the public output-column order for the selected observed species."""
    return [
        observed_species_column_name(species) if column == INTERNAL_OBSERVED_COLUMN else column
        for column in INTERNAL_OUTPUT_COLUMNS
    ]


def combine_scalar_values(values: Sequence[Any], digits: int = 3) -> str | pd.NA:
    """Combine scalar values into a unique comma-separated string."""
    formatted = unique_preserve_order(
        format_float_text(value, digits=digits)
        for value in values
        if not is_blank(value) and format_float_text(value, digits=digits)
    )
    if not formatted:
        return pd.NA
    return ",".join(formatted)


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


def compute_observed_species_flag(
    target_lines: Any,
    distance_arcsec: Any,
    fov_arcsec: Any,
    observed_species: Any,
) -> float:
    """Compute the user-facing observed-species flag."""
    if not has_observed_species_line(target_lines, observed_species):
        return 0.0

    try:
        distance_value = float(distance_arcsec)
    except (TypeError, ValueError):
        return 0.0

    if distance_value < 30.0:
        return 1.0

    try:
        fov_value = float(fov_arcsec)
    except (TypeError, ValueError):
        return 0.0

    if distance_value >= 30.0 and fov_value > 100.0:
        return 0.5
    return 0.0


def build_no_match_row(input_name: str, input_ra_deg: float, input_dec_deg: float) -> dict[str, Any]:
    """Create a placeholder output row for targets with no ALMA matches."""
    ra_text, dec_text = format_ra_dec_strings(input_ra_deg, input_dec_deg)
    return {
        "Name": input_name,
        "ra": ra_text,
        "dec": dec_text,
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
    }


def load_targets_from_table(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize supported tabular target inputs into Name, ra_deg, dec_deg."""
    columns = {str(col): col for col in df.columns}
    required_degree = {"Name", "ra_deg", "dec_deg"}
    if required_degree.issubset(columns):
        targets = df.loc[:, ["Name", "ra_deg", "dec_deg"]].copy()
        targets["Name"] = targets["Name"].astype(str)
        targets["ra_deg"] = pd.to_numeric(targets["ra_deg"], errors="coerce")
        targets["dec_deg"] = pd.to_numeric(targets["dec_deg"], errors="coerce")
    elif {"Name", "ra", "dec"}.issubset(columns):
        normalized_rows: list[dict[str, Any]] = []
        for idx, row in df.iterrows():
            try:
                ra_deg, dec_deg = parse_ra_dec_to_degrees(row["ra"], row["dec"])
            except Exception as exc:
                raise ValueError(f"Invalid RA/Dec values in input row {idx + 2}: {exc}") from exc
            normalized_rows.append(
                {
                    "Name": str(row["Name"]),
                    "ra_deg": ra_deg,
                    "dec_deg": dec_deg,
                }
            )
        targets = pd.DataFrame(normalized_rows, columns=["Name", "ra_deg", "dec_deg"])
    else:
        raise ValueError(
            "Input table must contain either Name,ra_deg,dec_deg or Name,ra,dec columns"
        )

    invalid = targets["ra_deg"].isna() | targets["dec_deg"].isna()
    if invalid.any():
        bad_rows = (targets.index[invalid] + 2).tolist()
        raise ValueError(f"Invalid RA/Dec values in input rows: {bad_rows}")
    return targets


def load_targets_from_text(path: str) -> pd.DataFrame:
    """Load targets from a plain-text file with lines like 'Name,RA DEC'."""
    normalized_rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            parts = [part.strip() for part in line.split(",", maxsplit=1)]
            if len(parts) != 2:
                raise ValueError(
                    f"Could not parse line {line_number}: expected 'Name,RA DEC', got {raw_line.rstrip()!r}"
                )

            name, coord_text = parts
            coord_parts = coord_text.split()
            if len(coord_parts) != 2:
                raise ValueError(
                    f"Could not parse coordinates on line {line_number}: {coord_text!r}"
                )

            try:
                ra_deg, dec_deg = parse_ra_dec_to_degrees(coord_parts[0], coord_parts[1])
            except Exception as exc:
                raise ValueError(f"Invalid coordinates on line {line_number}: {exc}") from exc

            normalized_rows.append(
                {
                    "Name": name,
                    "ra_deg": ra_deg,
                    "dec_deg": dec_deg,
                }
            )

    return pd.DataFrame(normalized_rows, columns=["Name", "ra_deg", "dec_deg"])


def load_targets(path: str) -> pd.DataFrame:
    """Load supported target files and normalize coordinates into degrees."""
    input_path = Path(path)

    try:
        df = pd.read_csv(path)
        return load_targets_from_table(df)
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError, ValueError):
        LOGGER.debug("Falling back to plain-text target parsing for %s", input_path)

    if input_path.suffix.lower() not in {".txt", ".dat", ".list", ".csv"}:
        LOGGER.debug("Attempting plain-text parse for unsupported extension %s", input_path.suffix)

    return load_targets_from_text(path)


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


def combine_arrays(values: Sequence[str]) -> str:
    """Combine multiple classified array values in stable order."""
    flattened: list[str] = []
    for value in values:
        if is_blank(value):
            continue
        flattened.extend(part.strip() for part in str(value).split(",") if part.strip())
    unique = unique_preserve_order(flattened)
    ordered = [array for array in ARRAY_ORDER if array in unique]
    return ",".join(ordered)


def combine_bands(values: Sequence[Any]) -> str:
    """Combine band_list values into a unique sorted comma-separated string."""
    tokens: list[str] = []
    for value in values:
        if is_blank(value):
            continue
        for piece in re.split(r"[,\s;/|]+", str(value)):
            cleaned = piece.strip()
            if cleaned:
                tokens.append(cleaned)
    return ",".join(stable_sort_numeric_strings(tokens))


def combine_lines(values: Sequence[str]) -> str:
    """Combine matched line lists into a unique comma-separated string."""
    items: list[str] = []
    unknown_seen = False
    for value in values:
        if is_blank(value):
            continue
        for piece in str(value).split(","):
            cleaned = piece.strip()
            if not cleaned:
                continue
            if cleaned == "Unknown":
                unknown_seen = True
                continue
            items.append(cleaned)

    unique_items = unique_preserve_order(items)
    if unique_items:
        return ",".join(unique_items)
    return "Unknown" if unknown_seen else ""


def blank_string_to_na(value: Any) -> Any:
    """Convert blank strings to pandas NA while preserving non-blank values."""
    if isinstance(value, str) and not value.strip():
        return pd.NA
    return value


def finalize_results(df: pd.DataFrame, observed_species: Any) -> pd.DataFrame:
    """Apply final normalization and derived columns before CSV export."""
    if df.empty:
        return df.copy()

    output = df.copy()
    for field in (
        "project_code",
        "alma_target_name",
        "alma_ra",
        "alma_dec",
        "observing_band",
        "telescope",
        "target_lines",
        "spectral_resolution_khz",
        "velocity_resolution_kms",
        "sensitivity_10kms_mjy_beam",
        "proposal_title",
    ):
        output[field] = output[field].map(blank_string_to_na)

    output[INTERNAL_OBSERVED_COLUMN] = output.apply(
        lambda row: compute_observed_species_flag(
            target_lines=row.get("target_lines"),
            distance_arcsec=row.get("distance_arcsec"),
            fov_arcsec=row.get("fov_arcsec"),
            observed_species=observed_species,
        ),
        axis=1,
    )
    output[INTERNAL_OBSERVED_COLUMN] = output.groupby("Name", dropna=False)[INTERNAL_OBSERVED_COLUMN].transform("max")
    return output


def select_cleaner_rows(
    df: pd.DataFrame,
    observed_species: Any,
    max_observed_rows_per_name: int,
) -> pd.DataFrame:
    """
    Reduce the final table to a cleaner subset.

    Rules:
    - keep one unmatched row when a source has no ALMA match
    - keep up to ``max_observed_rows_per_name`` closest rows when the selected observed species exists
    - otherwise keep the single closest row for that source
    """
    if df.empty:
        return df.copy()

    ordered = df.copy()
    ordered["_distance_sort"] = pd.to_numeric(ordered["distance_arcsec"], errors="coerce")
    ordered = ordered.sort_values(["Name", "_distance_sort"], kind="stable", na_position="last")

    selected_groups: list[pd.DataFrame] = []
    for _, group in ordered.groupby("Name", sort=False, dropna=False):
        unmatched = group[group["project_code"].isna()]
        if not unmatched.empty:
            selected_groups.append(unmatched.head(1))
            continue

        species_rows = group[
            group["target_lines"].fillna("").map(
                lambda value: has_observed_species_line(value, observed_species)
            )
        ]
        if not species_rows.empty:
            selected_groups.append(species_rows.head(max_observed_rows_per_name))
        else:
            selected_groups.append(group.head(1))

    cleaned = pd.concat(selected_groups, ignore_index=True)
    cleaned = cleaned.sort_values(["Name", "_distance_sort"], kind="stable", na_position="last")
    return cleaned.drop(columns=["_distance_sort"])


def deduplicate_results(df: pd.DataFrame, dedup_level: str, observed_species: Any) -> pd.DataFrame:
    """Deduplicate result rows according to the requested grouping level."""
    if df.empty or dedup_level == "none":
        return finalize_results(df, observed_species=observed_species)

    group_keys = ["Name", "ra", "dec", "project_code"]
    if dedup_level == "project_target":
        group_keys.append("alma_target_name")
    elif dedup_level != "project":
        raise ValueError(f"Unsupported dedup_level: {dedup_level}")

    grouped_rows: list[dict[str, Any]] = []
    for _, group in df.groupby(group_keys, dropna=False, sort=False):
        numeric_distance = pd.to_numeric(group["distance_arcsec"], errors="coerce")
        if numeric_distance.notna().any():
            best_idx = numeric_distance.idxmin()
        else:
            best_idx = group.index[0]
        best = group.loc[best_idx].to_dict()

        numeric_fov = pd.to_numeric(group["fov_arcsec"], errors="coerce")
        best["fov_arcsec"] = round(numeric_fov.max(), 3) if numeric_fov.notna().any() else pd.NA
        best["observing_band"] = blank_string_to_na(combine_bands(group["observing_band"].tolist()))
        best["telescope"] = blank_string_to_na(combine_arrays(group["telescope"].tolist()))
        best["target_lines"] = blank_string_to_na(combine_lines(group["target_lines"].tolist()))
        best["spectral_resolution_khz"] = combine_scalar_values(group["spectral_resolution_khz"].tolist(), digits=3)
        best["velocity_resolution_kms"] = combine_scalar_values(group["velocity_resolution_kms"].tolist(), digits=3)
        best["sensitivity_10kms_mjy_beam"] = combine_scalar_values(group["sensitivity_10kms_mjy_beam"].tolist(), digits=3)

        for field in ("proposal_title",):
            if is_blank(best.get(field)):
                candidates = [normalize_whitespace(v) for v in group[field].tolist()]
                for candidate in candidates:
                    if candidate:
                        best[field] = candidate
                        break

        grouped_rows.append(best)

    return finalize_results(
        pd.DataFrame(grouped_rows, columns=INTERNAL_OUTPUT_COLUMNS),
        observed_species=observed_species,
    )


def write_csv(df: pd.DataFrame, path: str, observed_species: Any) -> None:
    """Write results to CSV with the canonical column order."""
    output = df.copy()
    for column in INTERNAL_OUTPUT_COLUMNS:
        if column not in output.columns:
            output[column] = pd.NA

    output = output.loc[:, INTERNAL_OUTPUT_COLUMNS]
    output = output.rename(columns={INTERNAL_OBSERVED_COLUMN: observed_species_column_name(observed_species)})
    output["_distance_sort"] = pd.to_numeric(output["distance_arcsec"], errors="coerce")
    output = output.sort_values(by=["Name", "_distance_sort"], ascending=[True, True], kind="stable", na_position="last")
    output = output.drop(columns=["_distance_sort"])
    output.to_csv(path, index=False, na_rep="NaN")


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


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Search the ALMA archive near input sky positions and export matches to CSV."
    )
    parser.add_argument("input_csv", help="Input CSV/text with Name and coordinates")
    parser.add_argument("output_csv", help="Output CSV path")
    parser.add_argument(
        "--radius-arcmin",
        type=float,
        default=DEFAULT_RADIUS_ARCMIN,
        help=f"Cone-search radius in arcmin. Default: {DEFAULT_RADIUS_ARCMIN}",
    )
    parser.add_argument(
        "--dedup-level",
        choices=("none", "project", "project_target"),
        default="project_target",
        help="Deduplication level for output rows. Default: project_target",
    )
    parser.add_argument(
        "--line-velocity-tolerance-kms",
        type=float,
        default=DEFAULT_LINE_TOLERANCE_KMS,
        help=f"Velocity tolerance for line matching in km/s. Default: {DEFAULT_LINE_TOLERANCE_KMS}",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--observed-species",
        default=DEFAULT_OBSERVED_SPECIES,
        help=f"Species used for the final observed-in-ALMA flag and cleaner selection. Default: {DEFAULT_OBSERVED_SPECIES}",
    )
    parser.add_argument(
        "--cleaner",
        action="store_true",
        help="Write a reduced output table: keep unmatched rows, up to N closest rows for the selected observed species per source, otherwise one closest row",
    )
    parser.add_argument(
        "--cleaner-max-observed-rows-per-name",
        "--cleaner-max-co-rows-per-name",
        dest="cleaner_max_observed_rows_per_name",
        type=int,
        default=5,
        help="Maximum number of closest rows to keep per source for the selected observed species when --cleaner is used. Default: 5",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Program entry point."""
    args = parse_args(argv)
    configure_logging(verbose=args.verbose)

    if args.radius_arcmin <= 0:
        LOGGER.error("--radius-arcmin must be positive")
        return 1
    if args.line_velocity_tolerance_kms < 0:
        LOGGER.error("--line-velocity-tolerance-kms must be non-negative")
        return 1
    if args.cleaner_max_observed_rows_per_name <= 0:
        LOGGER.error("--cleaner-max-observed-rows-per-name must be positive")
        return 1

    try:
        targets = load_targets(args.input_csv)
    except Exception as exc:
        LOGGER.error("Failed to load input targets: %s", exc)
        return 1

    try:
        if pyvo is None:
            raise ImportError(
                "pyvo is not installed. Install it with: pip install pyvo"
            )
        service = pyvo.dal.TAPService(ALMA_TAP_URL)
    except Exception as exc:
        LOGGER.error("Failed to initialize ALMA TAP service: %s", exc)
        return 1

    all_rows: list[dict[str, Any]] = []
    for target in targets.itertuples(index=False):
        LOGGER.info(
            "Searching ALMA archive for %s at RA=%.6f Dec=%.6f within %.3f arcmin",
            target.Name,
            target.ra_deg,
            target.dec_deg,
            args.radius_arcmin,
        )
        try:
            query_df = query_alma_cone(
                service=service,
                ra_deg=float(target.ra_deg),
                dec_deg=float(target.dec_deg),
                radius_arcmin=float(args.radius_arcmin),
            )
        except Exception as exc:
            LOGGER.exception("ALMA TAP query failed for target %s: %s", target.Name, exc)
            all_rows.append(
                build_no_match_row(
                    input_name=str(target.Name),
                    input_ra_deg=float(target.ra_deg),
                    input_dec_deg=float(target.dec_deg),
                )
            )
            continue

        rows = rows_from_query_results(
            input_name=str(target.Name),
            input_ra_deg=float(target.ra_deg),
            input_dec_deg=float(target.dec_deg),
            query_df=query_df,
            line_velocity_tolerance_kms=float(args.line_velocity_tolerance_kms),
        )
        LOGGER.info("Found %d raw matches for %s", len(rows), target.Name)
        if rows:
            all_rows.extend(rows)
        else:
            all_rows.append(
                build_no_match_row(
                    input_name=str(target.Name),
                    input_ra_deg=float(target.ra_deg),
                    input_dec_deg=float(target.dec_deg),
                )
            )

    if all_rows:
        raw_df = pd.DataFrame(all_rows, columns=INTERNAL_OUTPUT_COLUMNS)
        result_df = deduplicate_results(
            raw_df,
            args.dedup_level,
            observed_species=args.observed_species,
        )
    else:
        result_df = pd.DataFrame(columns=INTERNAL_OUTPUT_COLUMNS)

    if args.cleaner:
        result_df = select_cleaner_rows(
            result_df,
            observed_species=args.observed_species,
            max_observed_rows_per_name=int(args.cleaner_max_observed_rows_per_name),
        )

    try:
        write_csv(result_df, args.output_csv, observed_species=args.observed_species)
    except Exception as exc:
        LOGGER.error("Failed to write output CSV: %s", exc)
        return 1

    LOGGER.info("Wrote %d rows to %s", len(result_df), args.output_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Input parsing and output-table helpers.

This module is responsible for normalizing user-supplied target catalogs,
combining and cleaning intermediate result rows, computing the final
observed-species flag, and writing the canonical CSV schema.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from .lines import (
    DEFAULT_OBSERVED_SPECIES,
    INTERNAL_OBSERVED_COLUMN,
    has_observed_species_line,
    observed_species_column_name,
)
from .utils import (
    combine_scalar_values,
    format_float_text,
    format_ra_dec_strings,
    is_blank,
    normalize_whitespace,
    parse_ra_dec_to_degrees,
    stable_sort_numeric_strings,
    unique_preserve_order,
)

DEFAULT_OBSERVED_DISTANCE_THRESHOLD_ARCSEC = 30.0
DEFAULT_OBSERVED_FOV_THRESHOLD_ARCSEC = 100.0
ARRAY_ORDER = ("12m", "7m", "TP")

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


def get_output_columns(species: Any) -> list[str]:
    """Return the exported column order for a specific observed-species label.

    Parameters
    ----------
    species : Any
        User-supplied species name, for example ``"CO"`` or ``"HCN"``.

    Returns
    -------
    list[str]
        Public CSV columns in the exact order used for export, with the final
        internal flag column renamed to the user-facing label.
    """
    return [
        observed_species_column_name(species) if column == INTERNAL_OBSERVED_COLUMN else column
        for column in INTERNAL_OUTPUT_COLUMNS
    ]


def compute_observed_species_flag(
    target_lines: Any,
    distance_arcsec: Any,
    fov_arcsec: Any,
    observed_species: Any,
    observed_distance_threshold_arcsec: float,
    observed_fov_threshold_arcsec: float,
) -> float:
    """Compute the internal observed-species score for one result row.

    The internal score is later converted to a simple ``Yes`` or ``No`` in the
    exported CSV. A positive value means the selected species is considered
    observed for that source. The score values are:

    - ``1.0`` when the inferred line is present and the ALMA pointing is within
      the distance threshold.
    - ``0.5`` when the inferred line is present, the pointing is farther away,
      but the field of view is large enough to still count as coverage.
    - ``0.0`` otherwise.

    Parameters
    ----------
    target_lines : Any
        Comma-separated inferred line names for the row.
    distance_arcsec : Any
        Angular separation between the input target and ALMA pointing center.
    fov_arcsec : Any
        Approximate ALMA field of view in arcseconds.
    observed_species : Any
        Species to test, such as ``"CO"`` or ``"HCN"``.
    observed_distance_threshold_arcsec : float
        Distance threshold for a definite match.
    observed_fov_threshold_arcsec : float
        FOV threshold for the looser coverage case.

    Returns
    -------
    float
        Internal score used during post-processing.
    """
    if not has_observed_species_line(target_lines, observed_species):
        return 0.0

    try:
        distance_value = float(distance_arcsec)
    except (TypeError, ValueError):
        return 0.0

    if distance_value < observed_distance_threshold_arcsec:
        return 1.0

    try:
        fov_value = float(fov_arcsec)
    except (TypeError, ValueError):
        return 0.0

    if (
        distance_value >= observed_distance_threshold_arcsec
        and fov_value > observed_fov_threshold_arcsec
    ):
        return 0.5
    return 0.0


def observed_species_flag_to_label(value: Any) -> str:
    """Convert an internal observed-species score into a CSV label.

    Parameters
    ----------
    value : Any
        Numeric score produced by :func:`compute_observed_species_flag`.

    Returns
    -------
    str
        ``"Yes"`` when the score is greater than zero, otherwise ``"No"``.
    """
    try:
        return "Yes" if float(value) > 0 else "No"
    except (TypeError, ValueError):
        return "No"


def build_no_match_row(input_name: str, input_ra_deg: float, input_dec_deg: float) -> dict[str, Any]:
    """Create a placeholder row for a target with no returned ALMA matches.

    Parameters
    ----------
    input_name : str
        Original target name from the input catalog.
    input_ra_deg : float
        Input right ascension in decimal degrees.
    input_dec_deg : float
        Input declination in decimal degrees.

    Returns
    -------
    dict[str, Any]
        Output row with coordinate fields filled and science metadata set to
        missing values.
    """
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
    """Normalize a tabular input catalog into ``Name``, ``ra_deg``, ``dec_deg``.

    Supported schemas are:

    - ``Name, ra_deg, dec_deg`` for decimal-degree coordinates.
    - ``Name, ra, dec`` for sexagesimal or decimal text coordinates.

    Parameters
    ----------
    df : pandas.DataFrame
        Raw table read from a CSV-like input file.

    Returns
    -------
    pandas.DataFrame
        Normalized target table with decimal-degree coordinates.

    Raises
    ------
    ValueError
        If the required columns are missing or any coordinate row cannot be
        parsed.
    """
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
    """Load targets from a plain-text coordinate list.

    Each non-comment line must have the form ``Name,RA DEC`` where the
    coordinate tokens can be decimal degrees or sexagesimal text.

    Parameters
    ----------
    path : str
        Path to the plain-text input file.

    Returns
    -------
    pandas.DataFrame
        Normalized target table with columns ``Name``, ``ra_deg``, and
        ``dec_deg``.

    Raises
    ------
    ValueError
        If any line cannot be parsed into a valid name and coordinate pair.
    """
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


def load_targets(path: str, logger: Any | None = None) -> pd.DataFrame:
    """Load a target catalog from CSV-like or plain-text input.

    The function first attempts structured CSV parsing. If that fails, it falls
    back to the plain-text parser used for line-based coordinate lists.

    Parameters
    ----------
    path : str
        Input file path.
    logger : Any | None, optional
        Optional logger used to report fallback decisions.

    Returns
    -------
    pandas.DataFrame
        Normalized target catalog in decimal degrees.
    """
    input_path = Path(path)

    try:
        df = pd.read_csv(path)
        return load_targets_from_table(df)
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError, ValueError):
        if logger is not None:
            logger.debug("Falling back to plain-text target parsing for %s", input_path)

    if input_path.suffix.lower() not in {".txt", ".dat", ".list", ".csv"} and logger is not None:
        logger.debug("Attempting plain-text parse for unsupported extension %s", input_path.suffix)

    return load_targets_from_text(path)


def combine_arrays(values: Sequence[str]) -> str:
    """Combine classified array labels into the canonical order.

    Parameters
    ----------
    values : sequence[str]
        Array classifications such as ``"12m"``, ``"7m"``, or comma-separated
        combinations from multiple rows.

    Returns
    -------
    str
        Unique array labels joined in ``12m,7m,TP`` order.
    """
    flattened: list[str] = []
    for value in values:
        if is_blank(value):
            continue
        flattened.extend(part.strip() for part in str(value).split(",") if part.strip())
    unique = unique_preserve_order(flattened)
    ordered = [array for array in ARRAY_ORDER if array in unique]
    return ",".join(ordered)


def combine_bands(values: Sequence[Any]) -> str:
    """Combine ALMA band metadata into a sorted comma-separated string.

    Parameters
    ----------
    values : sequence[Any]
        Raw ``band_list`` field values, potentially containing repeated values
        or multiple delimiters.

    Returns
    -------
    str
        Unique bands sorted numerically when possible.
    """
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
    """Combine inferred line labels from multiple rows.

    Parameters
    ----------
    values : sequence[str]
        Comma-separated line lists, often from multiple observations being
        merged into one output row.

    Returns
    -------
    str
        Unique line names in first-seen order. Returns ``"Unknown"`` only when
        no explicit line name is available but at least one source row was
        marked as unknown.
    """
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
    """Convert blank strings to :data:`pandas.NA`.

    Parameters
    ----------
    value : Any
        Scalar value to normalize.

    Returns
    -------
    Any
        ``pandas.NA`` for empty strings, otherwise the original value.
    """
    if isinstance(value, str) and not value.strip():
        return pd.NA
    return value


def finalize_results(
    df: pd.DataFrame,
    observed_species: Any = DEFAULT_OBSERVED_SPECIES,
    observed_distance_threshold_arcsec: float = DEFAULT_OBSERVED_DISTANCE_THRESHOLD_ARCSEC,
    observed_fov_threshold_arcsec: float = DEFAULT_OBSERVED_FOV_THRESHOLD_ARCSEC,
) -> pd.DataFrame:
    """Apply final cleanup and derive the observed-species flag column.

    Parameters
    ----------
    df : pandas.DataFrame
        Intermediate result table using the internal schema.
    observed_species : Any, optional
        Species used for the final observed-in-ALMA decision.
    observed_distance_threshold_arcsec : float, optional
        Distance threshold for a definite observed flag.
    observed_fov_threshold_arcsec : float, optional
        FOV threshold for the looser observed flag.

    Returns
    -------
    pandas.DataFrame
        Cleaned result table with normalized missing values and a groupwise
        observed-species score propagated across rows with the same source
        ``Name``.
    """
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
            observed_distance_threshold_arcsec=observed_distance_threshold_arcsec,
            observed_fov_threshold_arcsec=observed_fov_threshold_arcsec,
        ),
        axis=1,
    )
    output[INTERNAL_OBSERVED_COLUMN] = output.groupby("Name", dropna=False)[INTERNAL_OBSERVED_COLUMN].transform("max")
    return output


def select_cleaner_rows(
    df: pd.DataFrame,
    observed_species: Any = DEFAULT_OBSERVED_SPECIES,
    max_observed_rows_per_name: int = 5,
) -> pd.DataFrame:
    """
    Reduce the final table to a smaller human-review subset.

    Rules
    -----
    - Keep one unmatched row when a source has no ALMA match.
    - Keep up to ``max_observed_rows_per_name`` closest rows when the selected
      observed species exists.
    - Otherwise keep the single closest row for that source.

    Parameters
    ----------
    df : pandas.DataFrame
        Finalized result table.
    observed_species : Any, optional
        Species used to decide whether a source has relevant rows.
    max_observed_rows_per_name : int, optional
        Maximum number of closest species-matching rows to keep per source.

    Returns
    -------
    pandas.DataFrame
        Filtered table sorted by source name and distance.
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


def deduplicate_results(
    df: pd.DataFrame,
    dedup_level: str,
    observed_species: Any = DEFAULT_OBSERVED_SPECIES,
    observed_distance_threshold_arcsec: float = DEFAULT_OBSERVED_DISTANCE_THRESHOLD_ARCSEC,
    observed_fov_threshold_arcsec: float = DEFAULT_OBSERVED_FOV_THRESHOLD_ARCSEC,
) -> pd.DataFrame:
    """Deduplicate raw result rows before final export.

    Parameters
    ----------
    df : pandas.DataFrame
        Raw per-observation result rows in the internal schema.
    dedup_level : str
        Deduplication mode. Supported values are ``"none"``, ``"project"``,
        and ``"project_target"``.
    observed_species : Any, optional
        Species used for the final observed-species flag.
    observed_distance_threshold_arcsec : float, optional
        Distance threshold for a definite observed flag.
    observed_fov_threshold_arcsec : float, optional
        FOV threshold for the looser observed flag.

    Returns
    -------
    pandas.DataFrame
        Deduplicated and finalized output rows.

    Raises
    ------
    ValueError
        If ``dedup_level`` is not one of the supported values.
    """
    if df.empty or dedup_level == "none":
        return finalize_results(
            df,
            observed_species=observed_species,
            observed_distance_threshold_arcsec=observed_distance_threshold_arcsec,
            observed_fov_threshold_arcsec=observed_fov_threshold_arcsec,
        )

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

        if is_blank(best.get("proposal_title")):
            candidates = [normalize_whitespace(v) for v in group["proposal_title"].tolist()]
            for candidate in candidates:
                if candidate:
                    best["proposal_title"] = candidate
                    break

        grouped_rows.append(best)

    return finalize_results(
        pd.DataFrame(grouped_rows, columns=INTERNAL_OUTPUT_COLUMNS),
        observed_species=observed_species,
        observed_distance_threshold_arcsec=observed_distance_threshold_arcsec,
        observed_fov_threshold_arcsec=observed_fov_threshold_arcsec,
    )


def write_csv(df: pd.DataFrame, path: str, observed_species: Any = DEFAULT_OBSERVED_SPECIES) -> None:
    """Write the public CSV output file.

    Parameters
    ----------
    df : pandas.DataFrame
        Final result table in the internal schema.
    path : str
        Destination CSV file path.
    observed_species : Any, optional
        Species name used to label the final ``Observed ... in ALMA?`` column.
    """
    output = df.copy()
    for column in INTERNAL_OUTPUT_COLUMNS:
        if column not in output.columns:
            output[column] = pd.NA

    output = output.loc[:, INTERNAL_OUTPUT_COLUMNS]
    output[INTERNAL_OBSERVED_COLUMN] = output[INTERNAL_OBSERVED_COLUMN].map(observed_species_flag_to_label)
    output = output.rename(columns={INTERNAL_OBSERVED_COLUMN: observed_species_column_name(observed_species)})
    output["_distance_sort"] = pd.to_numeric(output["distance_arcsec"], errors="coerce")
    output = output.sort_values(by=["Name", "_distance_sort"], ascending=[True, True], kind="stable", na_position="last")
    output = output.drop(columns=["_distance_sort"])
    output.to_csv(path, index=False, na_rep="NaN")

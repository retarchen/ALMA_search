"""Shared utility helpers for ALMA archive search workflows.

These helpers are intentionally small and reusable. They normalize missing
values, parse coordinate strings, and combine repeated metadata values into
stable CSV-friendly text.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Sequence

import pandas as pd


def configure_logging(verbose: bool) -> None:
    """Configure the package-wide logging format and level.

    Parameters
    ----------
    verbose : bool
        When ``True``, enable debug logging. Otherwise use info-level logging.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def safe_get(record: dict[str, Any], key: str, default: Any = "") -> Any:
    """Read a dictionary-like value while normalizing null-like entries.

    Parameters
    ----------
    record : dict[str, Any]
        Mapping to read from.
    key : str
        Key to retrieve.
    default : Any, optional
        Fallback value used when the key is missing or null-like.

    Returns
    -------
    Any
        Stored value or the supplied default.
    """
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
    """Return whether a value should be treated as missing text/data.

    Parameters
    ----------
    value : Any
        Value to test.

    Returns
    -------
    bool
        ``True`` for ``None``, pandas missing values, and empty strings.
    """
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
    """Collapse repeated whitespace in a scalar value.

    Parameters
    ----------
    value : Any
        Value to normalize.

    Returns
    -------
    str
        String with internal whitespace collapsed to single spaces, or an empty
        string when the value is blank.
    """
    if is_blank(value):
        return ""
    return " ".join(str(value).split())


def unique_preserve_order(items: Iterable[str]) -> list[str]:
    """Return unique items while preserving first-seen order.

    Parameters
    ----------
    items : iterable[str]
        Candidate string values.

    Returns
    -------
    list[str]
        Non-blank unique values in their original encounter order.
    """
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
    """Sort string values numerically when possible, otherwise lexically.

    Parameters
    ----------
    values : iterable[str]
        String values to sort.

    Returns
    -------
    list[str]
        Unique values sorted with numeric strings before non-numeric ones.
    """
    unique_values = unique_preserve_order(str(v) for v in values if str(v).strip())

    def sort_key(item: str) -> tuple[int, float | str]:
        try:
            return (0, float(item))
        except ValueError:
            return (1, item)

    return sorted(unique_values, key=sort_key)


def parse_ra_dec_to_degrees(ra_value: Any, dec_value: Any) -> tuple[float, float]:
    """Parse RA and Dec values into decimal degrees.

    Parameters
    ----------
    ra_value : Any
        Right ascension value in decimal degrees or sexagesimal text.
    dec_value : Any
        Declination value in decimal degrees or sexagesimal text.

    Returns
    -------
    tuple[float, float]
        Parsed ``(ra_deg, dec_deg)`` pair.

    Raises
    ------
    ValueError
        If either coordinate is blank or cannot be parsed.
    """
    if is_blank(ra_value) or is_blank(dec_value):
        raise ValueError("RA/Dec values must not be blank")

    ra_text = str(ra_value).strip()
    dec_text = str(dec_value).strip()

    try:
        return float(ra_text), float(dec_text)
    except ValueError:
        pass

    import astropy.units as u
    from astropy.coordinates import SkyCoord

    coord = SkyCoord(ra_text, dec_text, unit=(u.hourangle, u.deg), frame="icrs")
    return float(coord.ra.deg), float(coord.dec.deg)


def format_ra_dec_strings(ra_deg: float, dec_deg: float) -> tuple[str, str]:
    """Format decimal-degree coordinates as sexagesimal strings.

    Parameters
    ----------
    ra_deg : float
        Right ascension in decimal degrees.
    dec_deg : float
        Declination in decimal degrees.

    Returns
    -------
    tuple[str, str]
        ``(ra_text, dec_text)`` formatted with colon separators.
    """
    import astropy.units as u
    from astropy.coordinates import SkyCoord

    coord = SkyCoord(ra_deg * u.deg, dec_deg * u.deg, frame="icrs")
    ra_text = coord.ra.to_string(unit=u.hour, sep=":", precision=2, pad=True)
    dec_text = coord.dec.to_string(unit=u.deg, sep=":", precision=2, pad=True, alwayssign=True)
    return str(ra_text), str(dec_text)


def to_optional_float(value: Any, scale: float = 1.0, digits: int = 3) -> float | pd.NA:
    """Convert a scalar to a rounded float when possible.

    Parameters
    ----------
    value : Any
        Input value to convert.
    scale : float, optional
        Multiplicative scale factor applied before rounding.
    digits : int, optional
        Number of decimal places to keep.

    Returns
    -------
    float | pandas.NA
        Rounded float result, or ``pandas.NA`` when conversion fails.
    """
    if is_blank(value):
        return pd.NA
    try:
        return round(float(value) * scale, digits)
    except (TypeError, ValueError):
        return pd.NA


def format_float_text(value: Any, digits: int = 3) -> str:
    """Format a scalar value as compact text for merged CSV fields.

    Parameters
    ----------
    value : Any
        Input scalar value.
    digits : int, optional
        Number of decimal places used when formatting numeric values.

    Returns
    -------
    str
        Blank string for missing input, a cleaned text value for non-numeric
        input, or a trimmed numeric string.
    """
    if is_blank(value):
        return ""
    try:
        number = round(float(value), digits)
    except (TypeError, ValueError):
        return normalize_whitespace(value)
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def combine_scalar_values(values: Sequence[Any], digits: int = 3) -> str | pd.NA:
    """Combine repeated scalar values into a unique CSV-friendly string.

    Parameters
    ----------
    values : sequence[Any]
        Scalar values collected across rows.
    digits : int, optional
        Number of decimal places for numeric formatting.

    Returns
    -------
    str | pandas.NA
        Comma-separated unique values, or ``pandas.NA`` when nothing usable is
        available.
    """
    formatted = unique_preserve_order(
        format_float_text(value, digits=digits)
        for value in values
        if not is_blank(value) and format_float_text(value, digits=digits)
    )
    if not formatted:
        return pd.NA
    return ",".join(formatted)

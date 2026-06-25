"""Shared utility helpers for ALMA archive search workflows."""

from __future__ import annotations

import logging
from typing import Any, Iterable, Sequence

import pandas as pd


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

    import astropy.units as u
    from astropy.coordinates import SkyCoord

    coord = SkyCoord(ra_text, dec_text, unit=(u.hourangle, u.deg), frame="icrs")
    return float(coord.ra.deg), float(coord.dec.deg)


def format_ra_dec_strings(ra_deg: float, dec_deg: float) -> tuple[str, str]:
    """Format RA/Dec in sexagesimal strings using colon separators."""
    import astropy.units as u
    from astropy.coordinates import SkyCoord

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

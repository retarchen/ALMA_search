"""Command-line entry point for ALMA Nearby Search."""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Sequence

import pandas as pd

from .io import (
    DEFAULT_OBSERVED_DISTANCE_THRESHOLD_ARCSEC,
    DEFAULT_OBSERVED_FOV_THRESHOLD_ARCSEC,
    INTERNAL_OUTPUT_COLUMNS,
    build_no_match_row,
    deduplicate_results,
    load_targets,
    select_cleaner_rows,
    write_csv,
)
from .lines import DEFAULT_OBSERVED_SPECIES
from .search import DEFAULT_LINE_TOLERANCE_KMS, DEFAULT_RADIUS_ARCMIN, create_tap_service, query_alma_cone, rows_from_query_results
from .utils import configure_logging

LOGGER = logging.getLogger("alma_nearby_search")


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
        "--observed-distance-threshold-arcsec",
        type=float,
        default=DEFAULT_OBSERVED_DISTANCE_THRESHOLD_ARCSEC,
        help=(
            "Distance threshold in arcsec for assigning a value of 1 to the observed-species flag. "
            f"Default: {DEFAULT_OBSERVED_DISTANCE_THRESHOLD_ARCSEC}"
        ),
    )
    parser.add_argument(
        "--observed-fov-threshold-arcsec",
        type=float,
        default=DEFAULT_OBSERVED_FOV_THRESHOLD_ARCSEC,
        help=(
            "FOV threshold in arcsec for assigning a value of 0.5 when outside the distance threshold. "
            f"Default: {DEFAULT_OBSERVED_FOV_THRESHOLD_ARCSEC}"
        ),
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
    if args.observed_distance_threshold_arcsec < 0:
        LOGGER.error("--observed-distance-threshold-arcsec must be non-negative")
        return 1
    if args.observed_fov_threshold_arcsec < 0:
        LOGGER.error("--observed-fov-threshold-arcsec must be non-negative")
        return 1
    if args.cleaner_max_observed_rows_per_name <= 0:
        LOGGER.error("--cleaner-max-observed-rows-per-name must be positive")
        return 1

    try:
        targets = load_targets(args.input_csv, logger=LOGGER)
    except Exception as exc:
        LOGGER.error("Failed to load input targets: %s", exc)
        return 1

    try:
        service = create_tap_service()
    except Exception as exc:
        LOGGER.error("Failed to initialize ALMA TAP service: %s", exc)
        return 1

    all_rows: list[dict[str, object]] = []
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
            observed_distance_threshold_arcsec=float(args.observed_distance_threshold_arcsec),
            observed_fov_threshold_arcsec=float(args.observed_fov_threshold_arcsec),
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

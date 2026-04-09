# ALMA Nearby Search

`alma_nearby_search.py` searches the ALMA archive around a list of sky positions using the ALMA TAP service and writes the results to a CSV.

It is designed for small target catalogs where you want to check whether nearby ALMA observations exist, what bands/arrays were used, and whether common CO lines are covered.

## Requirements

- Python 3
- `pyvo`
- `astropy`
- `pandas`

Install with:

```bash
pip install pyvo astropy pandas
```

## Input Formats

The script accepts either:

1. A CSV with degree columns:

```csv
Name,ra_deg,dec_deg
TargetA,83.6331,-5.3911
TargetB,150.025,-34.433
```

2. A CSV with sexagesimal columns:

```csv
Name,ra,dec
TargetA,04:49:26.41,-69:12:03.77
TargetB,05:24:15.77,-71:58:00.70
```

3. A plain text file with one source per line:

```text
J044926-691203,04:49:26.41 -69:12:03.77
J052415-715800,05:24:15.77 -71:58:00.70
```

## Basic Usage

Run from this directory with your Python environment:

```bash
python alma_nearby_search.py input.csv output.csv
```

## Important Defaults

- Search radius: `5` arcmin
- Deduplication level: `project_target`
- Line velocity tolerance: `350 km/s`

You can override them, for example:

```bash
python alma_nearby_search.py input.csv output.csv --radius-arcmin 3
```

```bash
python alma_nearby_search.py input.csv output.csv --dedup-level none
```

```bash
python alma_nearby_search.py input.csv output.csv --verbose
```

## What The Script Does

For each input target, the script:

1. Queries `ivoa.obscore` through the ALMA TAP service.
2. Searches for observations within a cone around the target.
3. Recomputes the target-to-observation separation with `astropy`.
4. Parses ALMA spectral coverage from `frequency_support` when available.
5. Infers likely lines from a built-in line catalog.
6. Classifies the array as `12m`, `7m`, and/or `TP`.
7. Writes one row per surviving match after deduplication.

If a target has no ALMA observation within the search radius, the script still writes one row for that source with ALMA-specific fields set to `NaN`.

## Output Columns

The current output CSV contains:

- `Name`
- `ra`
- `dec`
- `project_code`
- `alma_target_name`
- `alma_ra`
- `alma_dec`
- `distance_arcsec`
- `fov_arcsec`
- `observing_band`
- `telescope`
- `target_lines`
- `spectral_resolution_khz`
- `velocity_resolution_kms`
- `sensitivity_10kms_mjy_beam`
- `proposal_title`
- `Observed CO in ALMA?`

## Meaning Of `Observed CO in ALMA?`

This flag is assigned at the source level, so all rows with the same `Name` share the same final value:

- `1` if a CO line is present and at least one matching row is within `30` arcsec
- `0.5` if no `1` exists, but a CO line is present and at least one matching row has `distance_arcsec >= 30` and `fov_arcsec > 100`
- `0` otherwise

If both `1` and `0.5` conditions appear for the same source, the final source-level value is `1`.

## Deduplication Options

Available choices:

- `--dedup-level none`
- `--dedup-level project`
- `--dedup-level project_target`

Default:

```bash
--dedup-level project_target
```

This helps reduce repeated rows caused by multiple spectral windows or execution blocks within the same ALMA project.

## Notes

- ALMA metadata can contain multiple spectral resolutions or sensitivities for the same grouped result, so some output fields may contain comma-separated values.
- `target_lines` is inferred from spectral coverage and is only a practical line-coverage indicator, not a detection claim.
- The script uses archive metadata only and does not scrape rendered webpages.

## Example

```bash
python alma_nearby_search.py alma_targets_coor.txt alma_targets_all.csv --verbose
```

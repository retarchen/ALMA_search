# ALMA Nearby Search

ALMA Nearby Search queries the ALMA archive around a list of sky positions and writes the matching observations to a CSV table.

It is aimed at small target catalogs where you want to quickly check:

- whether nearby ALMA observations exist
- which bands and arrays were used
- whether common spectral lines such as CO or HCN are covered

## Current Repository Status

This repository currently contains:

- the package implementation under `src/alma_search/`
- a top-level compatibility launcher: `alma_nearby_search.py`
- a packaging outline in `structure.txt`

The package naming convention is:

- PyPI project name: `alma-search`
- Python import package: `alma_search`
- command-line name: `alma-search`

Important: Python package folders cannot use `-`, so `src/alma_search/` is correct and `src/alma-search/` is not valid.

## Installation

You can install the package locally from the repository root with:

```bash
pip install -e .
```

This installs the package in editable mode and pulls in the runtime dependencies:

- `pyvo`
- `astropy`
- `pandas`

If you clone the repository:

```bash
git clone https://github.com/retarchen/ALMA_search.git
cd ALMA_search
```

## How To Use It

Right now there are two practical ways to run the tool locally.

### Option 1: Run the main script directly

```bash
python alma_nearby_search.py input.csv output.csv
```

### Option 2: Run through the package module

From the repository root, without installing:

```bash
PYTHONPATH=src python -m alma_search.cli input.csv output.csv
```

or, after installation:

```bash
alma-search input.csv output.csv
```

This runs the package implementation directly.

## Input Formats

The tool accepts either:

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

## Basic Examples

```bash
python alma_nearby_search.py input.csv output.csv
```

```bash
python alma_nearby_search.py input.csv output.csv --radius-arcmin 3
```

```bash
python alma_nearby_search.py input.csv output.csv --dedup-level none
```

```bash
python alma_nearby_search.py input.csv output.csv --observed-species HCN
```

```bash
python alma_nearby_search.py input.csv output.csv --cleaner
```

```bash
PYTHONPATH=src python -m alma_search.cli input.csv output.csv --verbose
```

## Important Defaults

- Search radius: `5` arcmin
- Deduplication level: `project_target`
- Line velocity tolerance: `350 km/s`
- Observed-species flag: `CO`
- Observed-species thresholds: distance `< 30` arcsec for `1`, FOV `> 100` arcsec for `0.5`

## What The Tool Does

For each input target, the tool:

1. Queries `ivoa.obscore` through the ALMA TAP service.
2. Searches for observations within a cone around the target.
3. Recomputes the target-to-observation separation with `astropy`.
4. Parses ALMA spectral coverage from `frequency_support` when available.
5. Infers likely lines from a built-in line catalog.
6. Classifies the array as `12m`, `7m`, and/or `TP`.
7. Writes one row per surviving match after deduplication.

If a target has no ALMA observation within the search radius, the tool still writes one row for that source with ALMA-specific fields set to `NaN`.

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
- `Observed X in ALMA?`

## Meaning Of `Observed X in ALMA?`

The final column name depends on `--observed-species`.

Examples:

- default: `Observed CO in ALMA?`
- custom: `Observed HCN in ALMA?`

This flag is assigned at the source level, so all rows with the same `Name` share the same final value:

- `1` if the selected species is present and at least one matching row is within the distance threshold
- `0.5` if no `1` exists, but the selected species is present and at least one matching row has `distance_arcsec` greater than or equal to the distance threshold and `fov_arcsec` greater than the FOV threshold
- `0` otherwise

If both `1` and `0.5` conditions appear for the same source, the final source-level value is `1`.

Defaults:

- `--observed-distance-threshold-arcsec 30`
- `--observed-fov-threshold-arcsec 100`

For `--observed-species CO`, the matching is intentionally limited to the CO family (`12CO`, `13CO`, `C18O`, `C17O`) and does not count unrelated species such as `H2CO` or `HCO+`.

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

## Cleaner Output Mode

If you want a reduced output table, use:

```bash
python alma_nearby_search.py input.csv output.csv --cleaner
```

Rules in cleaner mode:

- keep one unmatched `NaN` row when a source has no ALMA match
- keep up to 5 closest rows containing the selected observed species for each source
- if the selected observed species is absent, keep the single closest row for that source

You can change that cap with:

```bash
python alma_nearby_search.py input.csv output.csv --cleaner --cleaner-max-observed-rows-per-name 3
```

## Identifiable Lines

The built-in line catalog currently includes the following transitions.

CO family:

- `12CO(1-0)`
- `12CO(2-1)`
- `12CO(3-2)`
- `12CO(4-3)`
- `12CO(6-5)`
- `12CO(7-6)`
- `13CO(1-0)`
- `13CO(2-1)`
- `13CO(3-2)`
- `13CO(4-3)`
- `C18O(1-0)`
- `C18O(2-1)`
- `C18O(3-2)`
- `C18O(4-3)`
- `C17O(1-0)`
- `C17O(2-1)`
- `C17O(3-2)`

Dense gas tracers:

- `HCN(1-0)`
- `HCN(3-2)`
- `HCN(4-3)`
- `HCO+(1-0)`
- `HCO+(3-2)`
- `HCO+(4-3)`
- `HNC(1-0)`
- `HNC(3-2)`
- `HNC(4-3)`
- `N2H+(1-0)`
- `N2H+(3-2)`
- `CS(2-1)`
- `CS(3-2)`
- `CS(5-4)`
- `CS(7-6)`

PDR and diffuse-gas tracers:

- `CN(1-0)`
- `CN(2-1)`
- `CCH(1-0)`
- `CCH(3-2)`

Atomic carbon:

- `[CI](1-0)`
- `[CI](2-1)`

Shock tracers:

- `SiO(2-1)`
- `SiO(5-4)`
- `SiO(8-7)`
- `SO(5_6-4_5)`
- `SO(6_5-5_4)`
- `SO2(11_1,11-10_0,10)`

Chemistry and cold gas:

- `H2CO(3_03-2_02)`
- `H2CO(3_22-2_21)`
- `H2CO(3_21-2_20)`
- `H2CO(2_12-1_11)`
- `NH2D(1_11-1_01)`

Complex and star-forming tracers:

- `CH3OH(5_0-4_0)`
- `CH3OH(2_k-1_k)`
- `CH3CN(12_0-11_0)`

Recombination lines:

- `H30alpha`
- `H40alpha`

Some entries such as `CN`, `CCH`, and `CH3OH(2_k-1_k)` are practical group-center proxies for blended or multi-component spectral complexes.

## Notes

- ALMA metadata can contain multiple spectral resolutions or sensitivities for the same grouped result, so some output fields may contain comma-separated values.
- `target_lines` is inferred from spectral coverage and is only a practical line-coverage indicator, not a detection claim.
- The tool uses archive metadata only and does not scrape rendered webpages.

## Example

```bash
python alma_nearby_search.py alma_targets_coor.txt alma_targets_all.csv --verbose
```

# ALMA Search

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Query the ALMA archive around target sky positions and export nearby
observations to a CSV table.

`alma_search` is a lightweight archive-search package for small target lists.
It helps you check whether ALMA observations exist nearby, which observing
bands and arrays were used, and whether common spectral lines such as CO or
HCN are covered.

## Links

- Source code: https://github.com/retarchen/ALMA_search
- Documentation source: `docs/`
- License: `MIT`

## Installation

Install from PyPI:

```bash
pip install alma_search
```

For local development from this repository:

```bash
pip install -e '.[dev]'
```

## Quick Start

Run the command-line tool after installation:

```bash
alma_search input.csv output.csv
```

Example input in decimal degrees:

```csv
Name,ra_deg,dec_deg
TargetA,83.6331,-5.3911
TargetB,150.025,-34.433
```

Example input in sexagesimal coordinates:

```csv
Name,ra,dec
TargetA,04:49:26.41,-69:12:03.77
TargetB,05:24:15.77,-71:58:00.70
```

Example input in plain text:

```text
J044926-691203,04:49:26.41 -69:12:03.77
J052415-715800,05:24:15.77 -71:58:00.70
```

Useful command examples:

```bash
alma_search input.csv output.csv --radius-arcmin 3
alma_search input.csv output.csv --dedup-level none
alma_search input.csv output.csv --observed-species HCN
alma_search input.csv output.csv --cleaner
alma_search input.csv output.csv --verbose
```

## Output

The output CSV reports source coordinates, nearby ALMA target metadata,
distance from the input position, field of view, observing band, telescope
array, inferred line coverage, and a final `Observed X in ALMA?` column that
is exported as `Yes` or `No`.

By default:

- search radius: `5` arcmin
- deduplication level: `project_target`
- observed species: `CO`
- line velocity tolerance: `350 km/s`

More detailed usage and API documentation are available in `docs/` and in the
generated Sphinx site under `docs/_build/html/`.

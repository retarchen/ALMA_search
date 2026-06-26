Output
======

Output Columns
--------------

The CSV output contains:

- ``Name``
- ``ra``
- ``dec``
- ``project_code``
- ``alma_target_name``
- ``alma_ra``
- ``alma_dec``
- ``distance_arcsec``
- ``fov_arcsec``
- ``observing_band``
- ``telescope``
- ``target_lines``
- ``spectral_resolution_khz``
- ``velocity_resolution_kms``
- ``sensitivity_10kms_mjy_beam``
- ``proposal_title``
- ``Observed X in ALMA?``

Observed Column
---------------

The final column name depends on ``--observed-species``.

Examples:

- ``Observed CO in ALMA?``
- ``Observed HCN in ALMA?``

The exported CSV now writes:

- ``Yes`` if the selected species is covered by at least one matching ALMA
  observation according to the internal threshold logic
- ``No`` otherwise

Internally, the package still uses the original scoring:

- ``1`` for a direct close-enough match
- ``0.5`` for a wider-field match that still covers the source
- ``0`` for no qualifying coverage

Query Failure Behavior
----------------------

If ALMA TAP queries fail because of network or service errors, the current CLI
no longer writes a misleading all-``NaN`` output file for the case where all
targets fail. Instead, it exits with a nonzero status and reports that the
problem is likely environmental rather than a true no-match result.

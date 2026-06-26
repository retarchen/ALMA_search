Usage
=====

Supported Input Formats
-----------------------

The package accepts three input styles.

CSV with decimal degrees:

.. code-block:: text

   Name,ra_deg,dec_deg
   TargetA,83.6331,-5.3911
   TargetB,150.025,-34.433

CSV with sexagesimal coordinates:

.. code-block:: text

   Name,ra,dec
   TargetA,04:49:26.41,-69:12:03.77
   TargetB,05:24:15.77,-71:58:00.70

Plain text with one source per line:

.. code-block:: text

   J044926-691203,04:49:26.41 -69:12:03.77
   J052415-715800,05:24:15.77 -71:58:00.70

Basic Commands
--------------

.. code-block:: bash

   alma_search input.csv output.csv

.. code-block:: bash

   alma_search input.csv output.csv --radius-arcmin 3

.. code-block:: bash

   alma_search input.csv output.csv --dedup-level none

.. code-block:: bash

   alma_search input.csv output.csv --observed-species HCN

.. code-block:: bash

   alma_search input.csv output.csv --cleaner

.. code-block:: bash

   alma_search input.csv output.csv --verbose

Defaults
--------

.. list-table::
   :header-rows: 1

   * - Parameter
     - Default
     - Flag
   * - Search radius
     - ``5`` arcmin
     - ``--radius-arcmin``
   * - Deduplication level
     - ``project_target``
     - ``--dedup-level``
   * - Line velocity tolerance
     - ``350`` km/s
     - ``--line-velocity-tolerance-kms``
   * - Observed species
     - ``CO``
     - ``--observed-species``
   * - Distance threshold
     - ``30`` arcsec
     - ``--observed-distance-threshold-arcsec``
   * - FOV threshold
     - ``100`` arcsec
     - ``--observed-fov-threshold-arcsec``

What ``--verbose`` Does
-----------------------

``--verbose`` enables debug logging. It does not change the science result. It
only prints extra details such as:

- input parsing fallback messages
- exact query submission timing
- full error traces if a TAP query fails

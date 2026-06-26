Examples
========

One-Target Real Sample
----------------------

This repository keeps one small tracked example input file:

- ``examples/alma_target_coor_first1.txt``

and one matching output file generated from that input:

- ``examples/alma_target_result_first1.csv``

The example command is:

.. code-block:: bash

   alma_search examples/alma_target_coor_first1.txt examples/alma_target_result_first1.csv --verbose

Sample input:

.. literalinclude:: ../examples/alma_target_coor_first1.txt
   :language: text

Sample output excerpt:

.. literalinclude:: ../examples/alma_target_result_first1.csv
   :language: text
   :lines: 1-4

The full generated sample file is:

- ``examples/alma_target_result_first1.csv``

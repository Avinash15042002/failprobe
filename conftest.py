"""Make the repository root importable during tests, under any invocation.

The project is installed editable as ``failprobe*`` only (see
``[tool.setuptools.packages.find]``), so the top-level ``api`` and ``cli``
packages are not on ``sys.path`` when the suite is run via the ``pytest``
console script — which, unlike ``python -m pytest``, does not add the current
directory. Inserting the repo root here lets ``import api`` / ``import cli``
resolve in CI (``pytest tests/``) and locally alike.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

"""Pytest config.

`santa` tests import `santa.*` only. Demo tests that still call the v1 prototype
(`src.*`) need `prototype/` on `sys.path` until issues 04/15 fold that code away.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROTOTYPE = Path(__file__).resolve().parent.parent / "prototype"
if str(_PROTOTYPE) not in sys.path:
    sys.path.insert(0, str(_PROTOTYPE))

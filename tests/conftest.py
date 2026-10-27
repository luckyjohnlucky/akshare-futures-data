#!/usr/bin/env python3
"""Shared test fixtures for PVC data collection tests.

All tests must use isolated output directories to never touch
real data files.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

"""Test bootstrap: make the flat project modules importable without installing.

Also pins the two required settings so the suite never depends on the
developer's `.env`. `config` resolves its environment at import time, which is
why this runs before any test module imports it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "sk-test")
os.environ.setdefault("MODEL", "test/model")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

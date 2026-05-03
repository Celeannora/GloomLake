"""Shared pytest configuration.

Adds the script source directories to ``sys.path`` so tests can import the
project's modules using either:

  * Package-style imports (``from scripts.utils.card_lookup import ...``),
    via the repo root being on the path, or
  * Bare module imports (``from synergy_types import ...``), via the
    individual ``scripts/{utils,analysis,cli}`` directories being on the path.

Both forms are used in the existing test suite; without this conftest the
bare-module-import tests fail with ModuleNotFoundError because the modules
were moved into the ``scripts/{utils,analysis,cli}`` subdirectories.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT_PATHS = [
    _REPO_ROOT,
    _REPO_ROOT / "scripts",
    _REPO_ROOT / "scripts" / "utils",
    _REPO_ROOT / "scripts" / "analysis",
    _REPO_ROOT / "scripts" / "cli",
]

for _path in _SCRIPT_PATHS:
    _str = str(_path)
    if _str not in sys.path:
        sys.path.insert(0, _str)

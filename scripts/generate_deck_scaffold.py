#!/usr/bin/env python3
"""Redirect — generate_deck_scaffold.py has moved to scripts/cli/.

Kept in place so existing callers (docs, shortcuts, muscle memory) that
invoke `scripts/generate_deck_scaffold.py` keep working. Prefers the
package import path but falls back to direct file execution if the
`scripts` package is not importable from the current layout.
"""
import runpy
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

if __name__ == "__main__":
    try:
        runpy.run_module("scripts.cli.generate_deck_scaffold", run_name="__main__")
    except ImportError:
        # Package layout unavailable (missing __init__.py, unusual install).
        # Fall back to executing the real file directly.
        _target = _root / "scripts" / "cli" / "generate_deck_scaffold.py"
        if not _target.exists():
            sys.stderr.write(
                f"generate_deck_scaffold shim: cannot locate real script at {_target}\n"
            )
            sys.exit(1)
        runpy.run_path(str(_target), run_name="__main__")

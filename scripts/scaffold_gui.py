#!/usr/bin/env python3
"""Redirect — scaffold_gui.py has moved to the project root."""
import sys
from pathlib import Path

# Add project root to path and run the real GUI
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

if __name__ == "__main__":
    from scaffold_gui import main
    main()

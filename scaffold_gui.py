#!/usr/bin/env python3
"""
scaffold_gui.py — legacy entry point shim.
The real application now lives in src/gui/main_window.py.
Run via: python run.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Delegate entirely to run.py
from run import main

if __name__ == "__main__":
    main()

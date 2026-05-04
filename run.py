#!/usr/bin/env python3
"""
GloomLake — MTG Deck Scaffold Generator
Entry point: python run.py
"""
import sys
from pathlib import Path

# Ensure repo root is on sys.path so `src.*` imports resolve
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from src.gui import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("GloomLake")
    app.setOrganizationName("GloomLake")
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Test script to verify GUI layout changes without launching full GUI
"""
import sys
from PySide6.QtWidgets import QApplication
from scaffold_gui import ScaffoldApp

def test_layout():
    print("Testing GUI layout...")
    
    # Create app without showing window
    app = QApplication(sys.argv)
    
    # Create main window
    win = ScaffoldApp()
    
    # Check widget names and order
    print("\nChecking widget references...")
    
    # Check focus_box exists
    if hasattr(win, 'focus_box'):
        print("[OK] focus_box widget exists")
    else:
        print("[ERROR] focus_box widget not found!")
        
    # Check _focus_char exists  
    if hasattr(win, '_focus_char'):
        print("[OK] _focus_char widget exists")
    else:
        print("[ERROR] _focus_char widget not found!")
        
    # Check mana_orbital exists
    if hasattr(win, 'mana_orbital'):
        print("[OK] mana_orbital widget exists")
    else:
        print("[ERROR] mana_orbital widget not found!")
        
    print("\nLayout test complete.")
    return 0

if __name__ == "__main__":
    sys.exit(test_layout())
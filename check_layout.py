#!/usr/bin/env python3
"""
Check the GUI layout structure
"""
import re

with open('scaffold_gui.py', 'r', encoding='utf-8') as f:
    content = f.read()
    
# Find all CardWidget().add_header calls
pattern = r'CardWidget\(\)\.add_header\("(\d+)", "([^"]+)", "([^"]*)"\)'
matches = re.findall(pattern, content)

print("Current Card Layout Order:")
print("=" * 60)
for num, title, desc in matches:
    print(f"Card {num}: {title}")
    if desc:
        print(f"     Description: {desc}")
    print()

# Also check for the _build_scaffold_tab method to see the order
print("\nChecking layout in _build_scaffold_tab method...")
lines = content.split('\n')
in_scaffold_tab = False
card_order = []
for i, line in enumerate(lines):
    if '_build_scaffold_tab' in line and 'def' in line:
        in_scaffold_tab = True
        print(f"Found _build_scaffold_tab at line {i}")
    elif in_scaffold_tab and 'def ' in line and '_build_scaffold_tab' not in line:
        # Another method starts
        break
    elif in_scaffold_tab and 'CardWidget' in line and 'add_header' in line:
        card_order.append(line.strip())
        
print(f"\nFound {len(card_order)} cards in order:")
for i, card_line in enumerate(card_order):
    print(f"{i+1}. {card_line[:80]}...")
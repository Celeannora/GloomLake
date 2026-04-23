#!/usr/bin/env python3
"""
Fix indentation in scaffold_gui.py
"""
import re

def fix_file():
    with open('scaffold_gui.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Find _build_scaffold_tab method
    fixed_lines = []
    in_method = False
    for i, line in enumerate(lines):
        if '_build_scaffold_tab' in line and 'def' in line:
            in_method = True
            print(f"Found _build_scaffold_tab at line {i+1}")
            fixed_lines.append(line)
        elif in_method and line.strip().startswith('def ') and '_build_scaffold_tab' not in line:
            # Another method starts
            in_method = False
            fixed_lines.append(line)
        elif in_method:
            # Fix indentation - should be 8 spaces for method body
            if line.strip() and not line.startswith(' ' * 8):
                # Check if it's a comment or empty line
                if line.strip().startswith('#') or not line.strip():
                    fixed_lines.append(line)
                else:
                    # Add proper indentation
                    fixed_line = ' ' * 8 + line.lstrip()
                    fixed_lines.append(fixed_line)
                    print(f"Fixed indentation at line {i+1}: {line[:40].strip()}...")
            else:
                fixed_lines.append(line)
        else:
            fixed_lines.append(line)
    
    # Write fixed file
    with open('scaffold_gui.py', 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)
    
    print("Indentation fixed. Please test the file.")

if __name__ == "__main__":
    fix_file()
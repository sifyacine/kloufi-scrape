#!/usr/bin/env python3
"""
Fix import paths in all scrape_details.py files.

This script fixes the incorrect relative path imports for insert2db module.

Problem:
    sys.path.insert(1, '../../../insert2db')  # Relative string - breaks when CWD changes
    from insert_scrape import insert_data_to_es

Solution:
    Since project root is already in sys.path, import directly:
    from insert2db.insert_scrape import insert_data_to_es
"""

import os
import re
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent

def fix_file(filepath: Path) -> bool:
    """Fix the import paths in a single file."""
    try:
        content = filepath.read_text(encoding='utf-8')
        original_content = content
        
        # Pattern 1: Fix broken syntax with extra parenthesis
        # sys.path.insert(0, (os.path.abspath(...) -> sys.path.insert(0, os.path.abspath(...)
        content = re.sub(
            r"sys\.path\.insert\(0, \(os\.path\.abspath\(",
            "sys.path.insert(0, os.path.abspath(",
            content
        )
        
        # Pattern 2: Fix sys.path.append to use insert(0, ...) for priority
        content = re.sub(
            r"sys\.path\.append\(os\.path\.abspath\(",
            "sys.path.insert(0, os.path.abspath(",
            content
        )
        
        # Pattern 3: Fix missing closing parenthesis - match the whole line and fix it
        # Match: sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../'))
        # Replace with properly closed version (5 opening, 5 closing parens needed)
        content = re.sub(
            r"sys\.path\.insert\(0, os\.path\.abspath\(os\.path\.join\(os\.path\.dirname\(__file__\), '([\.\/]+)'\)\)$",
            r"sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '\1')))",
            content,
            flags=re.MULTILINE
        )
        
        # Pattern 4: Remove the incorrect sys.path.insert for insert2db
        content = re.sub(
            r"^\s*sys\.path\.insert\(\d+,\s*['\"](\.\./)*insert2db['\"]\)\s*\n",
            "",
            content,
            flags=re.MULTILINE
        )
        
        # Pattern 5: Fix the import statement
        content = re.sub(
            r"from insert_scrape import insert_data_to_es",
            "from insert2db.insert_scrape import insert_data_to_es",
            content
        )
        
        # Pattern 6: Also fix incorrect import (insert_data_to_es instead of insert_scrape)
        content = re.sub(
            r"from insert_data_to_es import insert_data_to_es",
            "from insert2db.insert_scrape import insert_data_to_es",
            content
        )
        
        if content != original_content:
            filepath.write_text(content, encoding='utf-8')
            return True
        return False
        
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def main():
    """Find and fix all scrape_details.py files."""
    sites_dir = PROJECT_ROOT / "sites"
    
    if not sites_dir.exists():
        print(f"Sites directory not found: {sites_dir}")
        return
    
    # Find all Python files that might have this issue
    patterns = ["scrape_details.py", "main.py"]
    fixed_count = 0
    checked_count = 0
    
    for pattern in patterns:
        for filepath in sites_dir.rglob(pattern):
            checked_count += 1
            relative_path = filepath.relative_to(PROJECT_ROOT)
            
            if fix_file(filepath):
                print(f"✓ Fixed: {relative_path}")
                fixed_count += 1
            else:
                print(f"  Skipped (no changes needed): {relative_path}")
    
    print(f"\n{'='*50}")
    print(f"Summary: Fixed {fixed_count}/{checked_count} files")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()

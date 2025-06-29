#!/usr/bin/env python3
"""Bump minor version for FamilyBot"""

import sys
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

from bump_version import bump_version

if __name__ == "__main__":
    if bump_version("minor"):
        print("Minor version bumped successfully!")
        print("Don't forget to commit the changes:")
        print("   git add pyproject.toml && git commit -m 'bump: minor version'")
    else:
        print("Failed to bump minor version")
        sys.exit(1)

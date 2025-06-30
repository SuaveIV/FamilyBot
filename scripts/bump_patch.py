#!/usr/bin/env python3
"""Bump patch version for FamilyBot"""

import sys
from pathlib import Path
from bump_version import bump_version

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))


if __name__ == "__main__":
    if bump_version("patch"):
        print("Patch version bumped successfully!")
        print("Don't forget to commit the changes:")
        print("   git add pyproject.toml && git commit -m 'bump: patch version'")
    else:
        print("Failed to bump patch version")
        sys.exit(1)

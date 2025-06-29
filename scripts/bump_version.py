#!/usr/bin/env python3
"""
Automatic version bumping script for FamilyBot.

This script can be used as a git pre-commit hook or run manually
to automatically increment version numbers in pyproject.toml.
"""

import re
import sys
from pathlib import Path

def bump_version(version_type="patch"):
    """
    Bump version in pyproject.toml
    
    Args:
        version_type: "major", "minor", or "patch" (default)
    """
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    
    if not pyproject_path.exists():
        print(f"Error: {pyproject_path} not found")
        return False
    
    # Read current content
    content = pyproject_path.read_text(encoding='utf-8')
    
    # Find version line
    version_pattern = r'version = "(\d+)\.(\d+)\.(\d+)"'
    match = re.search(version_pattern, content)
    
    if not match:
        print("Error: Could not find version in pyproject.toml")
        return False
    
    major, minor, patch = map(int, match.groups())
    
    # Increment based on type
    if version_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif version_type == "minor":
        minor += 1
        patch = 0
    else:  # patch
        patch += 1
    
    new_version = f"{major}.{minor}.{patch}"
    old_version = f"{match.group(1)}.{match.group(2)}.{match.group(3)}"
    
    # Replace version in content
    new_content = re.sub(version_pattern, f'version = "{new_version}"', content)
    
    # Write back to file
    pyproject_path.write_text(new_content, encoding='utf-8')
    
    print(f"Version bumped: {old_version} -> {new_version}")
    
    # Stage the modified file for commit (when run as pre-commit hook)
    import subprocess
    try:
        subprocess.run(['git', 'add', 'pyproject.toml'], check=True, capture_output=True)
        print("[OK] pyproject.toml staged for commit")
    except subprocess.CalledProcessError:
        # Not a git repository or git not available - that's okay for manual runs
        pass
    
    return True

def main():
    """Main function for command line usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Bump FamilyBot version")
    parser.add_argument(
        "type", 
        nargs="?", 
        default="patch",
        choices=["major", "minor", "patch"],
        help="Version component to bump (default: patch)"
    )
    
    args = parser.parse_args()
    
    if bump_version(args.type):
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()

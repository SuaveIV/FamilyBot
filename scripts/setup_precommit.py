#!/usr/bin/env python3
"""
Setup pre-commit hooks for FamilyBot.

This script replaces the old bash-based git hooks with pre-commit,
which provides better VS Code integration and cross-platform support.
"""

import subprocess
import sys
from pathlib import Path

def install_precommit():
    """Install pre-commit hooks"""
    try:
        # Check if we're in a git repository
        subprocess.run(['git', 'rev-parse', '--git-dir'], 
                      check=True, capture_output=True)
    except subprocess.CalledProcessError:
        print("Error: Not in a git repository")
        return False
    
    try:
        # Install pre-commit hooks
        print("Installing pre-commit hooks...")
        result = subprocess.run(['pre-commit', 'install'], 
                               check=True, capture_output=True, text=True)
        print("Pre-commit hooks installed successfully!")
        
        # Show the configuration
        print("\nPre-commit configuration:")
        config_path = Path(".pre-commit-config.yaml")
        if config_path.exists():
            print(f"   Configuration file: {config_path}")
            print("   Hooks configured:")
            print("   - Auto version bump (patch) on every commit")
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"Error installing pre-commit hooks: {e}")
        print("Make sure pre-commit is installed: pip install pre-commit")
        return False
    except FileNotFoundError:
        print("Error: pre-commit command not found")
        print("Install pre-commit first: pip install pre-commit")
        return False

def remove_old_hooks():
    """Remove old bash-based git hooks if they exist"""
    git_dir = Path(".git")
    if not git_dir.exists():
        return
    
    old_hook = git_dir / "hooks" / "pre-commit"
    if old_hook.exists():
        try:
            old_hook.unlink()
            print("Removed old bash-based pre-commit hook")
        except OSError as e:
            print(f"Warning: Could not remove old hook: {e}")

def main():
    """Main setup function"""
    print("Setting up FamilyBot pre-commit hooks...")
    print("   This replaces the old bash-based system with pre-commit")
    print("   for better VS Code integration and reliability.\n")
    
    # Remove old hooks first
    remove_old_hooks()
    
    # Install new pre-commit hooks
    if install_precommit():
        print("\nSetup complete!")
        print("\nHow it works:")
        print("   - Version automatically bumps (patch) on every commit")
        print("   - Works reliably with VS Code and other IDEs")
        print("   - Cross-platform (no bash dependencies)")
        print("\nUsage:")
        print("   - Normal commits: Version bumps automatically")
        print("   - Skip version bump: git commit --no-verify")
        print("   - Manual version bump: python scripts/bump_version.py [major|minor|patch]")
        print("   - Test hooks: pre-commit run --all-files")
        
        return 0
    else:
        print("\nSetup failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Setup Git hooks for automatic version bumping.

This script sets up a pre-commit hook that automatically bumps
the patch version on each commit.
"""

import os
import stat
from pathlib import Path


def setup_pre_commit_hook():
    """Setup the pre-commit hook for automatic version bumping"""

    # Find git directory
    git_dir = Path(".git")
    if not git_dir.exists():
        print("Error: Not in a git repository")
        return False

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)

    pre_commit_hook = hooks_dir / "pre-commit"

    # Create the pre-commit hook script
    hook_content = """#!/bin/bash
# FamilyBot automatic version bumping pre-commit hook

echo "🔄 Auto-bumping version..."

# Run the version bump script
python scripts/bump_version.py patch

# Check if version was bumped
if [ $? -eq 0 ]; then
    echo "✅ Version bumped successfully"
    # Add the updated pyproject.toml to the commit
    git add pyproject.toml
else
    echo "❌ Failed to bump version"
    exit 1
fi
"""

    # Write the hook
    pre_commit_hook.write_text(hook_content, encoding="utf-8")

    # Make it executable
    current_permissions = pre_commit_hook.stat().st_mode
    pre_commit_hook.chmod(current_permissions | stat.S_IEXEC)

    print(f"✅ Pre-commit hook installed at: {pre_commit_hook}")
    print("🔄 Version will now auto-bump on each commit!")

    return True


def setup_manual_scripts():
    """Create convenient scripts for manual version bumping"""

    scripts = {
        "bump_patch.py": "patch",
        "bump_minor.py": "minor",
        "bump_major.py": "major",
    }

    for script_name, version_type in scripts.items():
        script_path = Path("scripts") / script_name

        script_content = f'''#!/usr/bin/env python3
"""Bump {version_type} version for FamilyBot"""

import sys
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

from bump_version import bump_version

if __name__ == "__main__":
    if bump_version("{version_type}"):
        print("✅ {version_type.title()} version bumped successfully!")
        print("💡 Don't forget to commit the changes:")
        print("   git add pyproject.toml && git commit -m 'bump: {version_type} version'")
    else:
        print("❌ Failed to bump {version_type} version")
        sys.exit(1)
'''

        script_path.write_text(script_content, encoding="utf-8")

        # Make executable on Unix systems
        if os.name != "nt":  # Not Windows
            current_permissions = script_path.stat().st_mode
            script_path.chmod(current_permissions | stat.S_IEXEC)

        print(f"✅ Created {script_name}")


def main():
    """Main setup function"""
    print("🚀 Setting up FamilyBot version bumping...")

    # Setup pre-commit hook
    if setup_pre_commit_hook():
        print()

        # Setup manual scripts
        setup_manual_scripts()

        print()
        print("🎉 Setup complete!")
        print()
        print("📋 Available options:")
        print("   • Automatic: Version bumps on every commit (pre-commit hook)")
        print(
            "   • Manual: Run scripts/bump_patch.py, scripts/bump_minor.py, or scripts/bump_major.py"
        )
        print("   • Direct: python scripts/bump_version.py [patch|minor|major]")
        print()
        print("💡 To disable auto-bumping, remove .git/hooks/pre-commit")

    else:
        print("❌ Setup failed")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())

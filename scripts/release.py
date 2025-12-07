#!/usr/bin/env python3
"""
A complete release automation script for FamilyBot.

This script automates the entire release process:
1.  Performs pre-flight checks (clean git state, correct branch).
2.  Bumps the version in pyproject.toml.
3.  Commits, tags, and pushes the changes to GitHub.
4.  Uses the 'gh' CLI to create a GitHub Release with generated notes.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

# --- Configuration ---
PYPROJECT_PATH = Path(__file__).parent.parent / "pyproject.toml"
MAIN_BRANCH = "main"


def run_command(command, check=True, capture=False):
    """Helper to run a shell command and handle errors."""
    print(f"--> Running: {' '.join(command)}")
    try:
        result = subprocess.run(
            command,
            check=check,
            text=True,
            capture_output=capture,
            encoding="utf-8",
        )
        return result
    except FileNotFoundError:
        print(
            f"ERROR: Command '{command[0]}' not found. Is it installed and in your PATH?"
        )
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"ERROR running command: {' '.join(command)}")
        print(e.stderr)
        sys.exit(1)


def pre_flight_checks():
    """Perform checks to ensure the repository is in a clean state for release."""
    print("Performing pre-flight checks...")

    # Check if gh CLI is installed and authenticated
    run_command(["gh", "auth", "status"])

    # Check if we are on the main branch
    git_branch_result = run_command(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture=True
    )
    current_branch = git_branch_result.stdout.strip()
    if current_branch != MAIN_BRANCH:
        print(f"ERROR: You must be on the '{MAIN_BRANCH}' branch to create a release.")
        sys.exit(1)

    # Check if the working directory is clean
    git_status_result = run_command(["git", "status", "--porcelain"], capture=True)
    if git_status_result.stdout:
        print(
            "ERROR: Your working directory is not clean. Please commit or stash your changes."
        )
        sys.exit(1)

    # Check if the local branch is in sync with the remote
    print("Fetching remote to check sync status...")
    run_command(["git", "fetch"])
    git_sync_result = run_command(["git", "status", "-uno"], capture=True)
    if "Your branch is behind" in git_sync_result.stdout:
        print(
            "ERROR: Your local branch is behind the remote. Please pull the latest changes."
        )
        sys.exit(1)

    print("OK: Pre-flight checks passed.")


def get_current_version():
    """Reads the current version from pyproject.toml."""
    content = PYPROJECT_PATH.read_text(encoding="utf-8")
    version_pattern = r'version = "(\d+\.\d+\.\d+)"'
    match = re.search(version_pattern, content)
    if not match:
        print("ERROR: Could not find version in pyproject.toml")
        sys.exit(1)
    return match.group(1)


def bump_version(current_version, version_type):
    """Calculates the next version number."""
    major, minor, patch = map(int, current_version.split("."))
    if version_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif version_type == "minor":
        minor += 1
        patch = 0
    else:  # patch
        patch += 1
    return f"{major}.{minor}.{patch}"


def update_pyproject_file(old_version, new_version):
    """Updates the version in the pyproject.toml file."""
    content = PYPROJECT_PATH.read_text(encoding="utf-8")
    new_content = content.replace(
        f'version = "{old_version}"', f'version = "{new_version}"'
    )
    PYPROJECT_PATH.write_text(new_content, encoding="utf-8")
    print(f"Updated pyproject.toml: {old_version} -> {new_version}")


def main():
    """Main function to orchestrate the release process."""
    parser = argparse.ArgumentParser(description="Create a new release for FamilyBot.")
    parser.add_argument(
        "type",
        choices=["major", "minor", "patch"],
        help="The type of version bump to perform.",
    )
    parser.add_argument(
        "--notes-file",
        type=str,
        help="Path to a file containing custom release notes.",
    )
    args = parser.parse_args()

    pre_flight_checks()

    old_version = get_current_version()
    new_version = bump_version(old_version, args.type)
    tag_name = f"v{new_version}"

    print(f"Preparing new release: {tag_name}")

    update_pyproject_file(old_version, new_version)

    # Commit the version bump
    commit_message = f"chore(release): version {tag_name}"
    run_command(["git", "add", str(PYPROJECT_PATH)])
    run_command(["git", "commit", "-m", commit_message])

    # Create the git tag
    run_command(["git", "tag", "-a", tag_name, "-m", f"Release {tag_name}"])

    # Push the commit and tag
    print("Pushing commit and tag to remote...")
    run_command(["git", "push", "origin", MAIN_BRANCH, "--follow-tags"])

    # Create the GitHub Release
    print("Creating GitHub Release...")
    gh_release_command = ["gh", "release", "create", tag_name]
    if args.notes_file:
        gh_release_command.extend(["--notes-file", args.notes_file])
    else:
        gh_release_command.append("--generate-notes")
    
    run_command(gh_release_command)

    print(f"OK: Successfully created and published release {tag_name}!")


if __name__ == "__main__":
    main()

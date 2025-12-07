# In scripts/check_updates.py

"""
A smart dependency update checker.

This script uses 'uv pip list --outdated' to find available package updates
and categorizes them into MAJOR, MINOR, and PATCH changes to help identify
potentially breaking updates.
"""

import json
import subprocess
import sys

from packaging.version import parse


# ANSI color codes for highlighting
class Colors:
    """ANSI color codes for terminal output."""

    RED = "\033[91m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    RESET = "\033[0m"


def check_package_updates():
    """
    Checks for outdated packages and prints a categorized, color-coded report.
    """
    try:
        # Use 'uv' to get outdated packages in JSON format
        result = subprocess.run(
            ["uv", "pip", "list", "--outdated", "--format=json"],
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        )
        outdated_packages = json.loads(result.stdout)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(
            f"{Colors.RED}❌ Error: Could not run 'uv'. Is it installed and in your PATH?{Colors.RESET}"
        )
        sys.exit(1)
    except json.JSONDecodeError:
        print(
            f"{Colors.RED}❌ Error: Could not parse JSON output from 'uv'.{Colors.RESET}"
        )
        sys.exit(1)

    if not outdated_packages:
        print(f"{Colors.GREEN}✅ All dependencies are up-to-date.{Colors.RESET}")
        return

    print(
        f"{Colors.BLUE}🔄 Found {len(outdated_packages)} outdated packages:{Colors.RESET}"
    )
    print("-" * 60)
    print(f"{'Package':<25} {'Current':<15} {'Latest':<15} {'Change Type':<15}")
    print("-" * 60)

    for pkg in outdated_packages:
        name = pkg["name"]
        current_v = parse(pkg["version"])
        latest_v = parse(pkg["latest_version"])

        if latest_v.major > current_v.major:
            change_type = f"{Colors.RED}MAJOR (Breaking){Colors.RESET}"
        elif latest_v.minor > current_v.minor:
            change_type = f"{Colors.YELLOW}MINOR (Feature){Colors.RESET}"
        else:
            change_type = f"{Colors.GREEN}PATCH (Fix){Colors.RESET}"

        print(f"{name:<25} {str(current_v):<15} {str(latest_v):<15} {change_type}")

    print("-" * 60)
    print(
        "\n💡 To apply safe patch/minor updates, run: {_}just update-deps{_}".format(
            _=Colors.BLUE
        )
    )
    print(
        "   To install a major update, manually edit 'pyproject.toml' and run 'just lock'."
    )
    print(f"{Colors.RESET}")


def main():
    """Script entry point."""
    check_package_updates()


if __name__ == "__main__":
    main()

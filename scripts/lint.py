#!/usr/bin/env python3
"""
Linting script for FamilyBot.

This script runs pylint on the project's Python files with the configured
settings from .pylintrc.
"""

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def write_lint_log(log_file: Path, result: subprocess.CompletedProcess, cmd: list[str]):
    """Write pylint output to a log file."""
    with log_file.open("w", encoding="utf-8") as f:
        f.write(f"Pylint run at {datetime.now(UTC).isoformat()}\n")
        f.write(f"Exit code: {result.returncode}\n")
        f.write(f"Command: {' '.join(cmd)}\n")
        f.write("=" * 80 + "\n\n")

        if result.stdout:
            f.write("STDOUT:\n")
            f.write(result.stdout)
            f.write("\n")

        if result.stderr:
            f.write("STDERR:\n")
            f.write(result.stderr)
            f.write("\n")


def main():
    """Main linting function"""
    print("Running pylint on FamilyBot code...")
    # Get the project root directory
    project_root = Path(__file__).parent.parent

    # Define the directories to lint
    lint_paths = ["src/", "scripts/"]

    # Build the pylint command
    cmd = ["pylint", "--rcfile=.pylintrc", *lint_paths]

    try:
        # Set environment variables to force UTF-8 encoding
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        # Run pylint and capture output with proper encoding
        result = subprocess.run(  # noqa: S603
            cmd,
            cwd=project_root,
            check=False,  # Don't raise exception on non-zero exit
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",  # Replace problematic characters instead of failing
            env=env,
            shell=False,
        )

        # Print output to console
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

        # Create log file if there are issues
        if result.returncode != 0:
            # Create logs directory if it doesn't exist
            logs_dir = project_root / "logs" / "scripts"
            logs_dir.mkdir(parents=True, exist_ok=True)

            # Generate timestamp for log file
            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            log_file = logs_dir / f"pylint_errors_{timestamp}.log"

            write_lint_log(log_file, result, cmd)

        if result.returncode == 0:
            print("\nPylint completed successfully - no issues found!")
        elif result.returncode & 32:
            print(f"\nPylint usage error occurred - log saved to: {log_file}")
            sys.exit(1)
        elif result.returncode & 1:
            print(f"\nPylint found fatal issues - log saved to: {log_file}")
            sys.exit(1)
        elif result.returncode & 2:
            print(f"\nPylint found errors - log saved to: {log_file}")
            sys.exit(1)
        else:
            print(f"\nPylint completed with warnings/suggestions (exit code: {result.returncode})")
            print(f"Log saved to: {log_file}")
            print("Consider addressing the issues above to improve code quality.")

        return result.returncode

    except FileNotFoundError:
        print("Error: pylint not found. Make sure it's installed:")
        print("  pip install pylint")
        print("  or")
        print("  uv add pylint")
        sys.exit(1)
    except (subprocess.SubprocessError, OSError) as e:
        print(f"Error running pylint: {e}")
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())

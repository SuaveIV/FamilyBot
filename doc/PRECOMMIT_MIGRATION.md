# Pre-commit Migration Guide

This document explains the migration from bash-based git hooks to pre-commit for automatic version bumping in FamilyBot.

## What Changed

### Before (Old System)

- Used bash-based git hooks created by `scripts/setup_git_hooks.py`
- Had issues with VS Code integration
- Platform-dependent (bash scripts don't work well on Windows)
- Manual git hook management

### After (New System)

- Uses `pre-commit` Python package for hook management
- Better VS Code and IDE integration
- Cross-platform compatibility
- Configuration-based approach with `.pre-commit-config.yaml`

## Migration Steps

### 1. Install Dependencies

The new system requires `pre-commit` which has been added to `pyproject.toml`:

```bash
pip install -e .
# or
uv sync
```

### 2. Setup Pre-commit Hooks

Run the setup script to install the new hooks:

```bash
python scripts/setup_precommit.py
# or
familybot-setup-precommit
```

This will:

- Remove any old bash-based hooks
- Install pre-commit hooks
- Configure automatic version bumping

### 3. Verify Installation

Test that the hooks are working:

```bash
pre-commit run --all-files
```

## How It Works

### Automatic Version Bumping

- Every commit automatically bumps the patch version
- The modified `pyproject.toml` is automatically staged
- Works reliably with VS Code and other IDEs

### Configuration

The behavior is controlled by `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: version-bump
        name: Auto-bump version
        entry: uv run python scripts/bump_version.py patch
        language: system
        stages: [pre-commit]
        pass_filenames: false
        always_run: true
        verbose: true
```

**Important**: The configuration uses `uv run python` to ensure the script runs in the correct Python environment managed by uv.

## Usage

### Normal Commits

Just commit as usual - version bumping happens automatically:

```bash
git add .
git commit -m "Add new feature"
# Version automatically bumps from 1.0.8 to 1.0.9
```

### Skip Version Bump

To skip version bumping for a specific commit:

```bash
git commit --no-verify -m "Documentation update"
```

### Manual Version Bumping

The existing manual scripts still work:

```bash
# Patch version (1.0.8 → 1.0.9)
python scripts/bump_patch.py

# Minor version (1.0.8 → 1.1.0)
python scripts/bump_minor.py

# Major version (1.0.8 → 2.0.0)
python scripts/bump_major.py

# Direct script with argument
python scripts/bump_version.py major
```

### Test Hooks

To test all pre-commit hooks without making a commit:

```bash
pre-commit run --all-files
```

## Benefits

1. **Better IDE Integration**: Works reliably with VS Code, PyCharm, and other IDEs
2. **Cross-platform**: No bash dependencies, works on Windows, macOS, and Linux
3. **Extensible**: Easy to add more pre-commit checks (linting, formatting, testing)
4. **Reliable**: More robust error handling and execution environment
5. **Standard Tool**: Uses the widely-adopted pre-commit framework

## Troubleshooting

### Pre-commit Not Found

If you get "pre-commit command not found":

```bash
pip install pre-commit
# or
uv add pre-commit
```

### Hooks Not Running

If hooks aren't running automatically:

```bash
pre-commit install
```

### Reset Hooks

To completely reset the pre-commit setup:

```bash
pre-commit uninstall
python scripts/setup_precommit.py
```

## Files Involved

### New Files

- `.pre-commit-config.yaml` - Pre-commit configuration
- `scripts/setup_precommit.py` - Setup script for new system
- `doc/PRECOMMIT_MIGRATION.md` - This documentation

### Modified Files

- `pyproject.toml` - Added pre-commit dependency and setup script
- `scripts/bump_version.py` - Added automatic git staging

### Deprecated Files

- `scripts/setup_git_hooks.py` - No longer needed (kept for reference)

The old bash-based hooks in `.git/hooks/` are automatically removed during migration.

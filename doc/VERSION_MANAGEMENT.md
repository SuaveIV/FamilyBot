# Version Management for FamilyBot

This document explains the automated version bumping system for FamilyBot.

## 🎯 Overview

FamilyBot uses semantic versioning (SemVer) with the format `MAJOR.MINOR.PATCH`:

- **MAJOR**: Breaking changes or significant new features
- **MINOR**: New features that are backward compatible
- **PATCH**: Bug fixes and small improvements

## 🔧 Setup

To enable automatic version bumping, run the setup script:

```bash
python scripts/setup_git_hooks.py
```

This will:

- Install a Git pre-commit hook for automatic patch version bumping
- Create convenient manual bumping scripts
- Set up the complete version management system

## 🚀 Usage Options

### 1. Automatic Version Bumping (Recommended)

Once the Git hook is installed, every commit will automatically bump the patch version:

```bash
git add .
git commit -m "fix: resolve logging import issue"
# 🔄 Auto-bumping version...
# ✅ Version bumped successfully
# Version bumped: 1.0.1 → 1.0.2
```

### 2. Manual Version Bumping

#### Quick Scripts

```bash
# Bump patch version (1.0.1 → 1.0.2)
python scripts/bump_patch.py

# Bump minor version (1.0.1 → 1.1.0)
python scripts/bump_minor.py

# Bump major version (1.0.1 → 2.0.0)
python scripts/bump_major.py
```

#### Direct Script Usage

```bash
# Bump specific version type
python scripts/bump_version.py patch   # Default
python scripts/bump_version.py minor
python scripts/bump_version.py major
```

## 📋 Version Bumping Guidelines

### When to Bump PATCH (1.0.1 → 1.0.2)

- Bug fixes
- Documentation updates
- Code refactoring without behavior changes
- Dependency updates
- Performance improvements

### When to Bump MINOR (1.0.1 → 1.1.0)

- New features that don't break existing functionality
- New API endpoints
- New configuration options
- New plugins or modules

### When to Bump MAJOR (1.0.1 → 2.0.0)

- Breaking changes to existing APIs
- Removal of deprecated features
- Major architectural changes
- Changes that require user intervention

## 🛠️ Configuration

### Disable Automatic Bumping

To disable automatic version bumping:

```bash
rm .git/hooks/pre-commit
```

### Re-enable Automatic Bumping

```bash
python scripts/setup_git_hooks.py
```

### Custom Hook Behavior

The pre-commit hook is located at `.git/hooks/pre-commit` and can be customized:

```bash
#!/bin/bash
# Custom pre-commit hook

echo "🔄 Auto-bumping version..."

# Only bump version for certain commit types
if git diff --cached --name-only | grep -E '\.(py|toml|yml|yaml)$' > /dev/null; then
    python scripts/bump_version.py patch

    if [ $? -eq 0 ]; then
        echo "✅ Version bumped successfully"
        git add pyproject.toml
    else
        echo "❌ Failed to bump version"
        exit 1
    fi
else
    echo "ℹ️  No Python files changed, skipping version bump"
fi
```

## 📊 Version History Tracking

### View Version History

```bash
# See version changes in git log
git log --oneline --grep="bump:"

# See all version tags
git tag -l "v*"
```

### Create Version Tags

```bash
# After bumping version, create a git tag
git tag -a v$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])") -m "Release v$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])")"

# Push tags to remote
git push origin --tags
```

## 🔍 Troubleshooting

### Hook Not Running

- Check if `.git/hooks/pre-commit` exists and is executable
- Verify the hook script has proper permissions: `chmod +x .git/hooks/pre-commit`

### Version Not Updating

- Ensure `pyproject.toml` exists and has the correct format
- Check that the version line matches: `version = "X.Y.Z"`

### Script Errors

- Verify Python 3 is available in your PATH
- Check that the scripts directory is accessible
- Ensure proper file permissions on the bump scripts

## 🎯 Best Practices

1. **Consistent Commit Messages**: Use conventional commit format

    ```text
    feat: add new wishlist filtering
    fix: resolve database connection issue
    docs: update installation guide
    ```

2. **Review Before Committing**: The auto-bump happens before commit, so you can review the version change

3. **Manual Bumps for Releases**: Use manual minor/major bumps for planned releases

4. **Tag Important Versions**: Create git tags for releases

    ```bash
    git tag -a v1.2.0 -m "Release v1.2.0: Major wishlist improvements"
    ```

5. **Document Changes**: Update CHANGELOG.md or release notes for significant versions

## 📝 Integration with CI/CD

The version bumping system integrates well with CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
name: Release
on:
    push:
        tags:
            - "v*"

jobs:
    release:
        runs-on: ubuntu-latest
        steps:
            - uses: actions/checkout@v3
            - name: Get version
              id: version
              run: echo "VERSION=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])")" >> $GITHUB_OUTPUT
            - name: Create Release
              uses: actions/create-release@v1
              with:
                  tag_name: v${{ steps.version.outputs.VERSION }}
                  release_name: FamilyBot v${{ steps.version.outputs.VERSION }}
```

## 🔗 Related Files

- `scripts/bump_version.py` - Core version bumping logic
- `scripts/setup_git_hooks.py` - Git hooks setup
- `scripts/bump_patch.py` - Quick patch version bump
- `scripts/bump_minor.py` - Quick minor version bump
- `scripts/bump_major.py` - Quick major version bump
- `pyproject.toml` - Project configuration with version
- `.git/hooks/pre-commit` - Git pre-commit hook (after setup)

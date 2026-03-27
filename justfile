# FamilyBot Justfile - Cross-platform task runner
# Run `just --list` to see all available commands

# Default recipe - shows help
default:
    @just --list

# === SETUP AND INSTALLATION ===

# Complete setup: create venv, install dependencies, and verify installation
setup:
    @echo "🚀 Setting up FamilyBot development environment..."
    just create-venv
    just install-deps
    just node-deps
    just verify-setup
    @echo "✅ Setup complete! Run 'just run' to start the bot."

# Install Node.js dependencies for linting and formatting
node-deps:
    @echo "📥 Installing Node.js development dependencies..."
    mise exec -- npm install -g markdownlint-cli2 prettier

# Create virtual environment using uv
create-venv:
    @echo "📦 Creating virtual environment with uv..."
    mise exec -- uv venv --clear
    @echo "✅ Virtual environment created at .venv/"

# Install all dependencies in editable mode
install-deps:
    @echo "📥 Installing dependencies from lockfile and project in editable mode..."
    mise exec -- uv pip install -r requirements.txt -e .
    @echo "✅ Dependencies installed."

# Clean reinstall: remove everything and start fresh
reinstall:
    @echo "🧹 Performing clean reinstall..."
    just clean-all
    just setup
    @echo "✅ Clean reinstall complete!"

# Generate a new lockfile from pyproject.toml
lock:
    @echo "🔒 Generating lockfile from pyproject.toml..."
    mise exec -- uv pip compile pyproject.toml --extra dev -o requirements.txt
    @echo "✅ requirements.txt lockfile updated."

# Upgrade all dependencies in the lockfile to the latest safe versions
update-deps:
    @echo "⬆️  Upgrading dependencies to their latest compatible versions (respecting ~=)..."
    mise exec -- uv pip compile pyproject.toml --extra dev --upgrade -o requirements.txt
    @echo "✅ Lockfile updated. Run 'just install-deps' to apply the changes."

# Verify installation is working
verify-setup:
    @echo "🔍 Verifying installation..."
    @echo "Python version:"
    mise exec -- uv run python --version
    @echo "FamilyBot version:"
    mise exec -- uv run python -c "import familybot; print('FamilyBot package loaded successfully')" || echo "⚠️  FamilyBot package not found"
    @echo "✅ Verification complete"

# === RUNNING THE BOT ===

# Run the main bot (recommended method)
run: verify-setup
    @echo "🤖 Starting FamilyBot..."
    @echo "Press Ctrl+C to stop the bot gracefully"
    mise exec -- uv run familybot
    @echo "🛑 FamilyBot stopped"

# Set up browser profile for token sender (first-time setup)
setup-browser:
    @echo "🌐 Setting up browser profile for Steam login..."
    mise exec -- uv run python scripts/setup_browser.py

# Test token extraction functionality
test-token:
    @echo "🔑 Testing token extraction..."
    mise exec -- uv run python scripts/test_token_plugin.py

# Run token diagnostic tool (detailed debugging)
diagnose-token:
    @echo "🔍 Running token diagnostics..."
    mise exec -- uv run python scripts/diagnose_token.py

# Force immediate token update
force-token:
    @echo "🔄 Forcing token update..."
    mise exec -- uv run python scripts/force_token_update.py

# Update Playwright and browser binaries
update-playwright:
    @echo "🎭 Updating Playwright..."
    mise exec -- uv pip install --upgrade playwright
    mise exec -- uv run playwright install chromium
    @echo "✅ Playwright updated"

# Test free games plugin
test-free-games:
    @echo "🎮 Testing free games plugin..."
    mise exec -- uv run python scripts/test_free_games.py

# Run bot with legacy script (backward compatibility)
run-legacy:
    @echo "🤖 Starting FamilyBot using legacy script..."
    @if [ -f "run_bots.ps1" ]; then powershell -ExecutionPolicy Bypass -File run_bots.ps1; elif [ -f "run_bots.sh" ]; then chmod +x run_bots.sh && ./run_bots.sh; else echo "❌ No legacy run script found"; fi

# === CACHE MANAGEMENT ===

# Purge game details cache
purge-cache:
    @echo "🧹 Purging game details cache..."
    mise exec -- uv run python src/familybot/FamilyBot.py --purge-cache
    @echo "✅ Game details cache purged"

# Purge wishlist cache
purge-wishlist:
    @echo "🧹 Purging wishlist cache..."
    mise exec -- uv run python src/familybot/FamilyBot.py --purge-wishlist
    @echo "✅ Wishlist cache purged"

# Purge family library cache
purge-family-library:
    @echo "🧹 Purging family library cache..."
    mise exec -- uv run python src/familybot/FamilyBot.py --purge-family-library
    @echo "✅ Family library cache purged"

# Purge all cache data
purge-all-cache:
    @echo "🧹 Purging ALL cache data..."
    mise exec -- uv run python src/familybot/FamilyBot.py --purge-all
    @echo "✅ All cache data purged"

# Purge price cache (ITAD prices and mappings)
purge-prices:
    @echo "🧹 Purging price cache..."
    mise exec -- uv run python src/familybot/FamilyBot.py --purge-prices
    @echo "✅ Price cache purged"

# Check price cache status (permanent vs TTL-based entries)
check-price-cache:
    @echo "🔍 Checking price cache status..."
    mise exec -- uv run python scripts/check_price_cache.py

# === DATABASE OPERATIONS ===

# Populate database with game data and family information
populate-db:
    @echo "📊 Populating database..."
    mise exec -- uv run python scripts/populate_database.py
    @echo "✅ Database populated"

# Import data from JSON file
import-json *args:
    @echo "📥 Importing JSON data..."
    mise exec -- uv run python scripts/json_database_importer.py {{args}}

# Convert Steamworks JSON to FamilyBot format
convert-json *args:
    @echo "🔄 Converting Steamworks JSON..."
    mise exec -- uv run python scripts/steamworks_json_converter.py {{args}}

# Populate price data (consolidated)
populate-prices *args:
    @echo "💰 Populating price data (consolidated)..."
    mise exec -- uv run python scripts/populate_prices.py {{args}}
    @echo "✅ Price data populated"

# Inspect database structure and contents
inspect-db:
    @echo "🔍 Inspecting database..."
    mise exec -- uv run familybot-inspect-db

# Backup database
backup-db:
    @echo "💾 Backing up database..."
    mise exec -- uv run python scripts/backup_database.py
    @echo "✅ Database backed up"

# Check database integrity
check-db:
    @echo "🩺 Checking database integrity..."
    mise exec -- uv run python scripts/check_db_integrity.py

# Debug deals detection logic
debug-deals:
    @echo "🔍 Debugging deals detection..."
    mise exec -- uv run python scripts/debug_deals.py

# Restore database from a backup (interactive)
restore-db:
    @echo "🔄 Restoring database from backup..."
    mise exec -- uv run python scripts/restore_database.py

# === LINTING AND FORMATTING ===

# Run ruff linter
lint:
    @echo "🔍 Running ruff linter..."
    mise exec -- uv run ruff check src/ scripts/

# Run ruff linter with auto-fix
lint-fix:
    @echo "🔧 Running ruff linter with auto-fix..."
    mise exec -- uv run ruff check --fix src/ scripts/

# Format code with ruff
format:
    @echo "✨ Formatting code with ruff..."
    mise exec -- uv run ruff format src/ scripts/

# Format markdown files with prettier
format-md:
    @echo "📝 Formatting markdown files..."
    mise exec -- npx prettier --write "**/*.md"

# Check code formatting without making changes
format-check:
    @echo "🔍 Checking code formatting..."
    mise exec -- uv run ruff format --check src/ scripts/

# Check markdown formatting without making changes
format-md-check:
    @echo "🔍 Checking markdown formatting..."
    mise exec -- npx prettier --check "**/*.md"

# Run markdown linter
lint-md:
    @echo "🔍 Linting markdown files..."
    mise exec -- npx markdownlint-cli2 "**/*.md"

# Run mypy type checker
type-check:
    @echo "🧐 Running mypy type checker..."
    mise exec -- uv run mypy src/ scripts/

# Run pip-audit for security vulnerabilities
audit:
    @echo "🛡️ Running pip-audit for security vulnerabilities..."
    mise exec -- uv run pip-audit -r requirements.txt

# Lint TOML files
check-toml:
    @echo "🔍 Checking TOML files..."
    mise exec -- uv run tombi lint pyproject.toml

# Format TOML files
format-toml:
    @echo "✨ Formatting TOML files..."
    mise exec -- uv run tombi format pyproject.toml

# Run all code quality checks
check: lint format-check type-check audit check-toml
    @echo "✅ All code quality checks passed!"

# Fix and format all code issues
fix: lint-fix format format-toml
    @echo "✅ Code fixed and formatted!"

# Legacy lint command (for backward compatibility)
lint-legacy:
    @echo "🔍 Running legacy lint script..."
    mise exec -- uv run familybot-lint

# === DEVELOPMENT TASKS ===

# Set up pre-commit hooks
setup-precommit:
    @echo "🪝 Setting up pre-commit hooks..."
    mise exec -- uv run familybot-setup-precommit
    @echo "✅ Pre-commit hooks installed"

# Run pre-commit style checks
pre-commit: check
    @echo "✅ Pre-commit checks completed"

# Create a new release (used by bump-* commands)
release version_type='patch':
    @echo "🚀 Creating a '{{ version_type }}' release..."
    mise exec -- uv run python scripts/release.py '{{ version_type }}'

# Bumps and creates a new patch release (e.g., 1.0.0 -> 1.0.1)
bump-patch:
    @just release 'patch'

# Bumps and creates a new minor release (e.g., 1.0.0 -> 1.1.0)
bump-minor:
    @just release 'minor'

# Bumps and creates a new major release (e.g., 1.0.0 -> 2.0.0)
bump-major:
    @just release 'major'

# Check for outdated Python dependencies
check-updates:
    @echo "🔍 Running smart update checker..."
    mise exec -- uv run python scripts/check_updates.py

# === UTILITY TASKS ===

# View real-time logs
logs:
    @echo "📋 Viewing FamilyBot logs (Ctrl+C to exit)..."
    @if [ -f "logs/familybot.log" ]; then tail -f logs/familybot.log; else echo "❌ Log file not found. Run the bot first."; fi

# View error logs
logs-errors:
    @echo "📋 Viewing error logs (Ctrl+C to exit)..."
    @if [ -f "logs/familybot_errors.log" ]; then tail -f logs/familybot_errors.log; else echo "❌ Error log file not found."; fi

# Check bot status and configuration
status:
    @echo "📊 FamilyBot Status:"
    @echo "==================="
    @echo "Virtual environment: $(if [ -d '.venv' ]; then echo '✅ Present'; else echo '❌ Missing'; fi)"
    @echo "Config file: $(if [ -f 'config.yml' ]; then echo '✅ Present'; else echo '❌ Missing (use config-template.yml)'; fi)"
    @echo "Browser profile: $(if [ -d 'FamilyBotBrowserProfile' ]; then echo '✅ Present'; else echo '❌ Missing (run just setup-browser)'; fi)"
    @echo "Database: $(if [ -f 'bot_data.db' ]; then echo '✅ Present'; else echo '❌ Missing (run just populate-db)'; fi)"

# === CLEANUP TASKS ===

# Clean Python cache files
clean-cache:
    @echo "🧹 Cleaning Python cache files..."
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -name "*.pyc" -delete 2>/dev/null || true
    find . -name "*.pyo" -delete 2>/dev/null || true
    @echo "✅ Python cache cleaned"

# Clean virtual environment
clean-venv:
    @echo "🧹 Removing virtual environment..."
    rm -rf .venv
    @echo "✅ Virtual environment removed"

# Clean logs
clean-logs:
    @echo "🧹 Cleaning log files..."
    rm -rf logs/*.log logs/scripts/*.log 2>/dev/null || true
    @echo "✅ Log files cleaned"

# Clean all generated files
clean-all: clean-cache clean-venv clean-logs
    @echo "🧹 Cleaning all generated files..."
    rm -rf *.egg-info build/ dist/ 2>/dev/null || true
    @echo "✅ All generated files cleaned"

# === MIGRATION HELPERS ===

# Migrate from legacy scripts to just
migrate-from-legacy:
    @echo "🔄 Migration guide from legacy scripts:"
    @echo "======================================"
    @echo "Old command → New command"
    @echo ".\reinstall_bot.ps1 → just reinstall"
    @echo ".\run_bots.ps1 → just run"
    @echo ".\purge_cache.ps1 → just purge-cache"
    @echo ".\purge_all_cache.ps1 → just purge-all-cache"
    @echo "uv run familybot-lint → just lint"
    @echo ""
    @echo "💡 Run 'just --list' to see all available commands"

# Show installation instructions for just
install-just-help:
    @echo "📦 Installing 'just' command runner:"
    @echo "==================================="
    @echo "Windows (Scoop): scoop install just"
    @echo "Windows (Chocolatey): choco install just"
    @echo "Windows (Cargo): cargo install just"
    @echo "macOS (Homebrew): brew install just"
    @echo "Linux (Cargo): cargo install just"
    @echo "Linux (Package manager): Check your distro's package manager"
    @echo ""
    @echo "💡 After installation, run 'just setup' to get started"

# === HELP AND INFORMATION ===

# Show detailed help
help:
    @echo "🤖 FamilyBot Task Runner Help"
    @echo "============================"
    @echo ""
    @echo "Quick Start:"
    @echo "  just setup          # Complete setup"
    @echo "  just run            # Start the bot"
    @echo ""
    @echo "Common Tasks:"
    @echo "  just lint           # Check code quality"
    @echo "  just format         # Format code"
    @echo "  just populate-db    # Set up database"
    @echo "  just purge-cache    # Clear cache"
    @echo ""
    @echo "For full command list: just --list"
    @echo "For migration help: just migrate-from-legacy"
    @echo "For just installation: just install-just-help"

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
    just verify-setup
    @echo "✅ Setup complete! Run 'just run' to start the bot."

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
run: create-venv install-deps
    @echo "🤖 Starting FamilyBot..."
    @echo "Press Ctrl+C to stop the bot gracefully"
    -mise exec -- uv run familybot
    @echo "🛑 FamilyBot stopped"

# Set up browser profile for token sender (first-time setup)
setup-browser:
    @echo "🌐 Setting up browser profile for Steam login..."
    mise exec -- uv run python scripts/setup_browser.py

# Test token extraction functionality
test-token:
    @echo "🔑 Testing token extraction..."
    mise exec -- uv run python scripts/test_token_plugin.py

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

# === DATABASE OPERATIONS ===

# Populate database with game data and family information
populate-db:
    @echo "📊 Populating database..."
    mise exec -- uv run python scripts/populate_database.py
    @echo "✅ Database populated"

# Populate price data (standard mode)
populate-prices:
    @echo "💰 Populating price data (standard mode)..."
    mise exec -- uv run python scripts/populate_prices.py
    @echo "✅ Price data populated"

# Populate price data (optimized mode - 6-10x faster)
populate-prices-fast:
    @echo "💰 Populating price data (optimized mode)..."
    mise exec -- uv run python scripts/populate_prices_optimized.py
    @echo "✅ Price data populated (optimized)"

# Populate price data (async mode - 15-25x faster)
populate-prices-turbo:
    @echo "💰 Populating price data (async turbo mode)..."
    mise exec -- uv run python scripts/populate_prices_async.py
    @echo "✅ Price data populated (turbo)"

# Inspect database structure and contents
inspect-db:
    @echo "🔍 Inspecting database..."
    mise exec -- uv run familybot-inspect-db

# Backup database
backup-db:
    @echo "💾 Backing up database..."
    mise exec -- uv run python scripts/backup_database.py
    @echo "✅ Database backed up"

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

# Check code formatting without making changes
format-check:
    @echo "🔍 Checking code formatting..."
    mise exec -- uv run ruff format --check src/ scripts/

# Run mypy type checker
type-check:
    @echo "🧐 Running mypy type checker..."
    mise exec -- uv run mypy src/ scripts/

# Run security audit for dependencies
audit:
    @echo "🛡️ Running pip-audit for security vulnerabilities..."
    mise exec -- uv run pip-audit -r requirements.txt

# Run all code quality checks
check: lint format-check type-check audit
    @echo "✅ All code quality checks passed!"

# Fix and format all code issues
fix: lint-fix format
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

# Bump version (patch)
bump-patch:
    @echo "📈 Bumping patch version..."
    mise exec -- uv run python scripts/bump_patch.py

# Bump version (minor)
bump-minor:
    @echo "📈 Bumping minor version..."
    mise exec -- uv run python scripts/bump_minor.py

# Bump version (major)
bump-major:
    @echo "📈 Bumping major version..."
    mise exec -- uv run python scripts/bump_major.py

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
    @echo "Database: $(if [ -f 'data/familybot.db' ]; then echo '✅ Present'; else echo '❌ Missing (run just populate-db)'; fi)"

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

# Changelog

## Added

- **CI/CD & Tooling**:
    - Integrated static analysis and CI tools.
    - Added a Justfile for cross-platform task management and setup automation.
    - Implemented a comprehensive version management system.
    - Changed to pre-commit for version bump hooks.
- **Price Population & Deals**:
    - Implemented a cache-then-write pattern for async price population to resolve database concurrency issues.
    - Enhanced price population scripts with performance tiers and optimized processing methods.
    - Implemented an optimized price population script with concurrent processing and adaptive rate limiting.
    - Enhanced rate limiting with retry logic for API requests in the `steam_family` plugin.
    - Integrated Steam WebAPI for enhanced game data retrieval in `populate_database` and `populate_prices` scripts.
    - Added debug scripts for deal detection and detailed wishlist analysis.
    - Added a debug script to investigate database structure and content.
    - Enhanced deal messaging to handle both formatted and unformatted lowest prices.
- **Core Functionality**:
    - Enhanced the `profile` command to support vanity URL resolution with improved handling for Steam community links.
    - Enhanced the `profile` command to support SteamID64 and vanity URL resolution with improved error handling.
    - Added `audioop-lts` dependency to the project.
- **Documentation**:
    - Added a comprehensive Pylint error remediation plan.
    - Enhanced the README with detailed descriptions for scripts and functionalities.
    - Added Steam integration details to third-party attributions.

### Changed

- **Refactoring**:
    - Applied linting fixes and code formatting.
    - Refactored `token_sender` and `api` modules.
    - Reorganized imports and enhanced error handling in `FamilyBot.py`.
    - Improved logging configuration and streamlined log message formatting.
    - Refactored imports across multiple scripts for consistency and clarity.
    - Removed trailing whitespace and enforced consistent formatting across Python files.
- **Price Population & Deals**:
    - Completed Phase 2 ITAD enhancement with Steam library assistance.
    - Completed Phase 1 Steam library price enhancement, including fallback for failed Store API calls, price source tracking, and improved error handling.
    - Removed the limit on games checked for deals in the `steam_family` plugin.
- **Dependencies**:
    - Updated dependencies and enhanced Steam API integration in the `steam_family` plugin.

### Fixed

- **Scripts**:
    - Resolved `justfile` script path and error handling issues.
- **Core Functionality**:
    - Improved error handling in ITAD name search.
- **Versioning**:
    - Bumped version to 1.0.13 and added `pylint` dependency.

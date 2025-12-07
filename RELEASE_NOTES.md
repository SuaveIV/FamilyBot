# FamilyBot v1.13.0

## 🚀 Key Changes

### 🏗️ Architecture: Steam Family Refactor
A major structural overhaul of the Steam Family integration has been completed. The monolithic `steam_family` module has been decomposed into specialized components:
*   **`steam_admin`**: Dedicated to administrative commands and controls.
*   **`steam_tasks`**: Manages background and scheduled processes.
*   **`steam_api_manager`**: Centralized handling of Steam API interactions.
*   **`steam_helpers`**: Shared utility functions.

This refactoring significantly improves code maintainability, reduces complexity, and lays the groundwork for easier future extensions.

### ⚡ Enhancements
*   **Price Accuracy**: Updated IsThereAnyDeal (ITAD) integration to utilize the historical low endpoint, ensuring more relevant price data.
*   **Cache Management**: Adjusted ITAD caching strategies and improved price population scripts (`populate_prices_async.py`, `populate_prices_optimized.py`) for better performance and accuracy.

### 🐛 Bug Fixes
*   **Database**: Fixed an issue where permanent cache entries could be incorrectly purged (`fix(db): protect permanent cache entries from cleanup`).
*   **General**: Various cleanups and fixes following the Steam Family refactor.

## 📜 Commit Log
*   `8f60784` Merge pull request #2 from SuaveIV/refactor-steam-family
*   `8772e81` refactor(prices): update price population scripts for accuracy
*   `0d30eb8` refactor(itad): update to historical low endpoint and adjust cache
*   `793e1b9` fix(db): protect permanent cache entries from cleanup
*   `e74681a` fix(refactor): cleanup steam_family refactor
*   `29335b6` Refactor steam_family to split God Object into smaller modules

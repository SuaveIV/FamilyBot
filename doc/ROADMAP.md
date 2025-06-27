# Project Roadmap for Family Bot

This document outlines the planned future development goals and enhancements for the Family Bot project.

## Completed Goals

### 1. Switch Token Gatherer to Playwright (COMPLETED - 2025-06-27)

* **Goal:** Replaced the Selenium-based token gathering (`getToken.py`) with Playwright.
* **Benefits:** Significantly improved robustness, reliability, and cross-platform compatibility of the token gathering process. Playwright handles browser binary management automatically and offers a more modern asynchronous API.

### 2. Combine Token Gatherer into Main Bot (COMPLETED - 2025-06-27)

* **Goal:** Consolidated the `getToken.py` script's functionality directly into the main `FamilyBot.py` program as a plugin.
* **Benefits:** Simplified overall bot management (single process to start/stop), enabled direct in-memory token transfer (eliminating the need for an internal WebSocket server for this purpose), and enhanced resource efficiency and unified graceful shutdowns.
* **Additional Features:** Added new admin commands (`!force_token`, `!token_status`), enhanced session persistence, and comprehensive documentation/startup script updates.

### 3. Add Web-Based UI (COMPLETED - 2025-06-27)

* **Goal:** Implement a web-based user interface for bot management.
* **Implementation:** Created a comprehensive FastAPI-powered web dashboard with modern Bootstrap/Bootswatch theming.
* **Features Delivered:**
  * **Dashboard**: Real-time bot status monitoring, cache statistics, recent games, family members, and wishlist summary
  * **Log Management**: Advanced log viewer with filtering, search, real-time updates, and export functionality
  * **Configuration Interface**: Current settings overview, plugin status, family member management, and setup help
  * **Theme System**: 16+ Bootswatch themes including comprehensive dark mode support (Darkly, Cyborg, Slate, Solar, Superhero, Vapor)
  * **Cache Control**: Web-based cache management and purge operations
  * **Mobile Responsive**: Fully responsive design that works on desktop, tablet, and mobile devices
* **Technical Stack:** FastAPI backend, Jinja2 templating, Bootstrap 5.3 with Bootswatch themes, responsive JavaScript with localStorage persistence
* **Integration:** Seamlessly integrated into main bot process with configurable host/port settings

## Future Development Goals

### 4. Game Pass and PS+ Integration Plugin

* **Goal:** Develop a new plugin to detect and announce when games are added to Xbox Game Pass and PlayStation Plus.
* **Challenges:** Accessing data for these platforms may require reverse-engineering unofficial APIs (e.g., for Game Pass, leveraging community-made APIs) or implementing web scraping techniques (e.g., for PS+ from community calendars like xfire.com) due to a lack of official public APIs. Web scraping introduces brittleness and requires careful rate-limiting.

### 5. Docker Support for Remote Hosting

* **Goal:** Add Docker support to containerize the bot application.
* **Benefits:** This will encapsulate the application and its dependencies into a portable unit, simplifying deployment to remote servers (VPS, cloud platforms), ensuring consistent execution environments, and streamlining updates.

## Optional Enhancements

### 6. Pylint on GitHub Actions

* **Goal:** Set up automated static code analysis using Pylint on GitHub Actions.
* **Benefits:** This will automatically enforce code quality standards, identify potential bugs and inefficiencies, and ensure code consistency across the project, providing immediate feedback on every push or pull request.
* **Timing:** Can be implemented at almost any point, but is particularly beneficial after major refactorings once the code structure is stable.

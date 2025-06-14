# Project Roadmap for Family Bot

This document outlines the planned future development goals and enhancements for the Family Bot project.

## Future Development Goals

### 1. Switch Token Gatherer to Playwright

* **Goal:** Replace the current Selenium-based token gathering (`getToken.py`) with Playwright.
* **Benefits:** This will significantly improve the robustness, reliability, and cross-platform compatibility of the token gathering process, as Playwright handles browser binary management automatically and offers a more modern asynchronous API.

### 2. Combine Token Gatherer into Main Bot

* **Goal:** Consolidate the `getToken.py` script's functionality directly into the main `FamilyBot.py` program.
* **Benefits:** This architectural improvement will simplify overall bot management (single process to start/stop), enable direct in-memory token transfer (eliminating the need for an internal WebSocket server for this purpose), and enhance resource efficiency and unified graceful shutdowns.

### 3. Add Web-Based UI

* **Goal:** Implement a web-based user interface for bot management.
* **Benefits:** This will provide a centralized dashboard for viewing bot status, logs, configurations, and potentially triggering commands (like `!force_epic`, `!coop`) outside of Discord. This is likely to be implemented using a lightweight Python web framework like Flask.

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

# Third-Party Attributions

This document lists all third-party libraries, frameworks, tools, and resources used in the FamilyBot project. We acknowledge and thank the developers and maintainers of these excellent open-source projects.

## Core Dependencies

### Discord Bot Framework

**[discord-py-interactions](https://github.com/interactions-py/interactions.py)**

- **Description**: Modern, feature-rich Discord bot framework for Python
- **License**: MIT License
- **Usage**: Core Discord bot functionality, command handling, and event management
- **Website**: <https://interactions-py.github.io/interactions.py/>

### Web Framework & Server

**[FastAPI](https://github.com/tiangolo/fastapi)**

- **Description**: Modern, fast web framework for building APIs with Python
- **License**: MIT License
- **Usage**: Web UI backend, REST API endpoints, and async request handling
- **Website**: <https://fastapi.tiangolo.com/>

**[Uvicorn](https://github.com/encode/uvicorn)**

- **Description**: Lightning-fast ASGI server implementation
- **License**: BSD 3-Clause License
- **Usage**: ASGI server for running the FastAPI web application
- **Website**: <https://www.uvicorn.org/>

**[Jinja2](https://github.com/pallets/jinja)**

- **Description**: Modern and designer-friendly templating language for Python
- **License**: BSD 3-Clause License
- **Usage**: HTML template rendering for the Web UI
- **Website**: <https://jinja.palletsprojects.com/>

### Data Validation & Serialization

**[Pydantic](https://github.com/pydantic/pydantic)**

- **Description**: Data validation using Python type hints
- **License**: MIT License
- **Usage**: API data models, configuration validation, and type safety
- **Website**: <https://docs.pydantic.dev/>

### HTTP & Networking

**[Requests](https://github.com/psf/requests)**

- **Description**: Simple, elegant HTTP library for Python
- **License**: Apache License 2.0
- **Usage**: Synchronous HTTP requests to Steam API and other web services
- **Website**: <https://requests.readthedocs.io/>

**[HTTPX](https://github.com/encode/httpx)**

- **Description**: Next generation HTTP client for Python with async support
- **License**: BSD 3-Clause License
- **Usage**: Asynchronous HTTP requests for improved performance
- **Website**: <https://www.python-httpx.org/>

**[WebSockets](https://github.com/python-websockets/websockets)**

- **Description**: Library for building WebSocket servers and clients
- **License**: BSD 3-Clause License
- **Usage**: Internal WebSocket communication between bot components
- **Website**: <https://websockets.readthedocs.io/>

### Browser Automation

**[Playwright](https://github.com/microsoft/playwright-python)**

- **Description**: Cross-browser automation library
- **License**: Apache License 2.0
- **Usage**: Steam token extraction and browser automation
- **Website**: <https://playwright.dev/python/>

**[Selenium](https://github.com/SeleniumHQ/selenium)**

- **Description**: Web browser automation framework
- **License**: Apache License 2.0
- **Usage**: Legacy token extraction (deprecated but preserved)
- **Website**: <https://selenium-python.readthedocs.io/>

**[WebDriver Manager](https://github.com/SergeyPirogov/webdriver_manager)**

- **Description**: Automatic WebDriver management for Selenium
- **License**: Apache License 2.0
- **Usage**: Automatic browser driver downloads and management
- **Website**: <https://pypi.org/project/webdriver-manager/>

### Configuration & Data Processing

**[PyYAML](https://github.com/yaml/pyyaml)**

- **Description**: YAML parser and emitter for Python
- **License**: MIT License
- **Usage**: Configuration file parsing and management
- **Website**: <https://pyyaml.org/>

**[tqdm](https://github.com/tqdm/tqdm)**

- **Description**: Fast, extensible progress bar for Python
- **License**: MIT License
- **Usage**: Progress indicators for long-running operations
- **Website**: <https://tqdm.github.io/>

## Frontend Dependencies (CDN)

### CSS Framework

**[Bootstrap](https://github.com/twbs/bootstrap)**

- **Description**: Popular CSS framework for responsive web development
- **License**: MIT License
- **Usage**: Base CSS framework for the Web UI
- **Website**: <https://getbootstrap.com/>
- **CDN**: <https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/>

**[Bootswatch](https://github.com/thomaspark/bootswatch)**

- **Description**: Free themes for Bootstrap
- **License**: MIT License
- **Usage**: Professional themes for the Web UI including dark mode support
- **Website**: <https://bootswatch.com/>
- **CDN**: <https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/>

### Icons

**[Font Awesome](https://github.com/FortAwesome/Font-Awesome)**

- **Description**: The web's most popular icon set and toolkit
- **License**: Font Awesome Free License (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT)
- **Usage**: Icons throughout the Web UI interface
- **Website**: <https://fontawesome.com/>
- **CDN**: <https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/>

## Development Tools

### Package Management

**[uv](https://github.com/astral-sh/uv)**

- **Description**: Extremely fast Python package installer and resolver
- **License**: Apache License 2.0
- **Usage**: Dependency management and virtual environment creation
- **Website**: <https://github.com/astral-sh/uv>

### Database

**[SQLite](https://www.sqlite.org/)**

- **Description**: Self-contained, serverless SQL database engine
- **License**: Public Domain
- **Usage**: Local database for caching game data, wishlists, and user information
- **Website**: <https://www.sqlite.org/>

## External APIs & Services

### Steam APIs

**[Steam Web API](https://steamcommunity.com/dev)**

- **Description**: Official Steam Web API for accessing Steam data
- **License**: Steam Web API Terms of Use
- **Usage**: Fetching game data, user libraries, wishlists, and family information
- **Website**: <https://steamcommunity.com/dev>

**[Steamworks Web API](https://partner.steamgames.com/doc/webapi_overview)**

- **Description**: Extended Steam API for developers
- **License**: Steamworks SDK Agreement
- **Usage**: Advanced Steam data access and family library management
- **Website**: <https://partner.steamgames.com/>

### Price Tracking

**[IsThereAnyDeal API](https://isthereanydeal.com/)**

- **Description**: Game price tracking and deal aggregation service
- **License**: IsThereAnyDeal Terms of Service
- **Usage**: Historical price data and current deal detection
- **Website**: <https://isthereanydeal.com/>

### Game Information

**[Epic Games Store](https://www.epicgames.com/)**

- **Description**: Digital video game storefront
- **License**: Epic Games Terms of Service
- **Usage**: Free game announcements and promotional data
- **Website**: <https://www.epicgames.com/store/>

## Original Project Attribution

**[FamilyBot by Chachigo](https://github.com/Chachigo/FamilyBot)**

- **Description**: Original FamilyBot Discord bot project
- **License**: Not specified
- **Usage**: Base project structure and core functionality concepts
- **Website**: <https://github.com/Chachigo/FamilyBot>

## License Compatibility

This project is distributed under its own license terms. All third-party dependencies listed above are compatible with our usage:

- **MIT License**: Permissive license allowing commercial and private use
- **BSD 3-Clause License**: Permissive license with attribution requirement
- **Apache License 2.0**: Permissive license with patent protection
- **Public Domain**: No restrictions on use
- **Font Awesome Free License**: Free for commercial and personal use with attribution

## Acknowledgments

We extend our gratitude to:

- The open-source community for creating and maintaining these excellent tools
- The Discord.py community for their continued support and development
- The FastAPI team for their modern, high-performance web framework
- The Bootstrap and Bootswatch teams for their responsive design frameworks
- Steam and Epic Games for providing APIs that enable this bot's functionality
- All contributors and users who help improve this project

## Reporting Issues

If you notice any missing attributions or licensing concerns, please:

1. Create an issue in the project repository
2. Include details about the missing attribution
3. Provide links to the original project or license information

We are committed to properly attributing all third-party code and resources used in this project.

---

**Last Updated**: December 27, 2025
**Project Version**: Latest
**Maintainer**: FamilyBot Development Team

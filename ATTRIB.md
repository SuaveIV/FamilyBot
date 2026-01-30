# Third-Party Attributions

FamilyBot exists because of the incredible work done by the open-source community. This page lists the libraries, frameworks, and tools that make this bot possible.

## Core Dependencies

### Discord Bot Framework

**[discord-py-interactions](https://github.com/interactions-py/interactions.py)**

- **Description**: The foundation for our Discord interactions.
- **License**: MIT License
- **Usage**: Core Discord bot functionality and command handling.
- **Website**: <https://interactions-py.github.io/interactions.py/>

### Web Framework & Server

**[FastAPI](https://github.com/tiangolo/fastapi)**

- **Description**: Powers our Web UI backend.
- **License**: MIT License
- **Usage**: REST API and async request handling.
- **Website**: <https://fastapi.tiangolo.com/>

**[Uvicorn](https://github.com/encode/uvicorn)**

- **Description**: The ASGI server running our FastAPI application.
- **License**: BSD 3-Clause License
- **Usage**: Serving the Web UI.
- **Website**: <https://www.uvicorn.org/>

**[Jinja2](https://github.com/pallets/jinja)**

- **Description**: Templating for our HTML pages.
- **License**: BSD 3-Clause License
- **Usage**: Rendering the Web UI.
- **Website**: <https://jinja.palletsprojects.com/>

### Data Validation & Serialization

**[Pydantic](https://github.com/pydantic/pydantic)**

- **Description**: Ensures our data matches the expected types.
- **License**: MIT License
- **Usage**: API models and configuration validation.
- **Website**: <https://docs.pydantic.dev/>

### HTTP & Networking

**[Requests](https://github.com/psf/requests)**

- **Description**: Standard library for synchronous HTTP requests.
- **License**: Apache License 2.0
- **Usage**: Talking to the Steam API and other services.
- **Website**: <https://requests.readthedocs.io/>

**[HTTPX](https://github.com/encode/httpx)**

- **Description**: Modern HTTP client with async support.
- **License**: BSD 3-Clause License
- **Usage**: Asynchronous API calls.
- **Website**: <https://www.python-httpx.org/>

**[WebSockets](https://github.com/python-websockets/websockets)**

- **Description**: WebSocket support for Python.
- **License**: BSD 3-Clause License
- **Usage**: Internal communication between bot components.
- **Website**: <https://websockets.readthedocs.io/>

### Steam Integration

**[Steam (solsticegamestudios/steam)](https://github.com/solsticegamestudios/steam)**

- **Description**: A specialized fork for interacting with Steam.
- **License**: MIT License
- **Usage**: Enhanced API access and fallback data retrieval.
- **Website**: <https://github.com/solsticegamestudios/steam>

### Browser Automation

**[Playwright](https://github.com/microsoft/playwright-python)**

- **Description**: Handles automated browser interactions.
- **License**: Apache License 2.0
- **Usage**: Extracting Steam tokens.
- **Website**: <https://playwright.dev/python/>

**[Selenium](https://github.com/SeleniumHQ/selenium)**

- **Description**: The classic browser automation framework.
- **License**: Apache License 2.0
- **Usage**: Legacy token extraction.
- **Website**: <https://selenium-python.readthedocs.io/>

**[WebDriver Manager](https://github.com/SergeyPirogov/webdriver_manager)**

- **Description**: Manages browser drivers automatically.
- **License**: Apache License 2.0
- **Usage**: Downloads drivers for Selenium.
- **Website**: <https://pypi.org/project/webdriver-manager/>

### Configuration & Data Processing

**[PyYAML](https://github.com/yaml/pyyaml)**

- **Description**: Reads and writes YAML files.
- **License**: MIT License
- **Usage**: Handling our `config.yml`.
- **Website**: <https://pyyaml.org/>

**[tqdm](https://github.com/tqdm/tqdm)**

- **Description**: Progress bars for the terminal.
- **License**: MIT License
- **Usage**: Visual feedback for long-running scripts.
- **Website**: <https://tqdm.github.io/>

## Frontend Dependencies (CDN)

### CSS Framework

**[Bootstrap](https://github.com/twbs/bootstrap)**

- **Description**: The styling foundation for our Web UI.
- **License**: MIT License
- **Usage**: Responsive layout and base components.
- **Website**: <https://getbootstrap.com/>

**[Bootswatch](https://github.com/thomaspark/bootswatch)**

- **Description**: Custom themes for Bootstrap.
- **License**: MIT License
- **Usage**: Providing various themes including dark mode.
- **Website**: <https://bootswatch.com/>

### Icons

**[Font Awesome](https://github.com/FortAwesome/Font-Awesome)**

- **Description**: The icons used throughout the dashboard.
- **License**: Font Awesome Free License
- **Usage**: UI icons.
- **Website**: <https://fontawesome.com/>

## Development Tools

### Package Management

**[uv](https://github.com/astral-sh/uv)**

- **Description**: Fast Python package manager.
- **License**: Apache License 2.0
- **Usage**: Managing dependencies and environments.
- **Website**: <https://github.com/astral-sh/uv>

### Database

**[SQLite](https://www.sqlite.org/)**

- **Description**: Zero-config SQL engine.
- **License**: Public Domain
- **Usage**: Local storage for games, wishlists, and users.
- **Website**: <https://www.sqlite.org/>

## External APIs & Services

### Steam APIs

**[Steam Web API](https://steamcommunity.com/dev)**

- **Description**: Primary data source for Steam information.
- **Usage**: Game data, user libraries, and wishlists.

**[Steamworks Web API](https://partner.steamgames.com/doc/webapi_overview)**

- **Description**: Extended API for family library management.

### Price Tracking

**[IsThereAnyDeal API](https://isthereanydeal.com/)**

- **Description**: Price tracking and deal aggregation.
- **Usage**: Finding historical lows and current sales.

### Game Information

**[Epic Games Store](https://www.epicgames.com/)**

- **Description**: Source for free game data.

## Original Project Attribution

**[FamilyBot by Chachigo](https://github.com/Chachigo/FamilyBot)**

- **Description**: The original project this version is based on.
- **Usage**: Base structure and core concepts.

## License Compatibility

FamilyBot is built using libraries compatible with permissive open-source usage (MIT, BSD, Apache 2.0, and Public Domain).

## Acknowledgments

Huge thanks to the maintainers of the projects listed above. Without your work, building something like FamilyBot would take months instead of days. We also appreciate the Discord.py community and everyone who uses and helps improve this bot.

---

**Maintainer**: FamilyBot Development Team

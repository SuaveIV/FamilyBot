# Dynamic Admin Commands for FamilyBot Web UI - Future Update Plan

This document outlines a plan for evolving FamilyBot's admin command system to be more dynamic, extensible, and automatically discoverable by the web UI. The goal is to allow plugins to define their own admin commands, which will then automatically appear in the web interface without manual updates to the core web API or HTML templates.

## 1. Vision and Goals

- **Automatic Discovery**: New admin commands defined in plugins should be automatically discovered by the web UI upon bot startup.
- **Extensibility**: Easily add new admin commands by simply defining them within new or existing plugins.
- **Maintainability**: Reduce the need for manual updates to `src/familybot/web/api.py` and `src/familybot/web/templates/admin.html` when new commands are added.
- **Centralized Logic**: Keep admin command execution logic within plugins or dedicated admin action modules, accessed via a generic API endpoint.
- **Metadata-Driven UI**: The web UI should render admin command buttons and forms based on metadata provided by the commands themselves.

## 2. Core Components

### 2.1. Plugin Admin Command Registry (`src/familybot/lib/admin_registry.py`)

This new module will serve as the central hub for all discoverable admin commands.

- **Purpose**: To collect and manage metadata for all admin commands exposed by plugins.
- **Structure**:

    ```python
    # src/familybot/lib/admin_registry.py
    from typing import Callable, Dict, Any, List

    class AdminCommand:
        def __init__(self, name: str, description: str, category: str, func: Callable, params: List[Dict[str, Any]] = None):
            self.name = name
            self.description = description
            self.category = category
            self.func = func # Reference to the async function that executes the command
            self.params = params if params is not None else [] # List of expected parameters

    _command_registry: Dict[str, AdminCommand] = {}

    def register_admin_command(name: str, description: str, category: str, params: List[Dict[str, Any]] = None):
        """Decorator to register an admin command."""
        def decorator(func: Callable):
            if name in _command_registry:
                raise ValueError(f"Admin command '{name}' already registered.")
            _command_registry[name] = AdminCommand(name, description, category, func, params)
            return func
        return decorator

    def get_all_admin_commands() -> Dict[str, AdminCommand]:
        """Returns all registered admin commands."""
        return _command_registry

    def get_admin_command(name: str) -> AdminCommand | None:
        """Returns a specific admin command by name."""
        return _command_registry.get(name)

    def group_commands_by_category() -> Dict[str, List[AdminCommand]]:
        """Groups registered commands by their category."""
        grouped = {}
        for cmd in _command_registry.values():
            if cmd.category not in grouped:
                grouped[cmd.category] = []
            grouped[cmd.category].append(cmd)
        return grouped
    ```

- **Responsibilities**:
  - Provide a decorator for plugins to register their admin functions.
  - Store metadata (name, description, category, function reference, parameters) for each command.
  - Offer methods to retrieve all commands, specific commands, and commands grouped by category.

### 2.2. Plugin Integration (Example: `src/familybot/plugins/steam_family.py`)

Plugins will use the `register_admin_command` decorator to expose their admin functionality.

- **Example Usage**:

    ```python
    # src/familybot/plugins/steam_family.py (excerpt)
    from interactions import Extension
    from familybot.lib.admin_registry import register_admin_command
    from familybot.lib.plugin_admin_actions import force_new_game_action, force_wishlist_action, purge_game_details_cache_action

    class steam_family(Extension):
        # ... (existing code) ...

        @register_admin_command(
            name="force_new_game",
            description="Force a check for new games and trigger notifications.",
            category="Steam Family Plugin Actions"
        )
        async def web_force_new_game(self):
            # This function will be called by the web API via the registry
            return await force_new_game_action()

        @register_admin_command(
            name="force_wishlist",
            description="Force a refresh of the wishlist data.",
            category="Steam Family Plugin Actions"
        )
        async def web_force_wishlist(self):
            return await force_wishlist_action()

        @register_admin_command(
            name="purge_game_details_cache",
            description="Purge all entries from the game details cache.",
            category="Cache Management"
        )
        async def web_purge_game_details_cache(self):
            return await purge_game_details_cache_action()

        # ... (other admin commands from other plugins would similarly register) ...
    ```

- **Note**: The existing Discord-specific prefixed commands (`force_new_game_command`, `force_wishlist_command`, `purge_cache_command`) can either:
  - Call these new `web_` prefixed methods directly.
  - Or, be refactored to simply call the underlying logic in `plugin_admin_actions.py` which is then called by both the Discord commands and the web-registered commands. The latter is already partially done.

### 2.3. Generic Web API Endpoint (`src/familybot/web/api.py`)

A single, generic endpoint will handle all admin command execution requests from the web UI.

- **Purpose**: To receive requests for executing any registered admin command and route them to the correct function via the registry.
- **Modification**:

    ```python
    # src/familybot/web/api.py (excerpt)
    from familybot.lib.admin_registry import get_admin_command, get_all_admin_commands, group_commands_by_category

    # ... (existing imports and setup) ...

    @app.get("/api/admin/commands", response_model=Dict[str, List[Dict[str, Any]]])
    async def get_admin_commands():
        """Returns a list of all registered admin commands, grouped by category, for UI generation."""
        grouped_commands = group_commands_by_category()
        serializable_commands = {}
        for category, commands in grouped_commands.items():
            serializable_commands[category] = [
                {"name": cmd.name, "description": cmd.description, "params": cmd.params}
                for cmd in commands
            ]
        return serializable_commands

    @app.post("/api/admin/execute/{command_name}", response_model=CommandResponse)
    async def execute_admin_command(command_name: str, request: Request):
        """Executes a registered admin command."""
        cmd = get_admin_command(command_name)
        if not cmd:
            raise HTTPException(status_code=404, detail=f"Admin command '{command_name}' not found.")

        try:
            # If the command expects parameters, parse them from the request body
            # For simplicity, assuming JSON body for parameters.
            # This part needs careful design based on how parameters are passed.
            params = {}
            if cmd.params:
                try:
                    request_body = await request.json()
                    for param_def in cmd.params:
                        param_name = param_def["name"]
                        if param_name in request_body:
                            params[param_name] = request_body[param_name]
                        elif param_def.get("required", False):
                            raise HTTPException(status_code=400, detail=f"Missing required parameter: {param_name}")
                except json.JSONDecodeError:
                    if cmd.params: # If params are expected but no JSON body
                         raise HTTPException(status_code=400, detail="Invalid JSON body for command parameters.")
            
            # Execute the command function
            # Assuming the command function returns a dict with "success" and "message"
            # Similar to the current plugin_admin_actions functions.
            result = await cmd.func(**params) # Pass parameters if any
            update_last_activity()
            return CommandResponse(success=result["success"], message=result["message"])
        except HTTPException as he:
            raise he
        except Exception as e:
            logger.error(f"Error executing dynamic admin command '{command_name}': {e}", exc_info=True)
            return CommandResponse(success=False, message=f"Error executing command: {str(e)}")

    # Remove existing specific admin POST endpoints (e.g., /api/admin/populate-database, /api/admin/purge-game-details, /api/admin/plugin-action)
    # The new /api/admin/execute/{command_name} will replace them.
    ```

### 2.4. Dynamic Web UI (`src/familybot/web/templates/admin.html` and `src/familybot/web/static/js/admin.js`)

The web UI will fetch the list of available commands from the new `/api/admin/commands` endpoint and dynamically generate the buttons and forms.

- **`src/familybot/web/templates/admin.html`**:

    ```html
    <!-- ... (head and navbar) ... -->
    <div class="container">
        <h1>Admin Commands</h1>
        <div id="admin-commands-container">
            <!-- Dynamic command sections will be loaded here by JavaScript -->
        </div>
        <div id="command-output">
            <!-- Command output will be displayed here -->
        </div>
    </div>
    <script src="/static/js/theme_switcher.js"></script>
    <script src="/static/js/admin.js"></script>
    <!-- ... (body and html closing tags) ... -->
    ```

- **`src/familybot/web/static/js/admin.js`**:

    ```javascript
    document.addEventListener('DOMContentLoaded', function() {
        const adminCommandsContainer = document.getElementById('admin-commands-container');
        const commandOutput = document.getElementById('command-output');

        async function fetchAndRenderCommands() {
            try {
                const response = await fetch('/api/admin/commands');
                const groupedCommands = await response.json(); // { "CategoryName": [{name: "", description: "", params: []}] }

                adminCommandsContainer.innerHTML = ''; // Clear existing content

                for (const category in groupedCommands) {
                    const categorySection = document.createElement('div');
                    categorySection.classList.add('command-section');
                    categorySection.innerHTML = `<h2>${category}</h2>`;

                    groupedCommands[category].forEach(cmd => {
                        const button = document.createElement('button');
                        button.classList.add('admin-command-btn');
                        button.dataset.commandName = cmd.name;
                        button.textContent = cmd.description; // Or a more user-friendly label

                        // Add parameter handling if needed (more complex UI for forms)
                        // For now, simple button for no-param commands
                        if (cmd.params && cmd.params.length > 0) {
                            // This would require generating a form for each command with parameters
                            // For simplicity, this example only generates buttons for commands without params
                            // or assumes params are handled by a generic input field.
                            // A more robust solution would dynamically create input fields based on cmd.params metadata.
                            button.textContent = `${cmd.description} (Requires Params)`;
                            button.disabled = true; // Disable if not yet implemented
                        }

                        categorySection.appendChild(button);
                        categorySection.appendChild(document.createElement('p')).classList.add('description');
                        categorySection.lastChild.textContent = cmd.description; // Display description below button
                    });
                    adminCommandsContainer.appendChild(categorySection);
                }

                // Re-attach event listeners to the newly created buttons
                attachCommandButtonListeners();

            } catch (error) {
                adminCommandsContainer.innerHTML = `<p class="error">Failed to load admin commands: ${error}</p>`;
                console.error('Error fetching admin commands:', error);
            }
        }

        function attachCommandButtonListeners() {
            const commandButtons = document.querySelectorAll('.admin-command-btn');
            commandButtons.forEach(button => {
                // Remove old listeners to prevent duplicates
                button.removeEventListener('click', handleCommandClick);
                button.addEventListener('click', handleCommandClick);
            });
        }

        async function handleCommandClick() {
            const commandName = this.dataset.commandName;
            const commandLabel = this.textContent.trim();

            // Disable all buttons
            document.querySelectorAll('.admin-command-btn').forEach(btn => btn.disabled = true);
            commandOutput.innerHTML = `<p>Executing "${commandLabel}"...</p>`;

            try {
                // If command has parameters, collect them from a form (not implemented in this simplified example)
                const requestBody = {}; // Populate with actual parameter values if applicable

                const response = await fetch(`/api/admin/execute/${commandName}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody) // Send parameters if any
                });
                const data = await response.json();

                let outputHtml = `<h3>${commandLabel} Result:</h3>`;
                if (data.success) {
                    outputHtml += `<p class="success">${data.message}</p>`;
                } else {
                    outputHtml += `<p class="error">${data.message}</p>`;
                }
                commandOutput.innerHTML = outputHtml;

            } catch (error) {
                commandOutput.innerHTML = `<h3>Error:</h3><p class="error">An error occurred while executing the command: ${error}</p>`;
                console.error('Error executing command:', error);
            } finally {
                // Re-enable all buttons
                document.querySelectorAll('.admin-command-btn').forEach(btn => btn.disabled = false);
            }
        }

        fetchAndRenderCommands(); // Initial fetch and render
    });
    ```

## 3. Implementation Steps

1. **Create `src/familybot/lib/admin_registry.py`**: Implement the `AdminCommand` class and helper functions (`register_admin_command`, `get_all_admin_commands`, `get_admin_command`, `group_commands_by_category`).
2. **Refactor `src/familybot/lib/plugin_admin_actions.py`**:
    - Decorate existing functions (e.g., `purge_game_details_cache_action`, `force_new_game_action`, `force_wishlist_action`) with `@register_admin_command`.
    - Consider moving these functions directly into the respective plugins if they are tightly coupled, or keep them as a shared library that plugins call and then re-expose via the decorator.
3. **Update `src/familybot/FamilyBot.py`**: Ensure that plugins are loaded *before* the web server starts, so that all admin commands are registered.
4. **Modify `src/familybot/web/api.py`**:
    - Remove the specific admin POST endpoints (`/api/admin/populate-database`, `/api/admin/purge-game-details`, `/api/admin/plugin-action`).
    - Add the new GET endpoint `/api/admin/commands` to expose registered command metadata.
    - Add the new POST endpoint `/api/admin/execute/{command_name}` to handle dynamic command execution.
5. **Update `src/familybot/web/templates/admin.html`**: Adjust the HTML structure to be a container for dynamically loaded content.
6. **Update `src/familybot/web/static/js/admin.js`**:
    - Implement `fetchAndRenderCommands` to call `/api/admin/commands` and dynamically create UI elements.
    - Modify `handleCommandClick` to call the generic `/api/admin/execute/{command_name}` endpoint.
    - Add logic for handling command parameters (e.g., generating input fields, validating input). This is the most complex part of the dynamic UI.

## 4. Migration Strategy

- **Phased Rollout**: Begin by implementing the registry and generic API endpoint, but keep the existing web UI and specific API endpoints initially.
- **Gradual Refactoring**: As each admin command is moved to the new decorator system, remove its corresponding hardcoded API endpoint and UI element.
- **Backward Compatibility**: If possible, maintain existing API endpoints for a transition period to avoid breaking any external tools that might be using them.

## 5. Future Enhancements

- **Parameter Handling**: Develop a more sophisticated system for defining and rendering UI elements for command parameters (e.g., text inputs, dropdowns, checkboxes) based on the `params` metadata.
- **Permissions**: Add a `permission_level` to `AdminCommand` and integrate with an authentication system to restrict access to certain commands.
- **Progress/Status Updates**: Implement a mechanism for long-running admin commands to send real-time progress updates back to the web UI via WebSockets.
- **Command Categories**: Allow plugins to define custom categories for their commands.

## 6. Documentation Updates

To fully support the dynamic admin command system, the following documentation and example files will need to be updated:

### 6.1. Plugin Specification

The plugin specification (e.g., `doc/PLUGIN_SPEC.md` or similar) should be updated to:

- Detail the `register_admin_command` decorator and its parameters (`name`, `description`, `category`, `params`).
- Explain how plugins can define their own admin commands and the expected return format for these command functions (e.g., `{"success": True, "message": "..."}`).
- Provide guidelines for categorizing commands and defining parameters for the web UI.

### 6.2. Example Plugin (`src/familybot/plugins/example_plugin.py.template`)

The `example_plugin.py.template` should be modified to include a simple example of an admin command registered using the new decorator. This will serve as a clear guide for developers creating new plugins.

```python
# src/familybot/plugins/example_plugin.py.template (excerpt)

# ... (existing imports) ...
from familybot.lib.admin_registry import register_admin_command

class example_plugin(Extension):
    # ... (existing __init__ and other methods) ...

    @register_admin_command(
        name="example_admin_command",
        description="An example admin command from the example plugin.",
        category="Example Plugin Commands",
        params=[
            {"name": "input_text", "type": "str", "description": "Some text input", "required": False}
        ]
    )
    async def example_admin_command_func(self, input_text: str = None):
        """
        This is an example admin command that can be triggered from the web UI.
        It demonstrates how to register a command and optionally accept parameters.
        """
        if input_text:
            message = f"Example admin command executed with input: '{input_text}'"
        else:
            message = "Example admin command executed without input."
        self.bot.logger.info(message) # Use plugin's logger
        return {"success": True, "message": message}

    # ... (rest of the plugin) ...
```

This comprehensive plan provides a clear roadmap for creating a highly flexible and maintainable admin command system for FamilyBot's web UI, along with the necessary documentation updates.

# Mise Integration Plan

This document outlines the plan to integrate `mise` into the FamilyBot project to standardize the development environment.

## Why Mise?

[Mise](https://mise.jdx.dev/) is a tool that helps manage tool versions (like Python) and environment variables on a per-project basis. By incorporating `mise`, we can ensure that every developer uses the same version of Python, which is specified in our `pyproject.toml` as `>=3.13`. This prevents "it works on my machine" issues and streamlines the setup process for new contributors.

## Proposed Changes

### 1. Add `.mise.toml`

A new file, `.mise.toml`, will be added to the root of the project with the following content:

```toml
[tools]
python = "3.13"
```

This file tells `mise` that the project requires Python 3.13.

### 2. Update `justfile`

The `justfile` will be updated to use `mise` to execute commands. This ensures that the correct Python version is used for all tasks. The main change will be to prefix commands with `mise exec --`.

For example, the `create-venv` task will be changed from:

```
create-venv:
    @echo "📦 Creating virtual environment with uv..."
    uv venv
    @echo "✅ Virtual environment created at .venv/"
```

to:

```
create-venv:
    @echo "📦 Creating virtual environment with uv..."
    mise exec -- uv venv
    @echo "✅ Virtual environment created at .venv/"
```

Similarly, all instances of `uv run` will be replaced with `mise exec -- uv run`, and `uv pip` will be replaced with `mise exec -- uv pip`.

### 3. Update `README.md`

The `README.md` file will be updated to include instructions on how to set up the project using `mise`.

## New Development Workflow

With these changes, the new workflow for setting up the project will be:

1.  **Install `mise`:** Follow the instructions on the [mise website](https://mise.jdx.dev/getting-started.html) to install `mise`.
2.  **Install tools:** Run `mise install` in the project root. This will install Python 3.13 if it's not already installed.
3.  **Setup project:** Run `just setup`. This will create the virtual environment and install all dependencies.
4.  **Run the bot:** Run `just run` to start the bot.

## Benefits

- **Consistent Environment:** Guarantees that all developers are using the same Python version.
- **Simplified Setup:** New developers can get up and running with just a few commands.
- **Automation:** The `justfile` handles the complexity of the environment, making it easy to run tasks.

This integration will make the development process for FamilyBot more robust and developer-friendly.

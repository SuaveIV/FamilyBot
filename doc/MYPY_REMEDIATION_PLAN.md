# Mypy Remediation Plan

This document outlines the plan to resolve the 41 `mypy` type errors detected by the `just check` command. The errors fall into three main categories.

---

## 1. Missing Type Stubs (`[import-untyped]`)

- **Problem**: This is the most common issue. `mypy` cannot verify code that uses libraries without type information (stubs). This affects `yaml`, `requests`, `tqdm`, `coloredlogs`, and `steam`.
- **Plan**:
    1.  Install official or community-provided "stub" packages for the libraries that have them.
    2.  Configure `mypy` to ignore the specific modules that do not have available stubs.

## 2. Type Inconsistencies (`[assignment]`, `[attr-defined]`)

- **Problem**: These are potential bugs where data of one type is being used where a different type is expected.
- **Examples**:
    - In `plugins/help_message.py`, a custom client protocol is being assigned to a variable that expects the base `Client` type.
    - In `scripts/populate_database.py`, a `float` is assigned to a variable that should be an `int`.
    - In `Token_Sender/getToken.py`, an incorrect attribute `ConnectionRefusedError` is used instead of the correct `ConnectionClosedError`.
- **Plan**: These will be fixed on a case-by-case basis by correcting the type hints, casting the variables, or using the correct attributes as defined by the libraries.

## 3. Ambiguous Type Hints (`[arg-type]`, `[misc]`)

- **Problem**: `mypy` cannot determine the type of a variable, usually because it is initialized as an empty list (e.g., `global_wishlist = []`).
- **Plan**: Add explicit type annotations to these variables (e.g., `global_wishlist: list = []`).

---

## Proposed Workflow

Here is the recommended step-by-step process to resolve these errors:

1.  **Install Stub Packages**: Add the following `types-*` packages to the `[project.optional-dependencies.dev]` section in `pyproject.toml`:

    ```toml
    "types-requests",
    "types-PyYAML",
    "types-tqdm",
    ```

2.  **Configure Mypy**: Create a new file named `mypy.ini` in the project root with the following content. This tells `mypy` to ignore the libraries that we know don't have type stubs.

    ```ini
    [mypy]

    [mypy-steam.*]
    ignore_missing_imports = True

    [mypy-coloredlogs.*]
    ignore_missing_imports = True

    [mypy-tqdm.asyncio]
    ignore_missing_imports = True
    ```

3.  **Install Dependencies**: Run `just install-deps` to install the new stub packages into the virtual environment.

4.  **Re-run Checks**: Run `just check` again. This will verify that the missing import errors are resolved and will provide a cleaner list of the remaining code errors.

5.  **Fix Code Errors**: Incrementally fix the remaining `[assignment]`, `[attr-defined]`, and `[var-annotated]` errors based on the new `mypy` output.

6.  **Verify**: Run `just check` after each fix to ensure the issue is resolved and no new errors are introduced.

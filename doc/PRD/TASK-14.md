# TASK-14 — Standardise type annotations to Python 3.10+ syntax

**Priority:** 🟢 Low  
**Effort:** S (1–2 hrs)  
**PRD reference:** §6.6  
**Depends on:** All other tasks (do last to avoid merge conflicts)

---

## Background

The project targets Python 3.13, but many files still use the older `typing` module imports: `Optional[str]`, `List[str]`, `Dict[str, Any]`, `Tuple[...]`. Python 3.10+ allows `str | None`, `list[str]`, `dict[str, Any]`, `tuple[...]` directly. Mixing both styles makes the codebase harder to read and signals uncertainty about the minimum Python version.

## Acceptance criteria

- [ ] No `Optional`, `List`, `Dict`, or `Tuple` imports remain from `typing`, except where required for runtime use (e.g. `TypedDict`, `TYPE_CHECKING` guards, `Protocol`). **Note: `Any` (from `typing`) is explicitly allowed.**
- [ ] All annotations use built-in generics: `str | None`, `list[str]`, `dict[str, Any]`, `tuple[str, ...]`.
- [ ] `from __future__ import annotations` is added to any file that has forward references after the change.
- [ ] `ruff check` passes on all modified files.
- [ ] No runtime errors are introduced — annotations evaluated at runtime (e.g. in dataclasses or `isinstance` guards) are verified separately.

## Implementation notes

Run ruff's auto-fix for the relevant upgrade rules across the whole source tree:

```bash
uv run ruff check --select UP006,UP007,UP035 --fix src/ scripts/
```

- `UP006` — `List[x]` → `list[x]`, `Dict[x, y]` → `dict[x, y]`, etc.
- `UP007` — `Optional[x]` → `x | None`, `Union[x, y]` → `x | y`
- `UP035` — removes now-unnecessary `from typing import ...` lines

Review the full diff before committing. Pay particular attention to any file that uses `dataclasses.fields()`, `get_type_hints()`, or Pydantic models, as these evaluate annotations at runtime and may behave differently without `from __future__ import annotations`.

**Allowed Imports Example:**
```python
from typing import Any, Dict, List, Optional, Protocol, Tuple, TypedDict, TYPE_CHECKING
from __future__ import annotations
```
Note: `Optional`, `List`, `Dict`, `Tuple` are listed here only to show they should be removed in favor of built-ins, while `Any` remains a valid import.

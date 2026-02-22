# TASK-09 — Consolidate deal detection into `steam_helpers.py:process_game_deal`

**Priority:** 🟠 High  
**Effort:** L (4–6 hrs)  
**PRD reference:** §6.3  
**Depends on:** TASK-04, TASK-05

---

## Background

The logic for "is this game a good deal?" — discount threshold check, historical-low comparison, deal reason string formatting — is copy-pasted across four locations:

| File | Location | Notes |
|------|----------|-------|
| `steam_helpers.py` | `process_game_deal` | Intended canonical location |
| `steam_admin.py` | `force_deals_command` | ~60 lines inline, threshold 30%/15% |
| `steam_admin.py` | `force_deals_unlimited_command` | Near-identical to above, no game limit |
| `plugin_admin_actions.py` | `force_deals_action` | Another copy, threshold 30%/15% |

The two admin commands differ only in game count limit and a family-sharing filter — not in deal detection logic. The magic numbers (30%, 15%, 1.2× buffer) appear independently in each copy.

## Acceptance criteria

- [ ] `process_game_deal` in `steam_helpers.py` is the single implementation of deal detection.
- [ ] `force_deals_command` and `force_deals_unlimited_command` in `steam_admin.py` call `process_game_deal`; they contain no inline discount calculation.
- [ ] `force_deals_action` in `plugin_admin_actions.py` calls `process_game_deal`; it contains no inline discount calculation.
- [ ] Deal thresholds are defined as named constants, not magic numbers:
  - `HIGH_DISCOUNT_THRESHOLD = 30`
  - `LOW_DISCOUNT_THRESHOLD = 15`
  - `HISTORICAL_LOW_BUFFER = 1.2`
- [ ] `force_deals_unlimited_command` is either merged into `force_deals_command` as a parameter variant or kept as a thin wrapper — no duplicated logic either way.
- [ ] Existing command behaviour (output format, which deals are shown, progress messages) is unchanged from the user's perspective.
- [ ] `ruff check` passes on all modified files.

## Implementation notes

Suggested refactor for the admin command, replacing both `force_deals_command` and `force_deals_unlimited_command`:

```python
@prefixed_command(name="force_deals")
async def force_deals_command(
    self,
    ctx: PrefixedContext,
    target_friendly_name: str | None = None,
    limit: int = 100,
    family_sharing_only: bool = False,
) -> None:
    ...
    for item in global_wishlist[:limit]:
        app_id = item[0]
        interested_users = item[1]

        game_data = await fetch_game_details(app_id, self.steam_api_manager)
        if not game_data:
            continue

        if family_sharing_only and not game_data.get("is_family_shared"):
            continue

        deal_info = await process_game_deal(app_id, self.steam_api_manager)
        if deal_info:
            deal_info["interested_users"] = [
                current_family_members.get(uid, "Unknown") for uid in interested_users
            ]
            deals_found.append(deal_info)
```

`force_deals_unlimited_command` becomes:

```python
@prefixed_command(name="force_deals_unlimited")
async def force_deals_unlimited_command(self, ctx: PrefixedContext) -> None:
    await self.force_deals_command(ctx, limit=9999, family_sharing_only=True)
```

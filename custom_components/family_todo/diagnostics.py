"""Diagnostics support for Family Todo.

One config entry = one list (see __init__.py), so this exports one list's
full stored state - items, sections, ordering - alongside the entry's own
config and the (redacted) global person -> notify service mapping, since
that's the other piece of state a "why isn't this reminder firing" report
would need. Task/section text itself isn't redacted: it's the household's
own data about their own list, the point of asking for it is to read it.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .notify_map import async_get_notify_map_store

# owner_user_id/notify targets identify a specific person's HA account or
# phone - not needed to diagnose a list/reminder problem, and this
# diagnostics export is the kind of thing that might get pasted into a
# GitHub issue.
TO_REDACT = {"owner_user_id", "notify_map"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return diagnostics for one Family Todo list."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    entity = entry_data.get("entity")

    list_data: dict[str, Any] | None = None
    if entity is not None:
        model = await entity._store.async_load()
        list_data = model.to_dict()

    notify_map = await async_get_notify_map_store(hass).async_load()

    return async_redact_data(
        {
            "entry": {
                "title": entry.title,
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
            "list": list_data,
            "notify_map": notify_map,
        },
        TO_REDACT,
    )

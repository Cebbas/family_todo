"""Adult/child write-permission check, shared by ws_api.py's list/item handlers.

Reuses the Family Planner integration's own "persons" list (name,
ha_user_id, role) as the single source of truth for who's an adult, instead
of keeping a second, separately-maintained role list here - two independent
places to mark someone as a child would inevitably drift apart. See the
family_planner integration's __init__.py (_is_adult/_current_person) for the
identical rule this mirrors.

Family Planner isn't a hard dependency: if it isn't installed/loaded, or the
caller isn't a person matched via ha_user_id, everyone is treated as an
adult (fail open) - the same safe default used throughout this permission
model, so nobody's task list locks up because of an unrelated integration
not being set up.
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant

_FAMILY_PLANNER_DOMAIN = "family_planner"


async def async_is_adult(hass: HomeAssistant, user_id: str | None) -> bool:
    """True unless the caller is a Family Planner person explicitly marked "child"."""
    if not user_id:
        return True
    store = hass.data.get(_FAMILY_PLANNER_DOMAIN)
    if store is None:
        return True
    data = await store.async_load()
    for person in (data or {}).get("persons") or []:
        if isinstance(person, dict) and person.get("ha_user_id") == user_id:
            return person.get("role") != "child"
    return True

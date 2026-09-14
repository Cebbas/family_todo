"""Global mapping of person -> notify service, used for due-date reminders.

Unlike everything in store.py this isn't per-list - a person should get
their reminders on the same phone no matter which Family Todo list the
overdue item lives in, so it's one small store shared by the whole
integration, keyed by `person.*` entity_id (stable even if the person's
display name changes) and mapping to a `notify.*` service name (e.g.
"mobile_app_sebastians_iphone", without the "notify." prefix).

Configured from the panel's "Notiser" tab (ws_list_notify_services /
ws_get_notify_map / ws_set_notify_target in ws_api.py) - there's no
reliable, general way to derive "which notify service belongs to this
person" automatically across HA installs, so it's an explicit one-time
mapping instead of magic guessing.
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, NOTIFY_MAP_STORAGE_KEY, NOTIFY_MAP_STORAGE_VERSION

_HASS_DATA_KEY = "notify_map_store"


class NotifyMapStore:
    """Persists the person -> notify service mapping in HA's own storage."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store = Store(hass, NOTIFY_MAP_STORAGE_VERSION, NOTIFY_MAP_STORAGE_KEY)
        self._data: dict[str, str] | None = None

    async def async_load(self) -> dict[str, str]:
        if self._data is None:
            self._data = await self._store.async_load() or {}
        return self._data

    async def async_set(self, person_entity_id: str, service: str | None) -> None:
        data = await self.async_load()
        if service:
            data[person_entity_id] = service
        else:
            data.pop(person_entity_id, None)
        await self._store.async_save(data)


def async_get_notify_map_store(hass: HomeAssistant) -> NotifyMapStore:
    """Returns the single shared NotifyMapStore instance for this HA run."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    store = domain_data.get(_HASS_DATA_KEY)
    if store is None:
        store = NotifyMapStore(hass)
        domain_data[_HASS_DATA_KEY] = store
    return store

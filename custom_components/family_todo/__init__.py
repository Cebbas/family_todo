"""The Family Todo integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, PLATFORMS
from .panel import async_register_panel
from .reminders import async_setup_reminders
from .store import FamilyTodoStore
from .ws_api import async_register_ws_api

_LOGGER = logging.getLogger(__name__)

# Inget att konfigurera via configuration.yaml - allt sker via config entries
# (en per lista, skapade från panelen eller Inställningar).
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    async_register_ws_api(hass)
    await async_register_panel(hass)
    async_setup_reminders(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"entry": entry}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Städa bort listans lagringsfil när den tas bort helt.

    Utan detta blir listans .storage-fil kvarliggande för evigt (samma
    fälla som cal_combiner tidigare gick i för sina egna kalendrar - se
    dess IDEAS.md "Robusthet"-avsnitt).
    """
    await FamilyTodoStore(hass, entry.entry_id).async_remove()

"""Registers the Family Todo sidebar panel and its static JS file."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PANEL_ICON, PANEL_URL_PATH

_LOGGER = logging.getLogger(__name__)
_STATIC_URL = f"/{DOMAIN}_panel"
_REGISTERED = f"{DOMAIN}_panel_registered"


async def async_register_panel(hass: HomeAssistant) -> None:
    if hass.data.get(_REGISTERED):
        return
    hass.data[_REGISTERED] = True

    www_dir = Path(__file__).parent / "www"

    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(_STATIC_URL, str(www_dir), False)]
        )
    except ImportError:
        hass.http.register_static_path(_STATIC_URL, str(www_dir), False)

    frontend.async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title="Att göra",
        sidebar_icon=PANEL_ICON,
        frontend_url_path=PANEL_URL_PATH,
        config={
            "_panel_custom": {
                "name": "family-todo-panel",
                "embed_iframe": False,
                "trust_external": True,
                "js_url": f"{_STATIC_URL}/family-todo-panel.js?v=2",
            }
        },
        require_admin=False,
    )

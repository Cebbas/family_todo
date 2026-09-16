"""Config flow for Family Todo.

Varje lista är en egen config entry (samma modell som cal_combiner
använder för sammanslagna kalendrar) - det gör varje lista till en riktig
`todo.*`-entitet som går att ta bort/inaktivera för sig, utan ett eget
"vilken lista"-begrepp inuti en enda entry.

`async_step_user` är den vanliga vägen (Inställningar → Enheter & tjänster
→ Lägg till integration) och visar ett formulär. `async_step_create_list`
tar samma data men utan formulär - det är vägen sidopanelen använder för
att skapa nya listor utan att användaren behöver klicka igenom
Inställningar varje gång (se ws_api.py: ws_create_list).
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import CONF_COLOR, CONF_ICON, CONF_NAME, CONF_OWNER_USER_ID, DEFAULT_ICON, DOMAIN

_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): str,
        vol.Optional(CONF_ICON, default=DEFAULT_ICON): str,
        vol.Optional(CONF_COLOR): str,
        # Valfri - se permissions.py för vad den styr. Kan även sättas/
        # ändras senare via panelen (ws_update_list), inte bara här.
        vol.Optional(CONF_OWNER_USER_ID): selector.UserSelector(),
    }
)


class FamilyTodoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Family Todo."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if not name:
                errors["base"] = "name_required"
            else:
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_NAME: name,
                        CONF_ICON: user_input.get(CONF_ICON) or DEFAULT_ICON,
                        CONF_COLOR: user_input.get(CONF_COLOR),
                        CONF_OWNER_USER_ID: user_input.get(CONF_OWNER_USER_ID),
                    },
                )
        return self.async_show_form(step_id="user", data_schema=_USER_SCHEMA, errors=errors)

    async def async_step_create_list(self, user_input: dict[str, Any]) -> FlowResult:
        """Skapas direkt av sidopanelen - alltid komplett data, inget formulär."""
        name = user_input[CONF_NAME].strip()
        return self.async_create_entry(
            title=name,
            data={
                CONF_NAME: name,
                CONF_ICON: user_input.get(CONF_ICON) or DEFAULT_ICON,
                CONF_COLOR: user_input.get(CONF_COLOR),
                CONF_OWNER_USER_ID: user_input.get(CONF_OWNER_USER_ID),
            },
        )

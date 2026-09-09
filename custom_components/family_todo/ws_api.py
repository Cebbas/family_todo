"""Websocket API used by the Family Todo sidebar panel."""
from __future__ import annotations

from datetime import date, datetime

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.todo import TodoItem, TodoItemStatus
from homeassistant.core import HomeAssistant

from .const import CONF_COLOR, CONF_ICON, CONF_NAME, DOMAIN
from .store import FamilyTodoStore, Subtask

SUBTASK_SCHEMA = {
    vol.Required("id"): str,
    vol.Required("summary"): str,
    vol.Optional("complete", default=False): bool,
}


def _entry_to_dict(entry) -> dict:
    return {
        "entry_id": entry.entry_id,
        "name": entry.data.get(CONF_NAME, entry.title),
        "icon": entry.data.get(CONF_ICON),
        "color": entry.data.get(CONF_COLOR),
    }


def _item_to_dict(item) -> dict:
    done, total = item.subtask_progress
    return {
        "uid": item.uid,
        "summary": item.summary,
        "status": item.status,
        "description": item.description,
        "due": item.due,
        "assignee": item.assignee,
        "subtasks": [s.to_dict() for s in item.subtasks],
        "subtasks_done": done,
        "subtasks_total": total,
    }


def _parse_due(value: str | None):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _get_entity(hass: HomeAssistant, entry_id: str):
    entry_data = hass.data.get(DOMAIN, {}).get(entry_id)
    return entry_data.get("entity") if entry_data else None


def _get_store(hass: HomeAssistant, entry_id: str) -> FamilyTodoStore | None:
    entry_data = hass.data.get(DOMAIN, {}).get(entry_id)
    if entry_data is None:
        return None
    entity = entry_data.get("entity")
    return entity._store if entity else None


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/list_lists"})
@websocket_api.async_response
async def ws_list_lists(hass: HomeAssistant, connection, msg):
    entries = hass.config_entries.async_entries(DOMAIN)
    connection.send_result(msg["id"], {"lists": [_entry_to_dict(e) for e in entries]})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/create_list",
        vol.Required("name"): str,
        vol.Optional("icon"): vol.Any(str, None),
        vol.Optional("color"): vol.Any(str, None),
    }
)
@websocket_api.async_response
async def ws_create_list(hass: HomeAssistant, connection, msg):
    name = msg["name"].strip()
    if not name:
        connection.send_error(msg["id"], "invalid_input", "Namn krävs")
        return
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "create_list"},
        data={"name": name, "icon": msg.get("icon"), "color": msg.get("color")},
    )
    if result.get("type") != "create_entry":
        connection.send_error(msg["id"], "invalid_input", "Kunde inte skapa listan")
        return
    connection.send_result(msg["id"], {"entry_id": result["result"].entry_id})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/update_list",
        vol.Required("entry_id"): str,
        vol.Required("name"): str,
        vol.Optional("icon"): vol.Any(str, None),
        vol.Optional("color"): vol.Any(str, None),
    }
)
@websocket_api.async_response
async def ws_update_list(hass: HomeAssistant, connection, msg):
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "Listan hittades inte")
        return
    name = msg["name"].strip()
    hass.config_entries.async_update_entry(
        entry,
        title=name,
        data={**entry.data, CONF_NAME: name, CONF_ICON: msg.get("icon"), CONF_COLOR: msg.get("color")},
    )
    connection.send_result(msg["id"], {"ok": True})


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/delete_list", vol.Required("entry_id"): str}
)
@websocket_api.async_response
async def ws_delete_list(hass: HomeAssistant, connection, msg):
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "Listan hittades inte")
        return
    await hass.config_entries.async_remove(msg["entry_id"])
    connection.send_result(msg["id"], {"ok": True})


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/list_items", vol.Required("entry_id"): str}
)
@websocket_api.async_response
async def ws_list_items(hass: HomeAssistant, connection, msg):
    store = _get_store(hass, msg["entry_id"])
    if store is None:
        connection.send_error(msg["id"], "not_found", "Listan hittades inte")
        return
    model = await store.async_load()
    connection.send_result(msg["id"], {"items": [_item_to_dict(i) for i in model.items]})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/create_item",
        vol.Required("entry_id"): str,
        vol.Required("summary"): str,
        vol.Optional("description"): vol.Any(str, None),
        vol.Optional("due"): vol.Any(str, None),
    }
)
@websocket_api.async_response
async def ws_create_item(hass: HomeAssistant, connection, msg):
    entity = _get_entity(hass, msg["entry_id"])
    if entity is None:
        connection.send_error(msg["id"], "not_found", "Listan hittades inte")
        return
    await entity.async_create_todo_item(
        TodoItem(
            summary=msg["summary"],
            status=TodoItemStatus.NEEDS_ACTION,
            description=msg.get("description"),
            due=_parse_due(msg.get("due")),
        )
    )
    connection.send_result(msg["id"], {"ok": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/update_item",
        vol.Required("entry_id"): str,
        vol.Required("uid"): str,
        vol.Required("summary"): str,
        vol.Required("status"): vol.In(["needs_action", "completed"]),
        vol.Optional("description"): vol.Any(str, None),
        vol.Optional("due"): vol.Any(str, None),
    }
)
@websocket_api.async_response
async def ws_update_item(hass: HomeAssistant, connection, msg):
    entity = _get_entity(hass, msg["entry_id"])
    if entity is None:
        connection.send_error(msg["id"], "not_found", "Listan hittades inte")
        return
    await entity.async_update_todo_item(
        TodoItem(
            uid=msg["uid"],
            summary=msg["summary"],
            status=TodoItemStatus(msg["status"]),
            description=msg.get("description"),
            due=_parse_due(msg.get("due")),
        )
    )
    connection.send_result(msg["id"], {"ok": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/delete_item",
        vol.Required("entry_id"): str,
        vol.Required("uid"): str,
    }
)
@websocket_api.async_response
async def ws_delete_item(hass: HomeAssistant, connection, msg):
    entity = _get_entity(hass, msg["entry_id"])
    if entity is None:
        connection.send_error(msg["id"], "not_found", "Listan hittades inte")
        return
    await entity.async_delete_todo_items([msg["uid"]])
    connection.send_result(msg["id"], {"ok": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/move_item",
        vol.Required("entry_id"): str,
        vol.Required("uid"): str,
        vol.Optional("previous_uid"): vol.Any(str, None),
    }
)
@websocket_api.async_response
async def ws_move_item(hass: HomeAssistant, connection, msg):
    entity = _get_entity(hass, msg["entry_id"])
    if entity is None:
        connection.send_error(msg["id"], "not_found", "Listan hittades inte")
        return
    await entity.async_move_todo_item(msg["uid"], msg.get("previous_uid"))
    connection.send_result(msg["id"], {"ok": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_item_extra",
        vol.Required("entry_id"): str,
        vol.Required("uid"): str,
        vol.Optional("assignee"): vol.Any(str, None),
        vol.Optional("subtasks"): [SUBTASK_SCHEMA],
    }
)
@websocket_api.async_response
async def ws_set_item_extra(hass: HomeAssistant, connection, msg):
    """Sparar delsteg och tilldelning - utökningsdata, se store.py.

    Rör aldrig summary/status/description/due (det gör create/update_item
    ovan) - bara de fält HA:s todo-schema inte har plats för.
    """
    store = _get_store(hass, msg["entry_id"])
    entity = _get_entity(hass, msg["entry_id"])
    if store is None or entity is None:
        connection.send_error(msg["id"], "not_found", "Listan hittades inte")
        return
    model = await store.async_load()
    changes: dict = {}
    if "assignee" in msg:
        changes["assignee"] = msg["assignee"]
    if "subtasks" in msg:
        changes["subtasks"] = [Subtask.from_dict(s) for s in msg["subtasks"]]
    item = model.update(msg["uid"], **changes)
    if item is None:
        connection.send_error(msg["id"], "not_found", "Uppgiften hittades inte")
        return
    await store.async_save()
    entity.async_write_ha_state()
    connection.send_result(msg["id"], {"ok": True})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/list_persons"})
@websocket_api.async_response
async def ws_list_persons(hass: HomeAssistant, connection, msg):
    """Bekvämlighetslista av person.*-entiteter för tilldelnings-väljaren.

    Tilldelning är fritext (`assignee`) - den här listan är bara ett
    förslag i panelens dropdown, inget krav att peka ut en person.*-entitet.
    """
    persons = [
        {"entity_id": state.entity_id, "name": state.attributes.get("friendly_name", state.entity_id)}
        for state in hass.states.async_all("person")
    ]
    persons.sort(key=lambda p: p["name"])
    connection.send_result(msg["id"], {"persons": persons})


def async_register_ws_api(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_list_lists)
    websocket_api.async_register_command(hass, ws_create_list)
    websocket_api.async_register_command(hass, ws_update_list)
    websocket_api.async_register_command(hass, ws_delete_list)
    websocket_api.async_register_command(hass, ws_list_items)
    websocket_api.async_register_command(hass, ws_create_item)
    websocket_api.async_register_command(hass, ws_update_item)
    websocket_api.async_register_command(hass, ws_delete_item)
    websocket_api.async_register_command(hass, ws_move_item)
    websocket_api.async_register_command(hass, ws_set_item_extra)
    websocket_api.async_register_command(hass, ws_list_persons)

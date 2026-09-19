"""Websocket API used by the Family Todo sidebar panel."""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.todo import TodoItem, TodoItemStatus
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import floor_registry as fr
from homeassistant.util import dt as dt_util

from .const import (
    CONF_COLOR,
    CONF_ICON,
    CONF_LIST_TYPE,
    CONF_NAME,
    CONF_OWNER_USER_ID,
    DOMAIN,
    LIST_TYPE_TASKS,
)
from .notify_map import async_get_notify_map_store
from .permissions import async_is_adult
from .store import (
    RECURRENCE_UNITS,
    FamilyTodoStore,
    Recurrence,
    Section,
    Subtask,
    TodoItemData,
    combine_description,
    split_description,
)

_LOGGER = logging.getLogger(__name__)

RECURRENCE_SCHEMA = {
    vol.Required("interval"): vol.All(int, vol.Range(min=1)),
    vol.Required("unit"): vol.In(RECURRENCE_UNITS),
}

SUBTASK_SCHEMA = {
    vol.Required("id"): str,
    vol.Required("summary"): str,
    vol.Optional("complete", default=False): bool,
    vol.Optional("due"): vol.Any(str, None),
    vol.Optional("recurrence"): vol.Any(RECURRENCE_SCHEMA, None),
}


def _entry_to_dict(entry) -> dict:
    return {
        "entry_id": entry.entry_id,
        "name": entry.data.get(CONF_NAME, entry.title),
        "list_type": entry.data.get(CONF_LIST_TYPE, LIST_TYPE_TASKS),
        "icon": entry.data.get(CONF_ICON),
        "color": entry.data.get(CONF_COLOR),
        "owner_user_id": entry.data.get(CONF_OWNER_USER_ID),
    }


def _item_to_dict(item) -> dict:
    done, total = item.subtask_progress
    return {
        "uid": item.uid,
        "summary": item.summary,
        "status": item.status,
        # Utan vårt auto-genererade tilldelnings-/delsteg-block (se
        # split_description/combine_description i store.py) - panelen har
        # redan den datan strukturerat via assignee/subtasks_* nedan och
        # ska aldrig visa eller skicka tillbaka blocket som fritext.
        "description": split_description(item.description),
        "due": item.due,
        "assignee": item.assignee,
        "subtasks": [s.to_dict() for s in item.subtasks],
        "subtasks_done": done,
        "subtasks_total": total,
        "section_id": item.section_id,
        "recurrence": item.recurrence.to_dict() if item.recurrence else None,
        "last_completed": item.last_completed,
        "reminder_sent": item.reminder_sent,
    }


def _section_to_dict(section) -> dict:
    return {"id": section.id, "name": section.name, "area_id": section.area_id, "icon": section.icon}


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


async def _require_list_write_access(hass: HomeAssistant, connection, msg: dict, entry_id: str) -> bool:
    """Gate for every handler that adds/changes/removes something in a list.

    True (allowed) for: adults, callers with no matched Family Planner
    person (fail open, see permissions.py), and anyone when the list has no
    owner_user_id set (an unowned list is a shared/family list, not "someone
    else's" - same convention the card uses for unowned calendars). A child
    is only blocked from a list that's explicitly owned by somebody else.
    Sends the "unauthorized" error itself on failure - callers just need to
    `return` when this comes back False.
    """
    user_id = connection.user.id if connection.user else None
    if await async_is_adult(hass, user_id):
        return True
    entry = hass.config_entries.async_get_entry(entry_id)
    owner = entry.data.get(CONF_OWNER_USER_ID) if entry else None
    if not owner or owner == user_id:
        return True
    connection.send_error(
        msg["id"], "unauthorized", "Du kan bara lägga till/ändra i din egen lista."
    )
    return False


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/list_lists"})
@websocket_api.async_response
async def ws_list_lists(hass: HomeAssistant, connection, msg):
    entries = hass.config_entries.async_entries(DOMAIN)
    connection.send_result(msg["id"], {"lists": [_entry_to_dict(e) for e in entries]})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/create_list",
        vol.Required("name"): str,
        vol.Optional("list_type", default=LIST_TYPE_TASKS): str,
        vol.Optional("icon"): vol.Any(str, None),
        vol.Optional("color"): vol.Any(str, None),
        vol.Optional("owner_user_id"): vol.Any(str, None),
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
        data={
            "name": name,
            "list_type": msg.get("list_type", LIST_TYPE_TASKS),
            "icon": msg.get("icon"),
            "color": msg.get("color"),
            "owner_user_id": msg.get("owner_user_id"),
        },
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
        vol.Optional("list_type"): vol.Any(str, None),
        vol.Optional("icon"): vol.Any(str, None),
        vol.Optional("color"): vol.Any(str, None),
        vol.Optional("owner_user_id"): vol.Any(str, None),
    }
)
@websocket_api.async_response
async def ws_update_list(hass: HomeAssistant, connection, msg):
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "Listan hittades inte")
        return
    if not await _require_list_write_access(hass, connection, msg, msg["entry_id"]):
        return
    name = msg["name"].strip()
    hass.config_entries.async_update_entry(
        entry,
        title=name,
        data={
            **entry.data,
            CONF_NAME: name,
            CONF_LIST_TYPE: msg.get("list_type") or entry.data.get(CONF_LIST_TYPE, LIST_TYPE_TASKS),
            CONF_ICON: msg.get("icon"),
            CONF_COLOR: msg.get("color"),
            CONF_OWNER_USER_ID: msg.get("owner_user_id"),
        },
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
    if not await _require_list_write_access(hass, connection, msg, msg["entry_id"]):
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
        vol.Optional("section_id"): vol.Any(str, None),
        vol.Optional("recurrence"): vol.Any(RECURRENCE_SCHEMA, None),
    }
)
@websocket_api.async_response
async def ws_create_item(hass: HomeAssistant, connection, msg):
    entity = _get_entity(hass, msg["entry_id"])
    store = _get_store(hass, msg["entry_id"])
    if entity is None or store is None:
        connection.send_error(msg["id"], "not_found", "Listan hittades inte")
        return
    if not await _require_list_write_access(hass, connection, msg, msg["entry_id"]):
        return
    recurrence = Recurrence.from_dict(msg["recurrence"]) if msg.get("recurrence") else None
    due = _parse_due(msg.get("due"))
    if recurrence is not None and due is None:
        # Ingen förfallodag angiven för en ny återkommande uppgift - sätt
        # första tillfället till "nu + intervallet" istället för att lämna
        # den utan förfallodag (annars har rullnings-logiken i
        # async_update_todo_item inget datum att räkna vidare från).
        due = recurrence.next_date(dt_util.now().date())
    await entity.async_create_todo_item(
        TodoItem(
            summary=msg["summary"],
            status=TodoItemStatus.NEEDS_ACTION,
            description=msg.get("description"),
            due=due,
        )
    )
    extra_changes: dict = {}
    if msg.get("section_id"):
        extra_changes["section_id"] = msg["section_id"]
    if recurrence is not None:
        extra_changes["recurrence"] = recurrence
    if extra_changes:
        # async_create_todo_item ovan har redan lagt till uppgiften sist i
        # samma delade store/modell - sätt utökningsfälten direkt istället
        # för en extra rundtripp via klienten (samma modell som
        # set_item_extra, men i samma anrop som skapandet för en smidigare
        # "skapa direkt med sektion/upprepning"-flöde i panelen).
        model = await store.async_load()
        new_item = model.items[-1]
        model.update(new_item.uid, **extra_changes)
        await store.async_save()
        entity.async_write_ha_state()
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
    if not await _require_list_write_access(hass, connection, msg, msg["entry_id"]):
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
    if not await _require_list_write_access(hass, connection, msg, msg["entry_id"]):
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
    if not await _require_list_write_access(hass, connection, msg, msg["entry_id"]):
        return
    await entity.async_move_todo_item(msg["uid"], msg.get("previous_uid"))
    connection.send_result(msg["id"], {"ok": True})


def _roll_recurring_subtasks(old_subtasks: list, new_subtasks: list) -> list:
    """Mirrors the item-level rollover in todo.py's async_update_todo_item,
    but per subtask instead of per item: a subtask with its own recurrence
    that just got checked off (complete False -> True, matched by id, so
    an add/remove/reorder in the same save doesn't misfire this) is left
    at needs_action with its due date rolled forward, rather than staying
    checked - same "answer every occurrence, not just the first" reasoning,
    just scoped to one checklist entry instead of the whole item."""
    old_by_id = {s.id: s for s in old_subtasks}
    today = dt_util.now().date()
    rolled = []
    for sub in new_subtasks:
        old = old_by_id.get(sub.id)
        just_completed = old is not None and not old.complete and sub.complete
        if just_completed and sub.recurrence is not None:
            base = _parse_due(sub.due) or today
            if hasattr(base, "date"):
                base = base.date()
            next_due = sub.recurrence.next_date(base)
            rolled.append(
                Subtask(
                    id=sub.id,
                    summary=sub.summary,
                    complete=False,
                    due=next_due.isoformat(),
                    recurrence=sub.recurrence,
                )
            )
        else:
            rolled.append(sub)
    return rolled


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_item_extra",
        vol.Required("entry_id"): str,
        vol.Required("uid"): str,
        vol.Optional("assignee"): vol.Any(str, None),
        vol.Optional("subtasks"): [SUBTASK_SCHEMA],
        vol.Optional("section_id"): vol.Any(str, None),
        vol.Optional("recurrence"): vol.Any(RECURRENCE_SCHEMA, None),
    }
)
@websocket_api.async_response
async def ws_set_item_extra(hass: HomeAssistant, connection, msg):
    """Sparar delsteg, tilldelning, sektion och upprepning - utökningsdata, se store.py.

    Rör aldrig summary/status/due (det gör create/update_item ovan) - bara
    de fält HA:s todo-schema inte har plats för. description uppdateras
    dock indirekt när assignee/subtasks ändras, för att hålla
    sammanfattningsblocket i den fältet aktuellt (se combine_description).
    """
    store = _get_store(hass, msg["entry_id"])
    entity = _get_entity(hass, msg["entry_id"])
    if store is None or entity is None:
        connection.send_error(msg["id"], "not_found", "Listan hittades inte")
        return
    if not await _require_list_write_access(hass, connection, msg, msg["entry_id"]):
        return
    model = await store.async_load()
    item = model.get(msg["uid"])
    if item is None:
        connection.send_error(msg["id"], "not_found", "Uppgiften hittades inte")
        return
    changes: dict = {}
    if "assignee" in msg:
        changes["assignee"] = msg["assignee"]
    if "subtasks" in msg:
        changes["subtasks"] = _roll_recurring_subtasks(
            item.subtasks, [Subtask.from_dict(s) for s in msg["subtasks"]]
        )
    if "section_id" in msg:
        changes["section_id"] = msg["section_id"]
    if "recurrence" in msg:
        changes["recurrence"] = Recurrence.from_dict(msg["recurrence"]) if msg["recurrence"] else None
    if "assignee" in changes or "subtasks" in changes:
        # Håll description-sammanfattningen (syns i HA:s eget todo-kort
        # och för röstassistenten) i synk med den nya tilldelningen/
        # delstegen - se combine_description i store.py.
        new_assignee = changes.get("assignee", item.assignee)
        new_subtasks = changes.get("subtasks", item.subtasks)
        changes["description"] = combine_description(
            split_description(item.description), new_assignee, new_subtasks
        )
    model.update(msg["uid"], **changes)
    await store.async_save()
    entity.async_write_ha_state()
    connection.send_result(msg["id"], {"ok": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/copy_item",
        vol.Required("entry_id"): str,
        vol.Required("uid"): str,
        vol.Required("section_ids"): [vol.Any(str, None)],
    }
)
@websocket_api.async_response
async def ws_copy_item(hass: HomeAssistant, connection, msg):
    """Skapar en fristående kopia av en uppgift i varje angiven sektion.

    Varje kopia är en helt egen uppgift - eget uid, egen avbockningsstatus,
    inte samma uppgift taggad i flera rum (en uppgift har bara ett
    section_id, se store.py). Källuppgiften ändras aldrig. Kopian startar
    om helt: status/last_completed/reminder_sent nollställs och delstegen
    får nya id:n och blir oavbockade, medan titel/beskrivning/förfallodag/
    tilldelning/upprepning tas med som de var.
    """
    entity = _get_entity(hass, msg["entry_id"])
    store = _get_store(hass, msg["entry_id"])
    if entity is None or store is None:
        connection.send_error(msg["id"], "not_found", "Listan hittades inte")
        return
    if not await _require_list_write_access(hass, connection, msg, msg["entry_id"]):
        return
    model = await store.async_load()
    source = model.get(msg["uid"])
    if source is None:
        connection.send_error(msg["id"], "not_found", "Uppgiften hittades inte")
        return

    user_text = split_description(source.description)
    created_uids = []
    for section_id in msg["section_ids"]:
        new_subtasks = [
            Subtask(
                id=uuid.uuid4().hex,
                summary=s.summary,
                complete=False,
                due=s.due,
                recurrence=s.recurrence,
            )
            for s in source.subtasks
        ]
        copy = model.add(
            TodoItemData(
                uid="",
                summary=source.summary,
                status="needs_action",
                description=combine_description(user_text, source.assignee, new_subtasks),
                due=source.due,
                assignee=source.assignee,
                subtasks=new_subtasks,
                section_id=section_id,
                recurrence=source.recurrence,
            )
        )
        created_uids.append(copy.uid)

    await store.async_save()
    entity.async_write_ha_state()
    connection.send_result(msg["id"], {"uids": created_uids})


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/list_sections", vol.Required("entry_id"): str}
)
@websocket_api.async_response
async def ws_list_sections(hass: HomeAssistant, connection, msg):
    store = _get_store(hass, msg["entry_id"])
    if store is None:
        connection.send_error(msg["id"], "not_found", "Listan hittades inte")
        return
    model = await store.async_load()
    connection.send_result(msg["id"], {"sections": [_section_to_dict(s) for s in model.sections]})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/create_section",
        vol.Required("entry_id"): str,
        vol.Required("name"): str,
        vol.Optional("area_id"): vol.Any(str, None),
        vol.Optional("icon"): vol.Any(str, None),
    }
)
@websocket_api.async_response
async def ws_create_section(hass: HomeAssistant, connection, msg):
    store = _get_store(hass, msg["entry_id"])
    if store is None:
        connection.send_error(msg["id"], "not_found", "Listan hittades inte")
        return
    if not await _require_list_write_access(hass, connection, msg, msg["entry_id"]):
        return
    name = msg["name"].strip()
    if not name:
        connection.send_error(msg["id"], "invalid_input", "Namn krävs")
        return
    model = await store.async_load()
    section = model.add_section(Section(id="", name=name, area_id=msg.get("area_id"), icon=msg.get("icon")))
    await store.async_save()
    connection.send_result(msg["id"], {"section": _section_to_dict(section)})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/update_section",
        vol.Required("entry_id"): str,
        vol.Required("section_id"): str,
        vol.Required("name"): str,
        vol.Optional("area_id"): vol.Any(str, None),
        vol.Optional("icon"): vol.Any(str, None),
    }
)
@websocket_api.async_response
async def ws_update_section(hass: HomeAssistant, connection, msg):
    store = _get_store(hass, msg["entry_id"])
    if store is None:
        connection.send_error(msg["id"], "not_found", "Listan hittades inte")
        return
    if not await _require_list_write_access(hass, connection, msg, msg["entry_id"]):
        return
    name = msg["name"].strip()
    if not name:
        connection.send_error(msg["id"], "invalid_input", "Namn krävs")
        return
    model = await store.async_load()
    section = model.update_section(
        msg["section_id"], name=name, area_id=msg.get("area_id"), icon=msg.get("icon")
    )
    if section is None:
        connection.send_error(msg["id"], "not_found", "Sektionen hittades inte")
        return
    await store.async_save()
    connection.send_result(msg["id"], {"section": _section_to_dict(section)})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/delete_section",
        vol.Required("entry_id"): str,
        vol.Required("section_id"): str,
    }
)
@websocket_api.async_response
async def ws_delete_section(hass: HomeAssistant, connection, msg):
    """Tar bort sektionen. Dess uppgifter tas inte bort - se Section.delete_section."""
    store = _get_store(hass, msg["entry_id"])
    if store is None:
        connection.send_error(msg["id"], "not_found", "Listan hittades inte")
        return
    if not await _require_list_write_access(hass, connection, msg, msg["entry_id"]):
        return
    model = await store.async_load()
    model.delete_section(msg["section_id"])
    await store.async_save()
    connection.send_result(msg["id"], {"ok": True})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/list_areas"})
@websocket_api.async_response
async def ws_list_areas(hass: HomeAssistant, connection, msg):
    """HA:s egna areor (rum) - bekvämlighetslista för sektionens area-väljare.

    floor_id följer med så panelen kan gruppera sektionerna per våning (en
    sektion kopplad till en area ärver den areans våning) - se
    ws_list_floors och _groupSectionsByFloor i family-todo-panel.js.
    """
    registry = ar.async_get(hass)
    areas = [
        {"area_id": area.id, "name": area.name, "icon": area.icon, "floor_id": area.floor_id}
        for area in registry.async_list_areas()
    ]
    areas.sort(key=lambda a: a["name"])
    connection.send_result(msg["id"], {"areas": areas})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/list_floors"})
@websocket_api.async_response
async def ws_list_floors(hass: HomeAssistant, connection, msg):
    """HA:s egna våningar - för att gruppera sektioner (rum) per våning i panelen.

    Sorterade lägsta våning först; en våning utan angiven "level" (t.ex. en
    egen "Ute"-våning för utomhusareor, som inte hör till huset i den
    bemärkelsen) sorteras sist, efter alla riktiga våningsplan.
    """
    registry = fr.async_get(hass)
    floors = [
        {"floor_id": floor.floor_id, "name": floor.name, "icon": floor.icon, "level": floor.level}
        for floor in registry.async_list_floors()
    ]
    floors.sort(key=lambda f: (f["level"] is None, f["level"] if f["level"] is not None else 0, f["name"]))
    connection.send_result(msg["id"], {"floors": floors})


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


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/list_notify_services"})
@websocket_api.async_response
async def ws_list_notify_services(hass: HomeAssistant, connection, msg):
    """Alla registrerade notify.*-tjänster - underlag för Notiser-tabbens väljare."""
    services = sorted(hass.services.async_services().get("notify", {}).keys())
    connection.send_result(msg["id"], {"services": services})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/get_notify_map"})
@websocket_api.async_response
async def ws_get_notify_map(hass: HomeAssistant, connection, msg):
    notify_map = await async_get_notify_map_store(hass).async_load()
    connection.send_result(msg["id"], {"map": dict(notify_map)})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_notify_target",
        vol.Required("person_entity_id"): str,
        vol.Optional("service"): vol.Any(str, None),
    }
)
@websocket_api.async_response
async def ws_set_notify_target(hass: HomeAssistant, connection, msg):
    """Kopplar (eller, med service=None, kopplar bort) en persons notistjänst.

    Global, listoberoende - se notify_map.py för varför det inte går att
    härleda automatiskt vilken notify.*-tjänst som hör till en person.
    """
    await async_get_notify_map_store(hass).async_set(msg["person_entity_id"], msg.get("service"))
    connection.send_result(msg["id"], {"ok": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/send_test_notification",
        vol.Required("service"): str,
    }
)
@websocket_api.async_response
async def ws_send_test_notification(hass: HomeAssistant, connection, msg):
    """Skickar en engångs-testnotis till notify.<service> - "Skicka test"-knappen
    på Notiser-fliken, så man kan verifiera kopplingen utan att vänta på en
    riktig förfallen uppgift. Samma anropsform som den faktiska påminnelsen
    (se reminders.py), så ett lyckat test verkligen speglar hur en riktig
    påminnelse skulle bete sig.
    """
    try:
        await hass.services.async_call(
            "notify",
            msg["service"],
            {"title": "Att göra", "message": "Det här är en testnotis från Att göra-panelen 👋"},
            blocking=True,
        )
    except Exception as err:  # noqa: BLE001 - vilket fel som helst ska visas för användaren, inte krascha panelen
        _LOGGER.warning("Family Todo: testnotis till notify.%s misslyckades (%s)", msg["service"], err)
        connection.send_error(msg["id"], "send_failed", str(err) or "Kunde inte skicka notisen.")
        return
    connection.send_result(msg["id"], {"ok": True})


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
    websocket_api.async_register_command(hass, ws_copy_item)
    websocket_api.async_register_command(hass, ws_list_sections)
    websocket_api.async_register_command(hass, ws_create_section)
    websocket_api.async_register_command(hass, ws_update_section)
    websocket_api.async_register_command(hass, ws_delete_section)
    websocket_api.async_register_command(hass, ws_list_areas)
    websocket_api.async_register_command(hass, ws_list_floors)
    websocket_api.async_register_command(hass, ws_list_persons)
    websocket_api.async_register_command(hass, ws_list_notify_services)
    websocket_api.async_register_command(hass, ws_get_notify_map)
    websocket_api.async_register_command(hass, ws_set_notify_target)
    websocket_api.async_register_command(hass, ws_send_test_notification)

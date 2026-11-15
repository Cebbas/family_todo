"""Push reminder for overdue, un-reminded todo items.

Runs a periodic sweep (every REMINDER_CHECK_INTERVAL_SECONDS) over every
Family Todo list's items. An item gets exactly one reminder, fired once its
`due` datetime has passed while it's still `needs_action`, provided:

- `due` has a time component (a plain date like "2026-01-01" has no
  "klockslag" to remind at, so date-only items are silently skipped - see
  `_due_datetime`)
- its `assignee` matches a `person.*` entity's current friendly name (the
  same matching the panel's assignee dropdown already relies on)
- that person has a notify service configured in the NotifyMapStore (set up
  from the panel's "Notiser" tab)

Anything short of that (no time on `due`, no assignee, assignee not mapped
to a notify service) still marks the item as reminded - once - so a missing
mapping produces one log warning instead of one every sweep forever.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.components.todo import TodoItem, TodoItemStatus
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import CONF_OWNER_USER_ID, DOMAIN, REMINDER_CHECK_INTERVAL_SECONDS
from .notify_map import async_get_notify_map_store
from .permissions import async_is_adult

# Mobilappens "Klar"-knapp i påminnelsen (se _reminder_payload) - HA:s
# mobilapp skickar tillbaka knappens action-sträng i ett
# mobile_app_notification_action-event, som async_handle_notification_action
# lyssnar på. Formatet är DONE_ACTION_PREFIX + "<entry_id>::<uid>".
DONE_ACTION_PREFIX = "FAMILY_TODO_DONE::"
MOBILE_APP_ACTION_EVENT = "mobile_app_notification_action"


def _reminder_payload(list_name: str, entry_id: str, item) -> dict:
    """Notisens innehåll, med en "Klar"-knapp som bockar av direkt från mobilen.

    `data.actions` är mobilappens (iOS/Android) format för actionable
    notifications; andra notify-tjänster ignorerar fältet. `tag` gör att
    en ny påminnelse om samma uppgift ersätter den gamla istället för att
    staplas.
    """
    return {
        "title": list_name,
        "message": f"Påminnelse: {item.summary}",
        "data": {
            "tag": f"family_todo_{item.uid}",
            "actions": [{"action": f"{DONE_ACTION_PREFIX}{entry_id}::{item.uid}", "title": "Klar"}],
        },
    }

_LOGGER = logging.getLogger(__name__)


def _due_datetime(value: str | None) -> datetime | None:
    """Parse `due` into an aware datetime, or None if it has no time-of-day."""
    if not value or len(value) <= 10:  # "YYYY-MM-DD" - date only, nothing to remind "at"
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = dt_util.as_local(parsed)
    return parsed


async def _async_check_due_reminders(hass: HomeAssistant, _now) -> None:
    domain_data = hass.data.get(DOMAIN)
    if not domain_data:
        return

    notify_map = await async_get_notify_map_store(hass).async_load()
    person_entity_by_name = {
        state.attributes.get("friendly_name", state.entity_id): state.entity_id
        for state in hass.states.async_all("person")
    }
    now = dt_util.now()

    for entry_data in list(domain_data.values()):
        if not isinstance(entry_data, dict):
            continue  # skips notify_map_store etc - only config-entry dicts have "entity"
        entity = entry_data.get("entity")
        if entity is None:
            continue
        model = await entity._store.async_load()

        changed = False
        for item in model.items:
            if item.status == "completed" or item.reminder_sent:
                continue
            due_dt = _due_datetime(item.due)
            if due_dt is None or due_dt > now:
                continue

            person_entity_id = person_entity_by_name.get(item.assignee) if item.assignee else None
            service = notify_map.get(person_entity_id) if person_entity_id else None
            if service:
                try:
                    await hass.services.async_call(
                        "notify",
                        service,
                        _reminder_payload(entity.name, entity._entry.entry_id, item),
                        blocking=True,
                    )
                except Exception:  # noqa: BLE001 - en trasig notistjänst ska inte stoppa resten av sveepen
                    _LOGGER.exception(
                        "Family Todo: notify.%s misslyckades för påminnelsen %r (%s)",
                        service,
                        item.summary,
                        entity.name,
                    )
            else:
                _LOGGER.warning(
                    "Family Todo: kunde inte skicka påminnelse för %r (%s) - "
                    "tilldelad %r har ingen notistjänst kopplad under Notiser i panelen",
                    item.summary,
                    entity.name,
                    item.assignee,
                )
            item.reminder_sent = True
            changed = True

        if changed:
            await entity._store.async_save()


async def async_handle_notification_action(hass: HomeAssistant, event: Event) -> None:
    """Bockar av uppgiften när någon tryckt "Klar" i påminnelsen på mobilen.

    Samma väg som en avbockning i panelen (entitetens vanliga uppdatering),
    så en återkommande uppgift rullar vidare och loggas med vem som gjorde
    det. Samma behörighetsregel som panelen: ett barn kan bara bocka av i en
    lista som saknar ägare eller är dess egen (se ws_api._require_list_write_access).
    """
    action = (event.data or {}).get("action") or ""
    if not action.startswith(DONE_ACTION_PREFIX):
        return
    entry_id, sep, uid = action[len(DONE_ACTION_PREFIX):].partition("::")
    if not sep:
        return
    entry_data = (hass.data.get(DOMAIN) or {}).get(entry_id)
    entity = entry_data.get("entity") if isinstance(entry_data, dict) else None
    if entity is None:
        _LOGGER.warning("Family Todo: listan för \"Klar\"-knappen finns inte längre (%s)", entry_id)
        return

    user_id = event.context.user_id if event.context else None
    if not await async_is_adult(hass, user_id):
        owner = entity._entry.data.get(CONF_OWNER_USER_ID)
        if owner and owner != user_id:
            _LOGGER.warning("Family Todo: %s får inte bocka av i listan %s", user_id, entity.name)
            return

    model = await entity._store.async_load()
    item = model.get(uid)
    if item is None or item.status == "completed":
        return
    entity.async_set_context(event.context)
    await entity.async_update_todo_item(
        TodoItem(
            uid=item.uid,
            summary=item.summary,
            status=TodoItemStatus.COMPLETED,
            description=item.description,
            due=_due_value(item.due),
        )
    )


def _due_value(value: str | None):
    """`due` som date/datetime, så som TodoItem vill ha det (samma tolkning som todo.py)."""
    if not value:
        return None
    from datetime import date

    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def async_setup_reminders(hass: HomeAssistant) -> None:
    """Registrerar den periodiska påminnelse-koll för hela integrationens livstid."""

    async def _tick(now) -> None:
        await _async_check_due_reminders(hass, now)

    async_track_time_interval(hass, _tick, timedelta(seconds=REMINDER_CHECK_INTERVAL_SECONDS))

    async def _on_action(event: Event) -> None:
        await async_handle_notification_action(hass, event)

    hass.bus.async_listen(MOBILE_APP_ACTION_EVENT, _on_action)

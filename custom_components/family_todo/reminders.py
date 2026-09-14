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

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import DOMAIN, REMINDER_CHECK_INTERVAL_SECONDS
from .notify_map import async_get_notify_map_store

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
                        {"title": entity.name, "message": f"Påminnelse: {item.summary}"},
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


def async_setup_reminders(hass: HomeAssistant) -> None:
    """Registrerar den periodiska påminnelse-koll för hela integrationens livstid."""

    async def _tick(now) -> None:
        await _async_check_due_reminders(hass, now)

    async_track_time_interval(hass, _tick, timedelta(seconds=REMINDER_CHECK_INTERVAL_SECONDS))

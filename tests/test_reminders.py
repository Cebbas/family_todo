"""Tests for reminders.py: the due-date push reminder sweep."""
from datetime import timedelta

from homeassistant.components.todo import TodoItem
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.family_todo.const import DOMAIN
from custom_components.family_todo.notify_map import async_get_notify_map_store
from custom_components.family_todo.reminders import _async_check_due_reminders, _due_datetime
from custom_components.family_todo.store import FamilyTodoStore
from custom_components.family_todo.todo import FamilyTodoListEntity


# ---- _due_datetime: date-only values have no "klockslag" to remind at ----

def test_due_datetime_ignores_date_only_values():
    assert _due_datetime("2026-09-09") is None


def test_due_datetime_ignores_missing_value():
    assert _due_datetime(None) is None


def test_due_datetime_parses_naive_datetime_as_local_and_aware():
    parsed = _due_datetime("2026-09-09T18:30")
    assert (parsed.hour, parsed.minute) == (18, 30)
    assert parsed.tzinfo is not None


def test_due_datetime_rejects_unparsable_value():
    assert _due_datetime("not-a-date") is None


# ---- _async_check_due_reminders: needs a hass instance ----

async def _make_entity(hass, entry_id="entry1", name="Hushåll"):
    entry = MockConfigEntry(domain=DOMAIN, entry_id=entry_id, data={"name": name})
    store = FamilyTodoStore(hass, entry_id)
    await store.async_load()
    entity = FamilyTodoListEntity(entry, store)
    entity.hass = hass
    entity.entity_id = f"todo.{entry_id}"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {"entry": entry, "entity": entity}
    return entity


def _overdue() -> str:
    return (dt_util.now() - timedelta(minutes=5)).isoformat()


async def test_sends_notification_for_overdue_item_assigned_to_mapped_person(hass):
    entity = await _make_entity(hass)
    hass.states.async_set("person.anna", "home", {"friendly_name": "Anna"})
    await async_get_notify_map_store(hass).async_set("person.anna", "mobile_app_annas_phone")

    calls = []
    hass.services.async_register("notify", "mobile_app_annas_phone", lambda call: calls.append(call))

    await entity.async_create_todo_item(TodoItem(summary="Läxor"))
    uid = entity.todo_items[0].uid
    entity._model().update(uid, assignee="Anna", due=_overdue())

    await _async_check_due_reminders(hass, dt_util.now())

    assert len(calls) == 1
    assert calls[0].data["message"] == "Påminnelse: Läxor"
    assert entity._model().get(uid).reminder_sent is True


async def test_does_not_notify_before_due_time(hass):
    entity = await _make_entity(hass)
    hass.states.async_set("person.anna", "home", {"friendly_name": "Anna"})
    await async_get_notify_map_store(hass).async_set("person.anna", "mobile_app_annas_phone")
    calls = []
    hass.services.async_register("notify", "mobile_app_annas_phone", lambda call: calls.append(call))

    await entity.async_create_todo_item(TodoItem(summary="Om en timme"))
    uid = entity.todo_items[0].uid
    future = (dt_util.now() + timedelta(hours=1)).isoformat()
    entity._model().update(uid, assignee="Anna", due=future)

    await _async_check_due_reminders(hass, dt_util.now())

    assert calls == []
    assert entity._model().get(uid).reminder_sent is False


async def test_skips_completed_items(hass):
    entity = await _make_entity(hass)
    await entity.async_create_todo_item(TodoItem(summary="Klar uppgift"))
    uid = entity.todo_items[0].uid
    entity._model().update(uid, status="completed", due=_overdue())

    await _async_check_due_reminders(hass, dt_util.now())

    assert entity._model().get(uid).reminder_sent is False


async def test_skips_date_only_due_without_marking_reminded(hass):
    # Ett datum utan tid har inget "klockslag" att påminna vid - se _due_datetime.
    entity = await _make_entity(hass)
    await entity.async_create_todo_item(TodoItem(summary="Ingen tid satt"))
    uid = entity.todo_items[0].uid
    entity._model().update(uid, due="2020-01-01")

    await _async_check_due_reminders(hass, dt_util.now())

    assert entity._model().get(uid).reminder_sent is False


async def test_marks_reminded_without_notify_target_so_it_only_warns_once(hass):
    entity = await _make_entity(hass)
    await entity.async_create_todo_item(TodoItem(summary="Otilldelad"))
    uid = entity.todo_items[0].uid
    entity._model().update(uid, due=_overdue())  # ingen assignee, ingen mappning

    await _async_check_due_reminders(hass, dt_util.now())

    assert entity._model().get(uid).reminder_sent is True


async def test_does_not_resend_already_reminded_item(hass):
    entity = await _make_entity(hass)
    hass.states.async_set("person.anna", "home", {"friendly_name": "Anna"})
    await async_get_notify_map_store(hass).async_set("person.anna", "mobile_app_annas_phone")
    calls = []
    hass.services.async_register("notify", "mobile_app_annas_phone", lambda call: calls.append(call))

    await entity.async_create_todo_item(TodoItem(summary="Redan påmind"))
    uid = entity.todo_items[0].uid
    entity._model().update(uid, assignee="Anna", due=_overdue(), reminder_sent=True)

    await _async_check_due_reminders(hass, dt_util.now())

    assert calls == []

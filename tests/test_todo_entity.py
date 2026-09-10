"""Tests for FamilyTodoListEntity: create/update/delete/move + persistence.

Uses the entity directly (not through a full config entry setup) - `hass`
and `entity_id` are set by hand, which is enough for `async_write_ha_state`
to work without going through an entity platform.
"""
from datetime import date

from homeassistant.components.todo import TodoItem, TodoItemStatus
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.family_todo.const import DOMAIN
from custom_components.family_todo.store import FamilyTodoStore, Recurrence, Subtask
from custom_components.family_todo.todo import FamilyTodoListEntity


async def _make_entity(hass, entry_id="entry1", name="Hushåll"):
    entry = MockConfigEntry(domain=DOMAIN, entry_id=entry_id, data={"name": name})
    store = FamilyTodoStore(hass, entry_id)
    await store.async_load()
    entity = FamilyTodoListEntity(entry, store)
    entity.hass = hass
    entity.entity_id = f"todo.{entry_id}"
    return entity


async def test_create_item_adds_to_todo_items(hass):
    entity = await _make_entity(hass)
    await entity.async_create_todo_item(TodoItem(summary="Handla mjölk"))
    assert [i.summary for i in entity.todo_items] == ["Handla mjölk"]
    assert entity.todo_items[0].status == TodoItemStatus.NEEDS_ACTION


async def test_create_item_persists_across_new_store_instance(hass):
    entity = await _make_entity(hass, entry_id="entry_persist")
    await entity.async_create_todo_item(TodoItem(summary="Städa"))

    reloaded_store = FamilyTodoStore(hass, "entry_persist")
    model = await reloaded_store.async_load()
    assert [i.summary for i in model.items] == ["Städa"]


async def test_update_item_changes_status_and_summary(hass):
    entity = await _make_entity(hass)
    await entity.async_create_todo_item(TodoItem(summary="Diska"))
    uid = entity.todo_items[0].uid
    await entity.async_update_todo_item(
        TodoItem(uid=uid, summary="Diska klart", status=TodoItemStatus.COMPLETED)
    )
    item = entity.todo_items[0]
    assert item.summary == "Diska klart"
    assert item.status == TodoItemStatus.COMPLETED


async def test_update_item_preserves_assignee_and_subtasks(hass):
    entity = await _make_entity(hass)
    await entity.async_create_todo_item(TodoItem(summary="Handla"))
    uid = entity.todo_items[0].uid
    entity._model().update(uid, assignee="Anna")

    await entity.async_update_todo_item(TodoItem(uid=uid, summary="Handla mat", status=TodoItemStatus.NEEDS_ACTION))

    assert entity._model().get(uid).assignee == "Anna"


async def test_delete_item_removes_it(hass):
    entity = await _make_entity(hass)
    await entity.async_create_todo_item(TodoItem(summary="Ta bort mig"))
    uid = entity.todo_items[0].uid
    await entity.async_delete_todo_items([uid])
    assert entity.todo_items == []


async def test_move_item_reorders(hass):
    entity = await _make_entity(hass)
    await entity.async_create_todo_item(TodoItem(summary="Först"))
    await entity.async_create_todo_item(TodoItem(summary="Sedan"))
    first_uid = entity.todo_items[0].uid
    second_uid = entity.todo_items[1].uid

    await entity.async_move_todo_item(second_uid, None)

    assert [i.uid for i in entity.todo_items] == [second_uid, first_uid]


# ---- recurrence: completing a recurring item rolls it forward instead ----

async def test_completing_recurring_item_reopens_it_with_next_due_date(hass):
    entity = await _make_entity(hass)
    await entity.async_create_todo_item(TodoItem(summary="Byta sängkläder"))
    uid = entity.todo_items[0].uid
    entity._model().update(uid, recurrence=Recurrence(interval=2, unit="weeks"), due="2026-09-09")

    await entity.async_update_todo_item(
        TodoItem(uid=uid, summary="Byta sängkläder", status=TodoItemStatus.COMPLETED)
    )

    item = entity._model().get(uid)
    assert item.status == "needs_action"
    assert item.due == "2026-09-23"


async def test_completing_recurring_item_sets_last_completed(hass):
    entity = await _make_entity(hass)
    await entity.async_create_todo_item(TodoItem(summary="Dammsuga"))
    uid = entity.todo_items[0].uid
    entity._model().update(uid, recurrence=Recurrence(interval=1, unit="weeks"))

    await entity.async_update_todo_item(TodoItem(uid=uid, summary="Dammsuga", status=TodoItemStatus.COMPLETED))

    assert entity._model().get(uid).last_completed == dt_util.now().date().isoformat()


async def test_completing_recurring_item_resets_subtasks(hass):
    entity = await _make_entity(hass)
    await entity.async_create_todo_item(TodoItem(summary="Städa badrum"))
    uid = entity.todo_items[0].uid
    entity._model().update(
        uid,
        recurrence=Recurrence(interval=1, unit="weeks"),
        subtasks=[Subtask("s1", "Skura golvet", complete=True), Subtask("s2", "Torka speglar", complete=True)],
    )

    await entity.async_update_todo_item(
        TodoItem(uid=uid, summary="Städa badrum", status=TodoItemStatus.COMPLETED)
    )

    subtasks = entity._model().get(uid).subtasks
    assert [s.complete for s in subtasks] == [False, False]
    assert [s.summary for s in subtasks] == ["Skura golvet", "Torka speglar"]


async def test_completing_item_without_recurrence_stays_completed(hass):
    entity = await _make_entity(hass)
    await entity.async_create_todo_item(TodoItem(summary="Engångsuppgift"))
    uid = entity.todo_items[0].uid

    await entity.async_update_todo_item(
        TodoItem(uid=uid, summary="Engångsuppgift", status=TodoItemStatus.COMPLETED)
    )

    assert entity._model().get(uid).status == "completed"


# ---- description mirrors assignee/delsteg for HA's own todo card/voice ----

async def test_update_item_mirrors_assignee_into_description(hass):
    entity = await _make_entity(hass)
    await entity.async_create_todo_item(TodoItem(summary="Handla"))
    uid = entity.todo_items[0].uid
    entity._model().update(uid, assignee="Anna")

    await entity.async_update_todo_item(TodoItem(uid=uid, summary="Handla mat", status=TodoItemStatus.NEEDS_ACTION))

    assert "👤 Anna" in entity.todo_items[0].description


async def test_update_item_preserves_users_own_description_text(hass):
    entity = await _make_entity(hass)
    await entity.async_create_todo_item(TodoItem(summary="Handla"))
    uid = entity.todo_items[0].uid
    entity._model().update(uid, assignee="Anna")

    await entity.async_update_todo_item(
        TodoItem(uid=uid, summary="Handla", status=TodoItemStatus.NEEDS_ACTION, description="Glöm inte kvittot")
    )

    description = entity.todo_items[0].description
    assert description.startswith("Glöm inte kvittot")
    assert "👤 Anna" in description


async def test_update_item_does_not_duplicate_meta_block_on_repeated_saves(hass):
    # HA:s eget redigeringsläge skickar tillbaka hela description-fältet
    # oförändrat (inklusive vårt block) varje gång - ska aldrig staplas.
    entity = await _make_entity(hass)
    await entity.async_create_todo_item(TodoItem(summary="Handla"))
    uid = entity.todo_items[0].uid
    entity._model().update(uid, assignee="Anna")

    for _ in range(3):
        await entity.async_update_todo_item(
            TodoItem(
                uid=uid,
                summary="Handla",
                status=TodoItemStatus.NEEDS_ACTION,
                description=entity.todo_items[0].description,
            )
        )

    assert entity.todo_items[0].description.count("Family Todo") == 1


async def test_uncompleting_recurring_item_does_not_roll_forward(hass):
    # Bara övergången needs_action -> completed ska rulla vidare - att bocka
    # UR en redan avklarad uppgift (ångra) ska bara öppna den igen som vanligt.
    # Caller skickar (precis som ws_update_item/panelen alltid gör) hela
    # itemet inklusive due, inte bara det ändrade fältet.
    entity = await _make_entity(hass)
    await entity.async_create_todo_item(TodoItem(summary="Vattna blommor"))
    uid = entity.todo_items[0].uid
    entity._model().update(uid, recurrence=Recurrence(interval=1, unit="weeks"), status="completed", due="2026-09-09")

    await entity.async_update_todo_item(
        TodoItem(
            uid=uid,
            summary="Vattna blommor",
            status=TodoItemStatus.NEEDS_ACTION,
            due=date(2026, 9, 9),
        )
    )

    item = entity._model().get(uid)
    assert item.status == "needs_action"
    assert item.due == "2026-09-09"

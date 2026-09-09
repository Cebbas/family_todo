"""Tests for FamilyTodoListEntity: create/update/delete/move + persistence.

Uses the entity directly (not through a full config entry setup) - `hass`
and `entity_id` are set by hand, which is enough for `async_write_ha_state`
to work without going through an entity platform.
"""
from homeassistant.components.todo import TodoItem, TodoItemStatus
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.family_todo.const import DOMAIN
from custom_components.family_todo.store import FamilyTodoStore
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

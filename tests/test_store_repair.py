"""FamilyTodoStore: repair issue + backup when stored data can't be fully read."""
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store

from custom_components.family_todo.const import DOMAIN, STORAGE_KEY_PREFIX, STORAGE_VERSION
from custom_components.family_todo.store import FamilyTodoStore, corrupt_issue_id


async def test_broken_data_creates_repair_issue_and_keeps_good_items(hass, hass_storage):
    hass_storage[f"{STORAGE_KEY_PREFIX}e1"] = {
        "version": STORAGE_VERSION,
        "key": f"{STORAGE_KEY_PREFIX}e1",
        "data": {"items": {"ok": {"uid": "ok", "summary": "Bra"}, "bad": {"nope": 1}}, "order": []},
    }
    store = FamilyTodoStore(hass, "e1", "Hushåll")
    model = await store.async_load()

    assert [i.summary for i in model.items] == ["Bra"]
    issue = ir.async_get(hass).async_get_issue(DOMAIN, corrupt_issue_id("e1"))
    assert issue is not None
    assert issue.translation_placeholders["name"] == "Hushåll"
    assert issue.translation_placeholders["count"] == "1"

    backup_key = issue.translation_placeholders["backup"].removeprefix(".storage/")
    backup = await Store(hass, STORAGE_VERSION, backup_key).async_load()
    assert "bad" in backup["items"]  # originalet, inklusive den trasiga posten


async def test_clean_load_clears_old_repair_issue(hass):
    ir.async_create_issue(
        hass, DOMAIN, corrupt_issue_id("e1"), is_fixable=False,
        severity=ir.IssueSeverity.ERROR, translation_key="corrupt_list",
    )
    await FamilyTodoStore(hass, "e1").async_load()
    assert ir.async_get(hass).async_get_issue(DOMAIN, corrupt_issue_id("e1")) is None


async def test_remove_clears_repair_issue(hass):
    ir.async_create_issue(
        hass, DOMAIN, corrupt_issue_id("e1"), is_fixable=False,
        severity=ir.IssueSeverity.ERROR, translation_key="corrupt_list",
    )
    await FamilyTodoStore(hass, "e1").async_remove()
    assert ir.async_get(hass).async_get_issue(DOMAIN, corrupt_issue_id("e1")) is None

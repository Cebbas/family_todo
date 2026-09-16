"""Tests for the websocket handlers that touch things outside store.py -
mainly ws_list_areas, since it depends on HA's area registry API shape
(easy to silently break across HA versions, unlike the pure model tests).
"""
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import floor_registry as fr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.family_todo import ws_api
from custom_components.family_todo.const import CONF_NAME, CONF_OWNER_USER_ID, DOMAIN
from custom_components.family_todo.store import FamilyTodoStore, Section
from custom_components.family_todo.todo import FamilyTodoListEntity


class _FakeConnection:
    def __init__(self, user_id=None):
        self.result = None
        self.error = None
        # None (delad kiosk/okänd inloggning) matchar produktionskoden, som
        # bara läser connection.user.id om connection.user inte är None -
        # se _require_list_write_access.
        self.user = _FakeUser(user_id) if user_id else None

    def send_result(self, msg_id, data=None):
        self.result = data

    def send_error(self, msg_id, code, message):
        self.error = (code, message)


class _FakeUser:
    def __init__(self, user_id):
        self.id = user_id


class _FakePersonsStore:
    """Minsta möjliga stand-in för family_planner:s Store, se permissions.py."""

    def __init__(self, persons):
        self._persons = persons

    async def async_load(self):
        return {"persons": self._persons}


async def test_list_areas_returns_registered_areas(hass):
    registry = ar.async_get(hass)
    registry.async_create("Kök")
    registry.async_create("Badrum")

    # ws_list_areas is decorated with @websocket_api.async_response, which
    # turns it into a *sync* function that schedules a background task
    # instead of returning a coroutine - `.__wrapped__` (set by functools.wraps
    # inside async_response) gives back the real coroutine function so the
    # test can await it directly instead of racing a background task.
    connection = _FakeConnection()
    await ws_api.ws_list_areas.__wrapped__(hass, connection, {"id": 1})

    names = sorted(a["name"] for a in connection.result["areas"])
    assert names == ["Badrum", "Kök"]
    assert all("area_id" in a for a in connection.result["areas"])


async def test_list_areas_empty_when_none_registered(hass):
    connection = _FakeConnection()
    await ws_api.ws_list_areas.__wrapped__(hass, connection, {"id": 1})
    assert connection.result["areas"] == []


async def test_list_areas_includes_floor_id(hass):
    floor = fr.async_get(hass).async_create("Undervåning", level=1)
    registry = ar.async_get(hass)
    area = registry.async_create("Kök")
    registry.async_update(area.id, floor_id=floor.floor_id)
    registry.async_create("Förådd")  # ingen våning satt

    connection = _FakeConnection()
    await ws_api.ws_list_areas.__wrapped__(hass, connection, {"id": 1})

    by_name = {a["name"]: a for a in connection.result["areas"]}
    assert by_name["Kök"]["floor_id"] == floor.floor_id
    assert by_name["Förådd"]["floor_id"] is None


async def test_list_floors_sorted_by_level_with_no_level_last(hass):
    registry = fr.async_get(hass)
    registry.async_create("Övervåning", level=2)
    registry.async_create("Ute", level=None)
    registry.async_create("Undervåning", level=1)

    connection = _FakeConnection()
    await ws_api.ws_list_floors.__wrapped__(hass, connection, {"id": 1})

    names = [f["name"] for f in connection.result["floors"]]
    assert names == ["Undervåning", "Övervåning", "Ute"]


async def test_list_floors_empty_when_none_registered(hass):
    connection = _FakeConnection()
    await ws_api.ws_list_floors.__wrapped__(hass, connection, {"id": 1})
    assert connection.result["floors"] == []


# ---- notify map: person -> notify service, used by reminders.py ----

async def test_list_notify_services_returns_registered_notify_domain_services(hass):
    hass.services.async_register("notify", "mobile_app_annas_phone", lambda call: None)
    hass.services.async_register("notify", "mobile_app_sebbes_phone", lambda call: None)

    connection = _FakeConnection()
    await ws_api.ws_list_notify_services.__wrapped__(hass, connection, {"id": 1})

    assert connection.result["services"] == ["mobile_app_annas_phone", "mobile_app_sebbes_phone"]


async def test_get_notify_map_empty_by_default(hass):
    connection = _FakeConnection()
    await ws_api.ws_get_notify_map.__wrapped__(hass, connection, {"id": 1})
    assert connection.result["map"] == {}


async def test_set_notify_target_then_get_notify_map_round_trips(hass):
    await ws_api.ws_set_notify_target.__wrapped__(
        hass,
        _FakeConnection(),
        {"id": 1, "person_entity_id": "person.anna", "service": "mobile_app_annas_phone"},
    )

    connection = _FakeConnection()
    await ws_api.ws_get_notify_map.__wrapped__(hass, connection, {"id": 2})

    assert connection.result["map"] == {"person.anna": "mobile_app_annas_phone"}


async def test_set_notify_target_with_no_service_clears_mapping(hass):
    await ws_api.ws_set_notify_target.__wrapped__(
        hass,
        _FakeConnection(),
        {"id": 1, "person_entity_id": "person.anna", "service": "mobile_app_annas_phone"},
    )
    await ws_api.ws_set_notify_target.__wrapped__(
        hass, _FakeConnection(), {"id": 2, "person_entity_id": "person.anna"}
    )

    connection = _FakeConnection()
    await ws_api.ws_get_notify_map.__wrapped__(hass, connection, {"id": 3})

    assert connection.result["map"] == {}


async def test_send_test_notification_calls_the_notify_service(hass):
    calls = []
    hass.services.async_register("notify", "annas_phone", lambda call: calls.append(call.data))

    connection = _FakeConnection()
    await ws_api.ws_send_test_notification.__wrapped__(
        hass, connection, {"id": 1, "service": "annas_phone"}
    )

    assert connection.error is None
    assert connection.result == {"ok": True}
    assert len(calls) == 1
    assert "test" in calls[0]["message"].lower()


async def test_send_test_notification_reports_error_when_service_fails(hass):
    def _boom(call):
        raise RuntimeError("ingen anslutning")

    hass.services.async_register("notify", "trasig_tjanst", _boom)

    connection = _FakeConnection()
    await ws_api.ws_send_test_notification.__wrapped__(
        hass, connection, {"id": 1, "service": "trasig_tjanst"}
    )

    assert connection.result is None
    assert connection.error is not None
    assert connection.error[0] == "send_failed"


async def test_send_test_notification_reports_error_for_unknown_service(hass):
    connection = _FakeConnection()
    await ws_api.ws_send_test_notification.__wrapped__(
        hass, connection, {"id": 1, "service": "finns_inte"}
    )

    assert connection.result is None
    assert connection.error is not None
    assert connection.error[0] == "send_failed"


# ---- adult/child write permission (create_item as the representative case -
# every other gated handler in ws_api.py calls the same
# _require_list_write_access helper right after the same not_found check) ----


async def _make_list(hass, entry_id, owner_user_id=None):
    """Wires up a config entry + entity the same way todo.py's
    async_setup_entry does, so ws_api's _get_entity/_get_store and
    hass.config_entries.async_get_entry (used by _require_list_write_access)
    both resolve it.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        data={CONF_NAME: "Lista", CONF_OWNER_USER_ID: owner_user_id},
    )
    entry.add_to_hass(hass)
    store = FamilyTodoStore(hass, entry_id)
    await store.async_load()
    entity = FamilyTodoListEntity(entry, store)
    entity.hass = hass
    entity.entity_id = f"todo.{entry_id}"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {"entity": entity}
    return entity


async def test_child_blocked_from_writing_another_persons_list(hass):
    hass.data["family_planner"] = _FakePersonsStore(
        [{"name": "Nadine", "ha_user_id": "nadine-uid", "role": "child"}]
    )
    entity = await _make_list(hass, "naomis_list", owner_user_id="naomi-uid")

    connection = _FakeConnection(user_id="nadine-uid")
    await ws_api.ws_create_item.__wrapped__(
        hass, connection, {"id": 1, "entry_id": "naomis_list", "summary": "Smyger in en uppgift"}
    )

    assert connection.error is not None
    assert connection.error[0] == "unauthorized"
    assert entity.todo_items == []


async def test_child_can_write_own_list(hass):
    hass.data["family_planner"] = _FakePersonsStore(
        [{"name": "Nadine", "ha_user_id": "nadine-uid", "role": "child"}]
    )
    entity = await _make_list(hass, "nadines_list", owner_user_id="nadine-uid")

    connection = _FakeConnection(user_id="nadine-uid")
    await ws_api.ws_create_item.__wrapped__(
        hass, connection, {"id": 1, "entry_id": "nadines_list", "summary": "Läxor"}
    )

    assert connection.error is None
    assert [i.summary for i in entity.todo_items] == ["Läxor"]


async def test_child_can_write_unowned_shared_list(hass):
    hass.data["family_planner"] = _FakePersonsStore(
        [{"name": "Nadine", "ha_user_id": "nadine-uid", "role": "child"}]
    )
    entity = await _make_list(hass, "handla", owner_user_id=None)

    connection = _FakeConnection(user_id="nadine-uid")
    await ws_api.ws_create_item.__wrapped__(
        hass, connection, {"id": 1, "entry_id": "handla", "summary": "Mjölk"}
    )

    assert connection.error is None
    assert [i.summary for i in entity.todo_items] == ["Mjölk"]


async def test_adult_can_write_anyones_list(hass):
    hass.data["family_planner"] = _FakePersonsStore(
        [{"name": "Sebastian", "ha_user_id": "sebastian-uid", "role": "adult"}]
    )
    entity = await _make_list(hass, "naomis_list", owner_user_id="naomi-uid")

    connection = _FakeConnection(user_id="sebastian-uid")
    await ws_api.ws_create_item.__wrapped__(
        hass, connection, {"id": 1, "entry_id": "naomis_list", "summary": "Kom ihåg tandläkaren"}
    )

    assert connection.error is None
    assert [i.summary for i in entity.todo_items] == ["Kom ihåg tandläkaren"]


async def test_unmatched_login_treated_as_adult(hass):
    """Ingen Family Planner-person med det ha_user_id:t - fail open, se permissions.py."""
    hass.data["family_planner"] = _FakePersonsStore(
        [{"name": "Nadine", "ha_user_id": "nadine-uid", "role": "child"}]
    )
    entity = await _make_list(hass, "naomis_list", owner_user_id="naomi-uid")

    connection = _FakeConnection(user_id="okand-uid")
    await ws_api.ws_create_item.__wrapped__(
        hass, connection, {"id": 1, "entry_id": "naomis_list", "summary": "Okänd användare"}
    )

    assert connection.error is None
    assert [i.summary for i in entity.todo_items] == ["Okänd användare"]


async def test_family_planner_not_installed_treated_as_adult(hass):
    """hass.data har ingen "family_planner"-store alls - fail open, se permissions.py."""
    entity = await _make_list(hass, "naomis_list", owner_user_id="naomi-uid")

    connection = _FakeConnection(user_id="nadine-uid")
    await ws_api.ws_create_item.__wrapped__(
        hass, connection, {"id": 1, "entry_id": "naomis_list", "summary": "Ingen family_planner"}
    )

    assert connection.error is None
    assert [i.summary for i in entity.todo_items] == ["Ingen family_planner"]


# ---- copy_item: fristående kopior av en uppgift till flera rum/sektioner ----


def _add_sections(entity, *names):
    model = entity._model()
    return [model.add_section(Section(id="", name=name)) for name in names]


async def test_copy_item_creates_independent_copy_per_section(hass):
    entity = await _make_list(hass, "list1")
    kok, tvatt = _add_sections(entity, "Kök", "Tvättstugan")

    connection = _FakeConnection()
    await ws_api.ws_create_item.__wrapped__(
        hass, connection, {"id": 1, "entry_id": "list1", "summary": "Dammsug"}
    )
    source_uid = entity.todo_items[0].uid
    entity._model().update(source_uid, section_id=kok.id)
    await entity._store.async_save()

    connection = _FakeConnection()
    await ws_api.ws_copy_item.__wrapped__(
        hass,
        connection,
        {"id": 2, "entry_id": "list1", "uid": source_uid, "section_ids": [tvatt.id]},
    )

    assert connection.error is None
    (new_uid,) = connection.result["uids"]
    assert new_uid != source_uid

    original = entity._model().get(source_uid)
    copy = entity._model().get(new_uid)
    assert original.section_id == kok.id  # källan orörd
    assert copy.section_id == tvatt.id
    assert copy.summary == "Dammsug"
    assert copy.status == "needs_action"


async def test_copy_item_to_multiple_sections_at_once(hass):
    entity = await _make_list(hass, "list1")
    a, b, c = _add_sections(entity, "A", "B", "C")

    await ws_api.ws_create_item.__wrapped__(
        hass, _FakeConnection(), {"id": 1, "entry_id": "list1", "summary": "Damma"}
    )
    source_uid = entity.todo_items[0].uid

    connection = _FakeConnection()
    await ws_api.ws_copy_item.__wrapped__(
        hass,
        connection,
        {"id": 2, "entry_id": "list1", "uid": source_uid, "section_ids": [a.id, b.id, c.id]},
    )

    assert len(connection.result["uids"]) == 3
    section_ids = sorted(entity._model().get(uid).section_id for uid in connection.result["uids"])
    assert section_ids == sorted([a.id, b.id, c.id])


def test_copy_item_resets_subtasks_and_completion():
    """Ren modell-nivå (ingen hass behövs) - se test_store.py:s stil."""
    from custom_components.family_todo.store import Subtask, TodoItemData, TodoListData

    model = TodoListData()
    source = model.add(
        TodoItemData(
            uid="",
            summary="Städa",
            status="completed",
            subtasks=[Subtask(id="s1", summary="Dammsug", complete=True)],
            last_completed="2026-01-01",
            reminder_sent=True,
        )
    )
    copy = model.add(
        TodoItemData(
            uid="",
            summary=source.summary,
            status="needs_action",
            subtasks=[Subtask(id="new", summary=s.summary, complete=False) for s in source.subtasks],
        )
    )
    assert copy.status == "needs_action"
    assert copy.last_completed is None
    assert copy.reminder_sent is False
    assert copy.subtasks[0].complete is False
    assert copy.subtasks[0].id != source.subtasks[0].id


async def test_child_blocked_from_copying_into_another_persons_list(hass):
    hass.data["family_planner"] = _FakePersonsStore(
        [{"name": "Nadine", "ha_user_id": "nadine-uid", "role": "child"}]
    )
    entity = await _make_list(hass, "naomis_list", owner_user_id="naomi-uid")
    (section,) = _add_sections(entity, "Kök")
    await ws_api.ws_create_item.__wrapped__(
        hass, _FakeConnection(user_id="naomi-uid"), {"id": 1, "entry_id": "naomis_list", "summary": "X"}
    )
    source_uid = entity.todo_items[0].uid

    connection = _FakeConnection(user_id="nadine-uid")
    await ws_api.ws_copy_item.__wrapped__(
        hass,
        connection,
        {"id": 2, "entry_id": "naomis_list", "uid": source_uid, "section_ids": [section.id]},
    )

    assert connection.error is not None
    assert connection.error[0] == "unauthorized"
    assert len(entity.todo_items) == 1  # ingen kopia skapades

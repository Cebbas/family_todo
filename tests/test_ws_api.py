"""Tests for the websocket handlers that touch things outside store.py -
mainly ws_list_areas, since it depends on HA's area registry API shape
(easy to silently break across HA versions, unlike the pure model tests).
"""
from homeassistant.helpers import area_registry as ar

from custom_components.family_todo import ws_api


class _FakeConnection:
    def __init__(self):
        self.result = None
        self.error = None

    def send_result(self, msg_id, data=None):
        self.result = data

    def send_error(self, msg_id, code, message):
        self.error = (code, message)


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

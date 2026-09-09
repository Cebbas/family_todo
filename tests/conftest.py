"""Shared fixtures for the Family Todo test suite.

Only tests that actually need a running Home Assistant instance (entity,
config flow, storage-through-hass) request the `hass` fixture explicitly -
the pure model tests in test_store.py run as plain sync functions with no
event loop, and an autouse dependency on `hass` would force one on them too.
"""
pytest_plugins = "pytest_homeassistant_custom_component"

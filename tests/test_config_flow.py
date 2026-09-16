"""Guards against module-level errors in config_flow.py.

A plain import is enough to catch the exact bug this is testing for: a
top-level expression (building _USER_SCHEMA) that referenced
`selector.UserSelector()`, a class that doesn't exist on every HA core
version. Nothing else in this test suite imports config_flow.py or drives a
real config flow - the other tests all construct a MockConfigEntry directly,
bypassing it entirely - so this module-level crash only ever surfaced live,
breaking every Family Todo list's startup at once. No `hass` fixture needed;
this is a pure import check, same style as test_store.py.
"""


def test_config_flow_module_imports_without_error():
    import custom_components.family_todo.config_flow  # noqa: F401

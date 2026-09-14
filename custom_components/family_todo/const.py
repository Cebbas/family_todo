"""Constants for the Family Todo integration."""

DOMAIN = "family_todo"

CONF_NAME = "name"
CONF_ICON = "icon"
CONF_COLOR = "color"

DEFAULT_ICON = "mdi:format-list-checks"

PLATFORMS = ["todo"]

PANEL_URL_PATH = "family-todo"
PANEL_TITLE = "Att göra"
PANEL_ICON = "mdi:format-list-checks"

STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = "family_todo_list_"

# Global (listoberoende) lagring av vilken notify.*-tjänst varje person ska
# få påminnelser skickade till, se notify_map.py.
NOTIFY_MAP_STORAGE_VERSION = 1
NOTIFY_MAP_STORAGE_KEY = "family_todo_notify_map"

# Hur ofta reminders.py letar efter förfallna, oavbockade uppgifter.
REMINDER_CHECK_INTERVAL_SECONDS = 60

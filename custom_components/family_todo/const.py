"""Constants for the Family Todo integration."""

DOMAIN = "family_todo"

CONF_NAME = "name"
CONF_ICON = "icon"
CONF_COLOR = "color"
# HA user_id för listans "ägare" (valfri) - se permissions.py/ws_api.py.
# Ett barn (role: "child" i Family Planner) får bara skriva i en lista där
# owner_user_id matchar dem själva; vuxna och listor utan ägare satt är
# opåverkade.
CONF_OWNER_USER_ID = "owner_user_id"

# What kind of list this is - changes which fields the panel shows on an
# item (tasks: full editor with assignee/due/recurrence/subtasks; shopping:
# just title + section, a faster add/check-off flow for standing in a
# store). Purely a panel-UI/default-icon distinction - both are ordinary
# todo.* entities underneath, same store/CRUD either way.
CONF_LIST_TYPE = "list_type"
LIST_TYPE_TASKS = "tasks"
LIST_TYPE_SHOPPING = "shopping"
LIST_TYPES = [LIST_TYPE_TASKS, LIST_TYPE_SHOPPING]

DEFAULT_ICON = "mdi:format-list-checks"
DEFAULT_SHOPPING_ICON = "mdi:cart"

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

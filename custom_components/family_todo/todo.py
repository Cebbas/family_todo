"""The todo.* entity for a single Family Todo list."""
from __future__ import annotations

import logging

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    CONF_COLOR,
    CONF_ICON,
    CONF_LIST_TYPE,
    CONF_NAME,
    DEFAULT_ICON,
    DEFAULT_SHOPPING_ICON,
    DOMAIN,
    LIST_TYPE_SHOPPING,
)
from .store import FamilyTodoStore, Subtask, TodoItemData, combine_description, split_description

_LOGGER = logging.getLogger(__name__)

_SUPPORTED_FEATURES = (
    TodoListEntityFeature.CREATE_TODO_ITEM
    | TodoListEntityFeature.UPDATE_TODO_ITEM
    | TodoListEntityFeature.DELETE_TODO_ITEM
    | TodoListEntityFeature.MOVE_TODO_ITEM
    | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    | TodoListEntityFeature.SET_DUE_DATE_ON_ITEM
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    store = FamilyTodoStore(hass, entry.entry_id)
    await store.async_load()
    entity = FamilyTodoListEntity(entry, store)
    hass.data[DOMAIN][entry.entry_id]["entity"] = entity
    async_add_entities([entity])


class FamilyTodoListEntity(TodoListEntity):
    """En familjelista, backad av en egen FamilyTodoStore.

    Delsteg och tilldelning (`assignee`) är utökningsdata utanför HA:s
    `todo`-schema - de lagras i samma store men fälten rörs aldrig av
    async_create/update/delete_todo_item, bara av sidopanelens
    websocket-anrop (se ws_api.py). En sammanfattning av dem speglas dock
    in i `description` (se combine_description/split_description i
    store.py), så den vanliga HA-todo-ytan (röstassistent, standardkortet)
    ändå får se tilldelning och delsteg-status, inte bara ren text.
    """

    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, store: FamilyTodoStore) -> None:
        self._entry = entry
        self._store = store
        self._attr_unique_id = entry.entry_id
        self._attr_name = entry.data.get(CONF_NAME, entry.title)
        default_icon = (
            DEFAULT_SHOPPING_ICON if entry.data.get(CONF_LIST_TYPE) == LIST_TYPE_SHOPPING else DEFAULT_ICON
        )
        self._attr_icon = entry.data.get(CONF_ICON) or default_icon
        self._attr_supported_features = _SUPPORTED_FEATURES

    @property
    def extra_state_attributes(self) -> dict:
        return {"color": self._entry.data.get(CONF_COLOR)}

    def _model(self):
        return self._store._data  # already loaded in async_setup_entry

    @property
    def todo_items(self) -> list[TodoItem]:
        return [
            TodoItem(
                uid=item.uid,
                summary=item.summary,
                status=TodoItemStatus(item.status),
                description=item.description,
                due=_parse_due(item.due),
            )
            for item in self._model().items
        ]

    async def async_create_todo_item(self, item: TodoItem) -> None:
        model = self._model()
        model.add(
            TodoItemData(
                uid="",
                summary=item.summary or "",
                status=(item.status or TodoItemStatus.NEEDS_ACTION).value,
                description=item.description,
                due=item.due.isoformat() if item.due else None,
            )
        )
        await self._store.async_save()
        self.async_write_ha_state()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        model = self._model()
        existing = model.get(item.uid)
        new_status = (item.status or TodoItemStatus.NEEDS_ACTION).value
        due = item.due.isoformat() if item.due else None
        # split_description tar bort ett ev. redan befintligt tilldelnings-/
        # delsteg-block innan vi bygger ett nytt (se store.py) - annars
        # skulle t.ex. HA:s eget redigeringsläge, som skickar tillbaka hela
        # description-fältet oförändrat, gradvis duplicera blocket.
        user_text = split_description(item.description)
        assignee = existing.assignee if existing else None

        if (
            existing is not None
            and existing.recurrence is not None
            and existing.status != TodoItemStatus.COMPLETED.value
            and new_status == TodoItemStatus.COMPLETED.value
        ):
            # Återkommande uppgift avbockad: lämna den inte som klar, utan
            # rulla den vidare till nästa tillfälle - nytt förfallodatum,
            # tillbaka till "att göra", delsteg nollställda för den nya
            # omgången. Gäller oavsett var avbockningen kom ifrån (panelen,
            # röstassistenten, HA:s eget todo-kort) eftersom alla går via
            # den här metoden.
            today = dt_util.now().date()
            base = _parse_due(existing.due) or today
            if hasattr(base, "date"):
                base = base.date()
            next_due = existing.recurrence.next_date(base)
            # A subtask's own recurrence *setting* carries over to the new
            # occurrence (it's independent metadata, not tied to whether
            # the parent item happened to just roll over) - its `due` does
            # not, since that was for the occurrence that just finished;
            # a recurring subtask gets a fresh one the next time it's
            # itself checked off (see _roll_recurring_subtasks in
            # ws_api.py), a non-recurring one just has none until set again.
            reset_subtasks = [
                Subtask(id=s.id, summary=s.summary, complete=False, recurrence=s.recurrence)
                for s in existing.subtasks
            ]
            model.update(
                item.uid,
                summary=item.summary,
                status=TodoItemStatus.NEEDS_ACTION.value,
                description=combine_description(user_text, assignee, reset_subtasks),
                due=next_due.isoformat(),
                last_completed=today.isoformat(),
                subtasks=reset_subtasks,
                # Nytt tillfälle, nytt due - ska kunna påminnas om igen (se
                # reminders.py/store.py:reminder_sent).
                reminder_sent=False,
            )
        else:
            subtasks = existing.subtasks if existing else []
            # due-ändringar (även från "inget datum" till ett datum, eller
            # tvärtom) ska kunna trigga en ny påminnelse - bara reminder_sent
            # om due:t är oförändrat sedan sist.
            due_changed = existing is None or existing.due != due
            model.update(
                item.uid,
                summary=item.summary,
                status=new_status,
                description=combine_description(user_text, assignee, subtasks),
                due=due,
                reminder_sent=False if due_changed else existing.reminder_sent,
            )
        await self._store.async_save()
        self.async_write_ha_state()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        self._model().delete(uids)
        await self._store.async_save()
        self.async_write_ha_state()

    async def async_move_todo_item(self, uid: str, previous_uid: str | None = None) -> None:
        self._model().move(uid, previous_uid)
        await self._store.async_save()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        entry_data = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id)
        if entry_data is not None:
            entry_data.pop("entity", None)


def _parse_due(value: str | None):
    if not value:
        return None
    from datetime import date, datetime

    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        _LOGGER.warning("Kunde inte tolka due-värdet %r", value)
        return None

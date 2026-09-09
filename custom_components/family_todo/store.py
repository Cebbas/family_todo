"""Data model + persistence for a single Family Todo list.

Split in two on purpose: `TodoListData` is a plain-Python model with no
Home Assistant dependency, so its CRUD/ordering/subtask logic can be unit
tested without spinning up a `hass` instance. `FamilyTodoStore` is the thin
wrapper that loads/saves that model through HA's own storage (`Store`),
mirroring how cal_combiner's OwnCalendarStore separates "what the data
looks like" from "where it's persisted".

Subtasks and assignee are *not* part of the HA `todo` entity schema
(`TodoItem` only has summary/status/description/due) - they're kept here
as extension data alongside each item, uid-keyed, and are only ever read/
written by the sidepanel via the websocket API. Home Assistant's own
todo card, and voice assistants, only ever see the plain item.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import uuid

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY_PREFIX, STORAGE_VERSION


@dataclass
class Subtask:
    """A single checklist entry within a todo item."""

    id: str
    summary: str
    complete: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "summary": self.summary, "complete": self.complete}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Subtask":
        return cls(id=data["id"], summary=data["summary"], complete=bool(data.get("complete", False)))


@dataclass
class TodoItemData:
    """A todo item plus the extension fields the HA `todo` platform can't hold."""

    uid: str
    summary: str
    status: str = "needs_action"  # "needs_action" | "completed"
    description: str | None = None
    due: str | None = None  # ISO date or datetime string
    assignee: str | None = None
    subtasks: list[Subtask] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "summary": self.summary,
            "status": self.status,
            "description": self.description,
            "due": self.due,
            "assignee": self.assignee,
            "subtasks": [s.to_dict() for s in self.subtasks],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TodoItemData":
        return cls(
            uid=data["uid"],
            summary=data["summary"],
            status=data.get("status", "needs_action"),
            description=data.get("description"),
            due=data.get("due"),
            assignee=data.get("assignee"),
            subtasks=[Subtask.from_dict(s) for s in data.get("subtasks", [])],
        )

    @property
    def subtask_progress(self) -> tuple[int, int]:
        """Return (antal klara, totalt antal) delsteg."""
        if not self.subtasks:
            return (0, 0)
        done = sum(1 for s in self.subtasks if s.complete)
        return (done, len(self.subtasks))


class TodoListData:
    """In-memory model for one list: an ordered collection of items."""

    def __init__(self, items: list[TodoItemData] | None = None) -> None:
        self._items: dict[str, TodoItemData] = {i.uid: i for i in (items or [])}
        self._order: list[str] = [i.uid for i in (items or [])]

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": {uid: item.to_dict() for uid, item in self._items.items()},
            "order": list(self._order),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TodoListData":
        data = data or {}
        items_by_uid = {
            uid: TodoItemData.from_dict(item_data) for uid, item_data in data.get("items", {}).items()
        }
        order = [uid for uid in data.get("order", []) if uid in items_by_uid]
        # Om ordningslistan tappat bort en uid (t.ex. korrupt data) - visa den
        # ändå, sist, hellre än att tyst döljas.
        order += [uid for uid in items_by_uid if uid not in order]
        model = cls()
        model._items = items_by_uid
        model._order = order
        return model

    @property
    def items(self) -> list[TodoItemData]:
        """Alla items i sparad ordning."""
        return [self._items[uid] for uid in self._order]

    def get(self, uid: str) -> TodoItemData | None:
        return self._items.get(uid)

    def add(self, item: TodoItemData, *, uid: str | None = None) -> TodoItemData:
        if uid is None:
            uid = uuid.uuid4().hex
        item.uid = uid
        self._items[uid] = item
        self._order.append(uid)
        return item

    def update(self, uid: str, **changes: Any) -> TodoItemData | None:
        item = self._items.get(uid)
        if item is None:
            return None
        for key, value in changes.items():
            setattr(item, key, value)
        return item

    def delete(self, uids: list[str]) -> None:
        for uid in uids:
            self._items.pop(uid, None)
        self._order = [uid for uid in self._order if uid not in uids]

    def move(self, uid: str, previous_uid: str | None) -> None:
        if uid not in self._order:
            return
        self._order.remove(uid)
        if previous_uid is None:
            self._order.insert(0, uid)
        else:
            try:
                index = self._order.index(previous_uid)
            except ValueError:
                self._order.append(uid)
            else:
                self._order.insert(index + 1, uid)


class FamilyTodoStore:
    """Persists one list's `TodoListData` in Home Assistant's own storage."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY_PREFIX}{entry_id}")
        self._data: TodoListData | None = None

    async def async_load(self) -> TodoListData:
        if self._data is None:
            raw = await self._store.async_load()
            self._data = TodoListData.from_dict(raw)
        return self._data

    async def async_save(self) -> None:
        if self._data is not None:
            await self._store.async_save(self._data.to_dict())

    async def async_remove(self) -> None:
        await self._store.async_remove()

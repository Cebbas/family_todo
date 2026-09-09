"""Data model + persistence for a single Family Todo list.

Split in two on purpose: `TodoListData` is a plain-Python model with no
Home Assistant dependency, so its CRUD/ordering/subtask logic can be unit
tested without spinning up a `hass` instance. `FamilyTodoStore` is the thin
wrapper that loads/saves that model through HA's own storage (`Store`),
mirroring how cal_combiner's OwnCalendarStore separates "what the data
looks like" from "where it's persisted".

Subtasks, assignee and section are *not* part of the HA `todo` entity
schema (`TodoItem` only has summary/status/description/due) - they're kept
here as extension data alongside each item, uid-keyed, and are only ever
read/written by the sidepanel via the websocket API. Home Assistant's own
todo card, and voice assistants, only ever see the plain item.

Sections ("delar") group items within a list - e.g. one per room - and
may optionally point at a Home Assistant area (`area_id`, from HA's own
area registry) so the panel can show the area's name/icon instead of
asking for a name again. A section with no `area_id` is just a plain
named group (e.g. "Den här veckan"); items with no `section_id` show up
ungrouped rather than being forced into a section.

Recurrence works differently from the other extension fields: checking
off a recurring item doesn't leave it completed - todo.py intercepts that
transition and instead rolls the item forward to its next occurrence
(new `due`, status back to needs_action, subtasks reset). See
FamilyTodoListEntity.async_update_todo_item.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any
import uuid

from dateutil.relativedelta import relativedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY_PREFIX, STORAGE_VERSION

RECURRENCE_UNITS = ("days", "weeks", "months")


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
class Section:
    """A named group of items within a list, optionally tied to an HA area."""

    id: str
    name: str
    area_id: str | None = None
    icon: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "area_id": self.area_id, "icon": self.icon}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Section":
        return cls(
            id=data["id"],
            name=data["name"],
            area_id=data.get("area_id"),
            icon=data.get("icon"),
        )


@dataclass
class Recurrence:
    """How often a task repeats, e.g. "every other week" (interval=2, unit="weeks")."""

    interval: int
    unit: str  # one of RECURRENCE_UNITS

    def to_dict(self) -> dict[str, Any]:
        return {"interval": self.interval, "unit": self.unit}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Recurrence":
        return cls(interval=int(data["interval"]), unit=data.get("unit", "weeks"))

    def next_date(self, from_date: date) -> date:
        """Nästa förfallodatum räknat från `from_date` (oftast förra förfallodatumet)."""
        return from_date + relativedelta(**{self.unit: self.interval})


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
    section_id: str | None = None
    recurrence: Recurrence | None = None
    last_completed: str | None = None  # ISO date of the last time this was checked off

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "summary": self.summary,
            "status": self.status,
            "description": self.description,
            "due": self.due,
            "assignee": self.assignee,
            "subtasks": [s.to_dict() for s in self.subtasks],
            "section_id": self.section_id,
            "recurrence": self.recurrence.to_dict() if self.recurrence else None,
            "last_completed": self.last_completed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TodoItemData":
        recurrence_data = data.get("recurrence")
        return cls(
            uid=data["uid"],
            summary=data["summary"],
            status=data.get("status", "needs_action"),
            description=data.get("description"),
            due=data.get("due"),
            assignee=data.get("assignee"),
            subtasks=[Subtask.from_dict(s) for s in data.get("subtasks", [])],
            section_id=data.get("section_id"),
            recurrence=Recurrence.from_dict(recurrence_data) if recurrence_data else None,
            last_completed=data.get("last_completed"),
        )

    @property
    def subtask_progress(self) -> tuple[int, int]:
        """Return (antal klara, totalt antal) delsteg."""
        if not self.subtasks:
            return (0, 0)
        done = sum(1 for s in self.subtasks if s.complete)
        return (done, len(self.subtasks))


class TodoListData:
    """In-memory model for one list: an ordered collection of items + sections."""

    def __init__(self, items: list[TodoItemData] | None = None) -> None:
        self._items: dict[str, TodoItemData] = {i.uid: i for i in (items or [])}
        self._order: list[str] = [i.uid for i in (items or [])]
        self._sections: dict[str, Section] = {}
        self._section_order: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": {uid: item.to_dict() for uid, item in self._items.items()},
            "order": list(self._order),
            "sections": {sid: section.to_dict() for sid, section in self._sections.items()},
            "section_order": list(self._section_order),
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

        sections_by_id = {
            sid: Section.from_dict(section_data) for sid, section_data in data.get("sections", {}).items()
        }
        section_order = [sid for sid in data.get("section_order", []) if sid in sections_by_id]
        section_order += [sid for sid in sections_by_id if sid not in section_order]

        model = cls()
        model._items = items_by_uid
        model._order = order
        model._sections = sections_by_id
        model._section_order = section_order
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

    # ---- sections ----

    @property
    def sections(self) -> list[Section]:
        """Alla sektioner i sparad ordning."""
        return [self._sections[sid] for sid in self._section_order]

    def get_section(self, section_id: str) -> Section | None:
        return self._sections.get(section_id)

    def add_section(self, section: Section, *, section_id: str | None = None) -> Section:
        if section_id is None:
            section_id = uuid.uuid4().hex
        section.id = section_id
        self._sections[section_id] = section
        self._section_order.append(section_id)
        return section

    def update_section(self, section_id: str, **changes: Any) -> Section | None:
        section = self._sections.get(section_id)
        if section is None:
            return None
        for key, value in changes.items():
            setattr(section, key, value)
        return section

    def delete_section(self, section_id: str) -> None:
        """Tar bort sektionen. Dess uppgifter tas INTE bort - de blir omärkta.

        En bortagen sektion ska aldrig ta uppgifterna i den med sig - att
        radera en gruppering är inte samma sak som att radera det som låg
        i den.
        """
        self._sections.pop(section_id, None)
        self._section_order = [sid for sid in self._section_order if sid != section_id]
        for item in self._items.values():
            if item.section_id == section_id:
                item.section_id = None


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

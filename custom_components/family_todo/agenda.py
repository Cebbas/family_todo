"""Tvärs-över-listor-översikt: vilka uppgifter förfaller inom ett datumintervall.

Driver både panelens "Veckan"-flik (veckans sysslor per person) och
family-planner-card:s "Idag"-vy (dagens/försenade uppgifter under varje
person) via family_todo/agenda i ws_api.py. Ren Python, inget hass-beroende -
ws_api.py samlar ihop (lista, modell)-paren och anropar `collect_agenda`.

Bara att-göra-listor tas med - en inköpslista har inga förfallodatum eller
tilldelningar att visa per person. Delsteg med eget förfallodatum (se
store.py:Subtask) blir egna rader, tilldelade samma person som uppgiften de
hör till, eftersom det är där återkommande småsysslor ("vattna blommorna"
var 3:e dag) typiskt bor.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable

from .const import LIST_TYPE_SHOPPING
from .store import TodoListData


def _due_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _in_window(due: date | None, start: date, end: date, include_overdue: bool) -> bool:
    if due is None:
        return False
    if start <= due <= end:
        return True
    return include_overdue and due < start


def collect_agenda(
    lists: Iterable[tuple[dict[str, Any], TodoListData]],
    start: date,
    end: date,
    *,
    include_overdue: bool = True,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Alla oavklarade uppgifter/delsteg med förfallodatum i [start, end].

    `include_overdue` tar även med sådant som förföll före `start` och
    fortfarande inte är avbockat. `overdue` i varje rad räknas mot `today`
    (default `start`) - inte mot `start` - så att en senare vecka i panelen
    inte markerar allt som försenat.
    """
    today = today or start
    rows: list[dict[str, Any]] = []
    for info, model in lists:
        if info.get("list_type") == LIST_TYPE_SHOPPING:
            continue
        sections = {s.id: s.name for s in model.sections}
        base = {
            "entry_id": info["entry_id"],
            "list_name": info.get("name"),
            "list_icon": info.get("icon"),
            "list_color": info.get("color"),
        }
        for item in model.items:
            if item.status == "completed":
                continue
            section_name = sections.get(item.section_id) if item.section_id else None
            due = _due_date(item.due)
            if _in_window(due, start, end, include_overdue):
                rows.append(
                    {
                        **base,
                        "kind": "item",
                        "uid": item.uid,
                        "subtask_id": None,
                        "summary": item.summary,
                        "parent_summary": None,
                        "due": item.due,
                        "assignee": item.assignee,
                        "section_name": section_name,
                        "recurrence": item.recurrence.to_dict() if item.recurrence else None,
                        "overdue": due < today,
                    }
                )
            for sub in item.subtasks:
                if sub.complete:
                    continue
                sub_due = _due_date(sub.due)
                if not _in_window(sub_due, start, end, include_overdue):
                    continue
                rows.append(
                    {
                        **base,
                        "kind": "subtask",
                        "uid": item.uid,
                        "subtask_id": sub.id,
                        "summary": sub.summary,
                        "parent_summary": item.summary,
                        "due": sub.due,
                        "assignee": item.assignee,
                        "section_name": section_name,
                        "recurrence": sub.recurrence.to_dict() if sub.recurrence else None,
                        "overdue": sub_due < today,
                    }
                )
    rows.sort(key=lambda r: (r["due"] or "", (r["summary"] or "").lower()))
    return rows

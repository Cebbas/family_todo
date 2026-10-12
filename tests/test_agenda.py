"""Tests for agenda.collect_agenda (pure Python, no hass)."""
from datetime import date

from custom_components.family_todo.agenda import collect_agenda
from custom_components.family_todo.store import Recurrence, Section, Subtask, TodoItemData, TodoListData

_INFO = {"entry_id": "e1", "name": "Sysslor", "list_type": "tasks"}
_MON = date(2026, 10, 12)
_SUN = date(2026, 10, 18)


def _model(*items):
    model = TodoListData()
    for item in items:
        model.add(item, uid=item.uid)
    return model


def test_includes_items_due_in_window_and_overdue():
    model = _model(
        TodoItemData(uid="a", summary="I veckan", due="2026-10-14", assignee="Naomi"),
        TodoItemData(uid="b", summary="Försenad", due="2026-10-01"),
        TodoItemData(uid="c", summary="Nästa vecka", due="2026-10-20"),
        TodoItemData(uid="d", summary="Utan datum"),
        TodoItemData(uid="e", summary="Klar", due="2026-10-13", status="completed"),
    )
    rows = collect_agenda([(_INFO, model)], _MON, _SUN)
    assert [r["summary"] for r in rows] == ["Försenad", "I veckan"]
    assert rows[0]["overdue"] is True
    assert rows[1]["overdue"] is False
    assert rows[1]["assignee"] == "Naomi"
    assert rows[1]["list_name"] == "Sysslor"


def test_overdue_can_be_excluded():
    model = _model(TodoItemData(uid="b", summary="Försenad", due="2026-10-01"))
    assert collect_agenda([(_INFO, model)], _MON, _SUN, include_overdue=False) == []


def test_datetime_due_is_compared_by_date():
    model = _model(TodoItemData(uid="a", summary="Med tid", due="2026-10-18T19:00:00"))
    assert len(collect_agenda([(_INFO, model)], _MON, _SUN)) == 1


def test_subtasks_with_own_due_become_rows_with_parent_assignee():
    model = _model(
        TodoItemData(
            uid="a",
            summary="Växter",
            assignee="Nadine",
            subtasks=[
                Subtask(id="s1", summary="Vattna", due="2026-10-15", recurrence=Recurrence(3, "days")),
                Subtask(id="s2", summary="Klar redan", due="2026-10-15", complete=True),
                Subtask(id="s3", summary="Utan datum"),
            ],
        )
    )
    rows = collect_agenda([(_INFO, model)], _MON, _SUN)
    assert len(rows) == 1
    assert rows[0]["kind"] == "subtask"
    assert rows[0]["subtask_id"] == "s1"
    assert rows[0]["parent_summary"] == "Växter"
    assert rows[0]["assignee"] == "Nadine"


def test_shopping_lists_are_skipped():
    model = _model(TodoItemData(uid="a", summary="Mjölk", due="2026-10-14"))
    assert collect_agenda([({**_INFO, "list_type": "shopping"}, model)], _MON, _SUN) == []


def test_overdue_is_relative_to_today_not_window_start():
    model = _model(TodoItemData(uid="a", summary="Ons", due="2026-10-21"))
    rows = collect_agenda(
        [(_INFO, model)], date(2026, 10, 19), date(2026, 10, 25), today=date(2026, 10, 12)
    )
    assert rows[0]["overdue"] is False


def test_section_name_included():
    model = _model(TodoItemData(uid="a", summary="Dammsug", due="2026-10-14", section_id="k"))
    model.add_section(Section(id="", name="Kök"), section_id="k")
    assert collect_agenda([(_INFO, model)], _MON, _SUN)[0]["section_name"] == "Kök"

"""Unit tests for the pure-Python list model in store.py.

No `hass` needed - TodoListData/TodoItemData/Subtask have no Home
Assistant dependency, only FamilyTodoStore (the persistence wrapper,
untested here) does.
"""
from custom_components.family_todo.store import Subtask, TodoItemData, TodoListData


def _item(uid="a", summary="Handla mjölk", **kwargs):
    return TodoItemData(uid=uid, summary=summary, **kwargs)


# ---- add / get / items ordering ----

def test_add_generates_uid_when_missing():
    model = TodoListData()
    item = model.add(_item(uid=""))
    assert item.uid
    assert model.get(item.uid) is item


def test_items_preserves_insertion_order():
    model = TodoListData()
    model.add(_item(uid="", summary="Först"))
    model.add(_item(uid="", summary="Sedan"))
    assert [i.summary for i in model.items] == ["Först", "Sedan"]


# ---- update ----

def test_update_changes_fields_and_preserves_extension_data():
    model = TodoListData()
    item = model.add(_item(uid="", assignee="Anna", subtasks=[Subtask("s1", "Köp mjölk")]))
    model.update(item.uid, summary="Handla", status="completed")
    updated = model.get(item.uid)
    assert updated.summary == "Handla"
    assert updated.status == "completed"
    # update() bara ändrar de fält som skickas in - assignee/subtasks orörda
    assert updated.assignee == "Anna"
    assert updated.subtasks[0].summary == "Köp mjölk"


def test_update_unknown_uid_returns_none():
    model = TodoListData()
    assert model.update("missing", summary="x") is None


# ---- delete ----

def test_delete_removes_item_and_order_entry():
    model = TodoListData()
    item = model.add(_item(uid=""))
    model.delete([item.uid])
    assert model.get(item.uid) is None
    assert model.items == []


# ---- move ----

def test_move_to_start():
    model = TodoListData()
    a = model.add(_item(uid="", summary="a"))
    b = model.add(_item(uid="", summary="b"))
    model.move(b.uid, None)
    assert [i.uid for i in model.items] == [b.uid, a.uid]


def test_move_after_previous_uid():
    model = TodoListData()
    a = model.add(_item(uid="", summary="a"))
    b = model.add(_item(uid="", summary="b"))
    c = model.add(_item(uid="", summary="c"))
    model.move(c.uid, a.uid)
    assert [i.uid for i in model.items] == [a.uid, c.uid, b.uid]


def test_move_unknown_uid_is_noop():
    model = TodoListData()
    a = model.add(_item(uid="", summary="a"))
    model.move("missing", None)
    assert [i.uid for i in model.items] == [a.uid]


# ---- subtask progress ----

def test_subtask_progress_no_subtasks():
    item = _item(subtasks=[])
    assert item.subtask_progress == (0, 0)


def test_subtask_progress_counts_complete():
    item = _item(subtasks=[Subtask("1", "a", True), Subtask("2", "b", False), Subtask("3", "c", True)])
    assert item.subtask_progress == (2, 3)


# ---- serialization round-trip ----

def test_to_dict_from_dict_round_trip():
    model = TodoListData()
    model.add(
        _item(
            uid="",
            summary="Städa rummet",
            description="Innan helgen",
            due="2026-09-20",
            assignee="Liam",
            subtasks=[Subtask("s1", "Dammsug", True), Subtask("s2", "Vädra", False)],
        )
    )
    restored = TodoListData.from_dict(model.to_dict())
    assert len(restored.items) == 1
    item = restored.items[0]
    assert item.summary == "Städa rummet"
    assert item.assignee == "Liam"
    assert item.subtask_progress == (1, 2)


def test_from_dict_handles_missing_order_entries():
    # En uid i "items" som saknas i "order" (t.ex. korrupt/gammal data)
    # ska ändå synas, hellre än att tyst försvinna.
    raw = {
        "items": {"x": {"uid": "x", "summary": "Spöke"}},
        "order": [],
    }
    model = TodoListData.from_dict(raw)
    assert [i.uid for i in model.items] == ["x"]


def test_from_dict_none_returns_empty_model():
    model = TodoListData.from_dict(None)
    assert model.items == []

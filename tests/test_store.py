"""Unit tests for the pure-Python list model in store.py.

No `hass` needed - TodoListData/TodoItemData/Subtask have no Home
Assistant dependency, only FamilyTodoStore (the persistence wrapper,
untested here) does.
"""
from datetime import date

from custom_components.family_todo.store import (
    Recurrence,
    Section,
    Subtask,
    TodoItemData,
    TodoListData,
    combine_description,
    split_description,
)


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


# ---- sections ----

def test_add_section_generates_id_when_missing():
    model = TodoListData()
    section = model.add_section(Section(id="", name="Kök", area_id="area.kok"))
    assert section.id
    assert model.get_section(section.id) is section


def test_sections_preserves_insertion_order():
    model = TodoListData()
    model.add_section(Section(id="", name="Kök"))
    model.add_section(Section(id="", name="Badrum"))
    assert [s.name for s in model.sections] == ["Kök", "Badrum"]


def test_update_section_changes_fields():
    model = TodoListData()
    section = model.add_section(Section(id="", name="Kök"))
    model.update_section(section.id, name="Köket", area_id="area.kok")
    updated = model.get_section(section.id)
    assert updated.name == "Köket"
    assert updated.area_id == "area.kok"


def test_delete_section_unlinks_items_instead_of_deleting_them():
    model = TodoListData()
    section = model.add_section(Section(id="", name="Kök"))
    item = model.add(_item(uid="", section_id=None))
    model.update(item.uid, section_id=section.id)

    model.delete_section(section.id)

    assert model.get_section(section.id) is None
    assert model.get(item.uid) is not None
    assert model.get(item.uid).section_id is None


def test_section_round_trip_through_dict():
    model = TodoListData()
    model.add_section(Section(id="", name="Kök", area_id="area.kok", icon="mdi:chef-hat"))
    model.add(_item(uid="", section_id=model.sections[0].id))

    restored = TodoListData.from_dict(model.to_dict())

    assert [s.name for s in restored.sections] == ["Kök"]
    assert restored.sections[0].area_id == "area.kok"
    assert restored.items[0].section_id == restored.sections[0].id


# ---- recurrence ----

def test_recurrence_next_date_weeks():
    recurrence = Recurrence(interval=2, unit="weeks")
    assert recurrence.next_date(date(2026, 9, 9)) == date(2026, 9, 23)


def test_recurrence_next_date_days():
    recurrence = Recurrence(interval=3, unit="days")
    assert recurrence.next_date(date(2026, 9, 9)) == date(2026, 9, 12)


def test_recurrence_next_date_months_clamps_short_month():
    # 31 jan + 1 månad ska landa i februari, inte "31:e februari"
    recurrence = Recurrence(interval=1, unit="months")
    assert recurrence.next_date(date(2026, 1, 31)) == date(2026, 2, 28)


def test_recurrence_round_trip_through_dict():
    model = TodoListData()
    model.add(_item(uid="", recurrence=Recurrence(interval=2, unit="weeks")))
    restored = TodoListData.from_dict(model.to_dict())
    assert restored.items[0].recurrence == Recurrence(interval=2, unit="weeks")


def test_item_without_recurrence_round_trips_to_none():
    model = TodoListData()
    model.add(_item(uid=""))
    restored = TodoListData.from_dict(model.to_dict())
    assert restored.items[0].recurrence is None


# ---- description meta block (assignee/delsteg synligt utanför panelen) ----

def test_combine_description_appends_assignee():
    result = combine_description("Handla mjölk och bröd", "Anna", [])
    assert result == "Handla mjölk och bröd\n\n⸻ Family Todo ⸻\n👤 Anna"


def test_combine_description_appends_subtask_progress():
    subtasks = [Subtask("s1", "Mjölk", complete=True), Subtask("s2", "Bröd", complete=False)]
    result = combine_description("", None, subtasks)
    assert result == "⸻ Family Todo ⸻\n☑️ 1/2 delsteg klara"


def test_combine_description_with_assignee_and_subtasks():
    subtasks = [Subtask("s1", "Mjölk", complete=True)]
    result = combine_description(None, "Anna", subtasks)
    assert result == "⸻ Family Todo ⸻\n👤 Anna\n☑️ 1/1 delsteg klara"


def test_combine_description_without_assignee_or_subtasks_returns_plain_text():
    assert combine_description("Bara en vanlig text", None, []) == "Bara en vanlig text"


def test_combine_description_with_nothing_at_all_returns_none():
    assert combine_description("", None, []) is None
    assert combine_description(None, None, []) is None


def test_split_description_removes_meta_block():
    full = combine_description("Handla mjölk", "Anna", [Subtask("s1", "x", complete=False)])
    assert split_description(full) == "Handla mjölk"


def test_split_description_without_meta_block_returns_text_unchanged():
    assert split_description("Bara en vanlig text") == "Bara en vanlig text"


def test_split_description_handles_none():
    assert split_description(None) == ""


def test_combine_then_split_round_trips_and_never_duplicates_on_repeated_calls():
    # Simulerar att panelen/HA:s eget redigeringsläge skickar tillbaka
    # samma description flera gånger i rad - blocket ska ersättas, aldrig
    # staplas på sig självt.
    description = combine_description("Städa", "Anna", [Subtask("s1", "x", complete=False)])
    for _ in range(3):
        description = combine_description(split_description(description), "Anna", [Subtask("s1", "x", complete=True)])
    assert description.count("⸻ Family Todo ⸻") == 1
    assert description == "Städa\n\n⸻ Family Todo ⸻\n👤 Anna\n☑️ 1/1 delsteg klara"

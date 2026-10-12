"""Tests for the shopping-list keyword categorisation in categories.py (pure Python)."""
from custom_components.family_todo.categories import (
    PRESET_CATEGORIES,
    guess_category,
    guess_section_id,
    section_category,
)
from custom_components.family_todo.store import Section


def test_guess_exact_word():
    assert guess_category("Mjölk") == "dairy"
    assert guess_category("Bananer") == "produce"


def test_guess_compound_word_by_suffix():
    assert guess_category("Lättmjölk") == "dairy"
    assert guess_category("Vetemjöl") == "pantry"


def test_guess_ignores_quantity_and_extra_words():
    assert guess_category("2 paket köttfärs") == "meat"


def test_short_keyword_does_not_match_inside_other_words():
    # "te" (Skafferi) får inte matcha slutet av "tomate" e.d.
    assert guess_category("Choklad") == "pantry"
    assert guess_category("Gurkmeja-te") == "pantry"
    assert guess_category("Kotte") is None


def test_guess_returns_none_for_unknown():
    assert guess_category("Present till mormor") is None


def test_guess_restricted_to_available_keys():
    assert guess_category("Mjölk", ["produce"]) is None


def test_section_category_from_explicit_key_or_matching_name():
    assert section_category(Section(id="1", name="Whatever", category="dairy")) == "dairy"
    assert section_category(Section(id="2", name="mejeri")) == "dairy"
    assert section_category(Section(id="3", name="Kök")) is None


def test_guess_section_id_picks_matching_section():
    sections = [
        Section(id="s-produce", name="Frukt & grönt", category="produce"),
        Section(id="s-dairy", name="Mejeri", category="dairy"),
    ]
    assert guess_section_id("Yoghurt", sections) == "s-dairy"
    assert guess_section_id("Köttfärs", sections) is None  # ingen Kött-sektion i listan


def test_preset_keys_are_unique():
    keys = [c["key"] for c in PRESET_CATEGORIES]
    assert len(keys) == len(set(keys))

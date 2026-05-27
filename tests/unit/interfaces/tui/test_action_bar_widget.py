"""format_action_bar — чистая функция формата ability-полосы."""

from __future__ import annotations

from dnd.application.abilities.ability import AbilityId
from dnd.application.abilities.defaults import register_default_abilities
from dnd.application.abilities.registry import AbilityRegistry
from dnd.interfaces.tui.widgets.action_bar_widget import format_action_bar


def _registry() -> AbilityRegistry:
    r = AbilityRegistry()
    register_default_abilities(r)
    return r


def test_format_bar_from_keymap() -> None:
    r = _registry()
    keymap = {
        "a": r.get(AbilityId("weapon_attack")),
        "d": r.get(AbilityId("dodge")),
    }
    bar = format_action_bar(keymap)
    assert "[a] Attack" in bar
    assert "[d] Dodge" in bar


def test_format_bar_empty() -> None:
    assert format_action_bar({}) == ""


def test_format_bar_sorted_by_key() -> None:
    r = _registry()
    keymap = {
        "z": r.get(AbilityId("dodge")),
        "a": r.get(AbilityId("weapon_attack")),
    }
    bar = format_action_bar(keymap)
    assert bar.index("[a]") < bar.index("[z]")


def test_format_bar_separator_two_spaces() -> None:
    """Между записями — двойной пробел; шире, чем имя ability, поэтому
    визуально воспринимается как разделитель колонок, а не пробел внутри
    имени (например, 'Eldritch Blast')."""
    r = _registry()
    keymap = {
        "a": r.get(AbilityId("weapon_attack")),
        "d": r.get(AbilityId("dodge")),
    }
    assert "  " in format_action_bar(keymap)

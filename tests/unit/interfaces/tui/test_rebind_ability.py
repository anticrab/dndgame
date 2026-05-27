"""rebind_ability / ability_can_afford — хелперы меню способностей (этап S)."""
from __future__ import annotations

from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ability_id import AbilityId
from dnd.domain.values.ids import CreatureId
from dnd.interfaces.tui.screens.keymap import rebind_ability


def _actor() -> Creature:
    return Creature.create(
        id_=CreatureId("hero"),
        name="hero",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10,
        armor_class=10,
        speed_ft=30,
    )


def test_rebind_sets_keybinding() -> None:
    actor = _actor()
    rebind_ability(actor, "z", AbilityId("weapon_attack"))
    assert actor.keybindings["z"] == AbilityId("weapon_attack")


def test_rebind_clears_previous_key_of_same_ability() -> None:
    """Одна способность не должна висеть на двух клавишах."""
    actor = _actor()
    actor.keybindings["z"] = AbilityId("weapon_attack")
    rebind_ability(actor, "x", AbilityId("weapon_attack"))
    assert "z" not in actor.keybindings
    assert actor.keybindings["x"] == AbilityId("weapon_attack")


def test_rebind_overwrites_other_ability_on_that_key() -> None:
    """Одна клавиша = одна способность: новый бинд вытесняет старую."""
    actor = _actor()
    actor.keybindings["z"] = AbilityId("dodge")
    rebind_ability(actor, "z", AbilityId("weapon_attack"))
    assert actor.keybindings["z"] == AbilityId("weapon_attack")

"""Creature.ability_ids + Creature.keybindings — поля L2-T4."""
from __future__ import annotations

from dnd.application.dto.ids import CreatureId
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ability_id import AbilityId
from dnd.domain.values.weapon import LONGSWORD


def _make() -> Creature:
    return Creature.create(
        id_=CreatureId("x"), name="X",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10, armor_class=10, speed_ft=30, equipped_weapon=LONGSWORD,
    )


def test_default_abilities_includes_attack() -> None:
    c = _make()
    assert AbilityId("weapon_attack") in c.ability_ids


def test_default_abilities_six_basic() -> None:
    """6 базовых — синхронизировано с register_default_abilities (L2-3)."""
    c = _make()
    assert set(c.ability_ids) == {
        AbilityId("weapon_attack"),
        AbilityId("dodge"),
        AbilityId("dash"),
        AbilityId("disengage"),
        AbilityId("interact"),
        AbilityId("break_object"),
    }


def test_default_keybindings_empty() -> None:
    c = _make()
    assert c.keybindings == {}


def test_custom_keybinding_override() -> None:
    """Mutable dict: пользователь может переназначить hotkey."""
    c = _make()
    c.keybindings["z"] = AbilityId("weapon_attack")
    assert c.keybindings == {"z": AbilityId("weapon_attack")}


def test_each_creature_has_own_keybindings_dict() -> None:
    """default_factory=dict гарантирует, что dict не шарится между instance'ами."""
    c1 = _make()
    c2 = _make()
    c1.keybindings["z"] = AbilityId("weapon_attack")
    assert c2.keybindings == {}

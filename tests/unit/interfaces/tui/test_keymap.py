"""build_keymap — {hotkey: Ability} с учётом override'ов keybindings."""

from __future__ import annotations

from dnd.application.abilities.defaults import register_default_abilities
from dnd.application.abilities.registry import AbilityRegistry
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ability_id import AbilityId
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.weapon import LONGSWORD
from dnd.interfaces.tui.screens.keymap import build_keymap


def _make(keybindings: dict[str, AbilityId] | None = None) -> Creature:
    c = Creature.create(
        id_=CreatureId("x"),
        name="X",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10,
        armor_class=10,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )
    if keybindings:
        c.keybindings.update(keybindings)
    return c


def _reg() -> AbilityRegistry:
    r = AbilityRegistry()
    register_default_abilities(r)
    return r


def test_default_hotkey_a_maps_to_attack() -> None:
    km = build_keymap(_make(), _reg())
    assert km["a"].id == AbilityId("weapon_attack")


def test_override_z_replaces_default_a() -> None:
    """После override 'z'→weapon_attack ключ 'a' свободен."""
    km = build_keymap(_make({"z": AbilityId("weapon_attack")}), _reg())
    assert km["z"].id == AbilityId("weapon_attack")
    assert "a" not in km


def test_override_replaces_only_specified() -> None:
    """Override одного hotkey'я не трогает default'ы остальных."""
    km = build_keymap(_make({"z": AbilityId("weapon_attack")}), _reg())
    assert km["d"].id == AbilityId("dodge")
    assert km["h"].id == AbilityId("dash")


def test_all_six_defaults_mapped() -> None:
    km = build_keymap(_make(), _reg())
    assert {ab.id for ab in km.values()} == {
        AbilityId("weapon_attack"),
        AbilityId("dodge"),
        AbilityId("dash"),
        AbilityId("disengage"),
        AbilityId("interact"),
        AbilityId("break_object"),
    }

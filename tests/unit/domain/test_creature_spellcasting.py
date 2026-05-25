"""P1-3: Creature spellcasting-поля + деривации (attack/DC/слоты)."""
from __future__ import annotations

import pytest

from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.ids import SpellId


def _caster(*, int_: int = 16, prof: int = 2) -> Creature:
    c = Creature.create(
        id_="mage", name="Mage",
        abilities=AbilityScores.of(str_=8, dex=12, con=12, int_=int_, wis=10, cha=10),
        max_hp=8, armor_class=12, speed_ft=30, proficiency_bonus=prof,
    )
    c.spellcasting_ability = Ability.INT
    c.spell_slots = {1: 2}
    c.known_spells = (SpellId("fire_bolt"), SpellId("magic_missile"))
    return c


def test_defaults_non_caster() -> None:
    c = Creature.create(
        id_="grunt", name="Grunt",
        abilities=AbilityScores.of(str_=12, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=10, armor_class=12, speed_ft=30,
    )
    assert c.spellcasting_ability is None
    assert c.spell_slots == {}
    assert c.known_spells == ()


def test_spell_attack_and_dc() -> None:
    c = _caster(int_=16, prof=2)  # INT mod +3, prof +2
    assert c.spell_attack_bonus() == 5      # 2 + 3
    assert c.spell_save_dc() == 13          # 8 + 2 + 3


def test_non_caster_derivation_raises() -> None:
    c = Creature.create(
        id_="grunt", name="Grunt",
        abilities=AbilityScores.of(str_=12, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=10, armor_class=12, speed_ft=30,
    )
    with pytest.raises(ValueError):
        c.spell_attack_bonus()
    with pytest.raises(ValueError):
        c.spell_save_dc()


def test_slots_consume_and_exhaust() -> None:
    c = _caster()
    assert c.has_spell_slot(1)
    c.consume_spell_slot(1)
    c.consume_spell_slot(1)
    assert not c.has_spell_slot(1)
    with pytest.raises(ValueError):
        c.consume_spell_slot(1)


def test_cantrip_unlimited() -> None:
    c = _caster()
    assert c.has_spell_slot(0)       # level 0 — всегда True
    c.consume_spell_slot(0)          # no-op
    assert c.has_spell_slot(0)

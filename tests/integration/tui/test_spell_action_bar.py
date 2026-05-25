"""P1-10: spell_ability + полоса заклинаний в action-bar."""
from __future__ import annotations

from dnd.application.abilities.spell_abilities import (
    is_spell_ability,
    spell_ability,
)
from dnd.application.dto.ids import SpellId
from dnd.application.dto.player_intent import CastSpellIntent
from dnd.domain.values.ability import Ability
from dnd.domain.values.damage import DamageType
from dnd.domain.values.spell import Spell, SpellEffect, TargetingSpec, TargetKind


def _fire_bolt() -> Spell:
    return Spell(
        id=SpellId("fire_bolt"), name="Fire Bolt", level=0, school="evocation",
        effect=SpellEffect.ATTACK, targeting=TargetingSpec(kind=TargetKind.SINGLE),
        range_ft=120, description="", dice="1d10", damage_type=DamageType.FIRE,
    )


def test_spell_ability_builds_cast_intent() -> None:
    ab = spell_ability(_fire_bolt(), "1")
    assert ab.default_hotkey == "1"
    assert ab.name == "Fire Bolt"
    assert ab.requires_target is True
    assert is_spell_ability(ab)
    intent = ab.intent_factory(target_id="gob")
    assert isinstance(intent, CastSpellIntent)
    assert intent.spell_id == SpellId("fire_bolt")
    assert intent.target_id == "gob"


def test_base_ability_is_not_spell_ability() -> None:
    base = Ability  # noqa: F841 — sanity import
    from dnd.application.abilities.ability import Ability as Ab
    from dnd.application.dto.action import ActionEconomyCost
    from dnd.domain.values.ability_id import AbilityId
    a = Ab(
        id=AbilityId("weapon_attack"), name="Attack", icon="A", default_hotkey="a",
        economy_cost=ActionEconomyCost.ACTION, requires_target=True,
        requires_path=False, intent_factory=lambda target_id=None: CastSpellIntent(
            spell_id=SpellId("x"), target_id=None),
    )
    assert not is_spell_ability(a)

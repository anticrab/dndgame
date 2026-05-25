"""P1-1: Spell value-объект + enums + валидация."""
from __future__ import annotations

import pytest

from dnd.domain.values.ability import Ability
from dnd.domain.values.damage import DamageType
from dnd.domain.values.ids import SpellId
from dnd.domain.values.spell import (
    AreaShape,
    OriginMode,
    Spell,
    SpellEffect,
    TargetingSpec,
    TargetKind,
)


def _attack_spell() -> Spell:
    return Spell(
        id=SpellId("fire_bolt"), name="Fire Bolt", level=0, school="evocation",
        effect=SpellEffect.ATTACK,
        targeting=TargetingSpec(kind=TargetKind.SINGLE),
        range_ft=120, description="Огненная стрела.",
        dice="1d10", damage_type=DamageType.FIRE,
    )


def test_valid_attack_spell() -> None:
    s = _attack_spell()
    assert s.effect is SpellEffect.ATTACK
    assert s.level == 0
    assert s.targeting.kind is TargetKind.SINGLE


def test_valid_save_spell() -> None:
    s = Spell(
        id=SpellId("sacred_flame"), name="Sacred Flame", level=0, school="evocation",
        effect=SpellEffect.SAVE, targeting=TargetingSpec(kind=TargetKind.SINGLE),
        range_ft=60, description="Пламя.", dice="1d8", damage_type=DamageType.RADIANT,
        save_ability=Ability.DEX, save_for_half=False,
    )
    assert s.save_ability is Ability.DEX


def test_valid_heal_spell() -> None:
    s = Spell(
        id=SpellId("cure_wounds"), name="Cure Wounds", level=1, school="abjuration",
        effect=SpellEffect.HEAL, targeting=TargetingSpec(kind=TargetKind.SINGLE),
        range_ft=5, description="Лечение.", heal_dice="1d8",
    )
    assert s.heal_dice == "1d8"


def test_valid_buff_spell() -> None:
    s = Spell(
        id=SpellId("shield_of_faith"), name="Shield of Faith", level=1,
        school="abjuration", effect=SpellEffect.BUFF,
        targeting=TargetingSpec(kind=TargetKind.SINGLE), range_ft=60,
        description="+2 КД.", ac_bonus=2, concentration=True,
    )
    assert s.ac_bonus == 2 and s.concentration is True


def test_negative_level_rejected() -> None:
    with pytest.raises(ValueError):
        Spell(
            id=SpellId("x"), name="X", level=-1, school="e",
            effect=SpellEffect.AUTO, targeting=TargetingSpec(kind=TargetKind.SINGLE),
            range_ft=10, description="", dice="1d4", damage_type=DamageType.FORCE,
        )


def test_attack_without_dice_rejected() -> None:
    with pytest.raises(ValueError):
        Spell(
            id=SpellId("x"), name="X", level=0, school="e",
            effect=SpellEffect.ATTACK, targeting=TargetingSpec(kind=TargetKind.SINGLE),
            range_ft=10, description="",
        )


def test_save_without_save_ability_rejected() -> None:
    with pytest.raises(ValueError):
        Spell(
            id=SpellId("x"), name="X", level=0, school="e",
            effect=SpellEffect.SAVE, targeting=TargetingSpec(kind=TargetKind.SINGLE),
            range_ft=10, description="", dice="1d8", damage_type=DamageType.RADIANT,
        )


def test_heal_without_heal_dice_rejected() -> None:
    with pytest.raises(ValueError):
        Spell(
            id=SpellId("x"), name="X", level=1, school="e",
            effect=SpellEffect.HEAL, targeting=TargetingSpec(kind=TargetKind.SINGLE),
            range_ft=5, description="",
        )


def test_buff_without_effect_rejected() -> None:
    with pytest.raises(ValueError):
        Spell(
            id=SpellId("x"), name="X", level=1, school="e",
            effect=SpellEffect.BUFF, targeting=TargetingSpec(kind=TargetKind.SINGLE),
            range_ft=60, description="",
        )


# --- P2-1: AoE TargetingSpec ---------------------------------------------

def test_area_circle_at_point_valid() -> None:
    ts = TargetingSpec(
        kind=TargetKind.AREA, origin=OriginMode.AT_POINT,
        shape=AreaShape.CIRCLE, radius_ft=10,
    )
    assert ts.shape is AreaShape.CIRCLE
    assert ts.origin is OriginMode.AT_POINT


def test_area_cone_from_caster_valid() -> None:
    ts = TargetingSpec(
        kind=TargetKind.AREA, origin=OriginMode.FROM_CASTER,
        shape=AreaShape.CONE, length_ft=15,
    )
    assert ts.shape is AreaShape.CONE


def test_area_line_valid() -> None:
    ts = TargetingSpec(
        kind=TargetKind.AREA, origin=OriginMode.FROM_CASTER,
        shape=AreaShape.LINE, length_ft=30,
    )
    assert ts.shape is AreaShape.LINE


def test_area_without_shape_rejected() -> None:
    with pytest.raises(ValueError):
        TargetingSpec(kind=TargetKind.AREA)


def test_circle_without_radius_rejected() -> None:
    with pytest.raises(ValueError):
        TargetingSpec(kind=TargetKind.AREA, shape=AreaShape.CIRCLE)


def test_cone_without_length_rejected() -> None:
    with pytest.raises(ValueError):
        TargetingSpec(kind=TargetKind.AREA, shape=AreaShape.CONE)

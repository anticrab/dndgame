"""CONTROL-заклинания (T2): валидация полей Spell."""
from __future__ import annotations

import pytest

from dnd.domain.conditions.builtin import PARALYZED, UNCONSCIOUS
from dnd.domain.values.ability import Ability
from dnd.domain.values.ids import SpellId
from dnd.domain.values.spell import (
    Spell,
    SpellEffect,
    TargetingSpec,
    TargetKind,
)


def _control(**over: object) -> Spell:
    base: dict[str, object] = dict(
        id=SpellId("x"), name="X", level=1, school="enchantment",
        effect=SpellEffect.CONTROL,
        targeting=TargetingSpec(kind=TargetKind.SINGLE),
        range_ft=60, description="",
        condition=PARALYZED, save_ability=Ability.WIS,
    )
    base.update(over)
    return Spell(**base)  # type: ignore[arg-type]


def test_control_with_save_ok() -> None:
    sp = _control()
    assert sp.effect is SpellEffect.CONTROL
    assert sp.condition == PARALYZED


def test_control_with_pool_ok() -> None:
    sp = _control(save_ability=None, hp_pool_dice="5d8", condition=UNCONSCIOUS)
    assert sp.hp_pool_dice == "5d8"


def test_control_requires_condition() -> None:
    with pytest.raises(ValueError, match="condition"):
        _control(condition=None)


def test_control_requires_exactly_one_gate() -> None:
    # ни пула, ни save
    with pytest.raises(ValueError, match=r"hp_pool_dice|save_ability"):
        _control(save_ability=None, hp_pool_dice=None)
    # и пул, и save одновременно
    with pytest.raises(ValueError, match=r"hp_pool_dice|save_ability"):
        _control(hp_pool_dice="5d8")


def test_repeat_save_requires_save_ability() -> None:
    with pytest.raises(ValueError, match="condition_repeat_save"):
        _control(save_ability=None, hp_pool_dice="5d8",
                 condition=UNCONSCIOUS, condition_repeat_save=True)

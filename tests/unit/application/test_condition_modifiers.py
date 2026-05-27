"""ConditionService.collect_modifiers — self-модификаторы активных состояний (T3)."""
from __future__ import annotations

from dnd.application.engine.condition_service import ConditionService
from dnd.domain.conditions.builtin import POISONED, register_default_conditions
from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.modifiers import DisadvantageEffect, ModifierTargetKind


def _svc() -> ConditionService:
    reg = ConditionRegistry()
    register_default_conditions(reg)
    return ConditionService(reg)


def _creature() -> Creature:
    return Creature.create(
        id_=CreatureId("c"), name="c",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10, armor_class=10, speed_ft=30,
    )


def test_poisoned_gives_attack_disadvantage_modifier() -> None:
    svc = _svc()
    c = _creature()
    c.apply_condition(POISONED)
    mods = svc.collect_modifiers(c, ModifierTargetKind.ATTACK_ROLL)
    assert len(mods) == 1
    assert isinstance(mods[0].effect, DisadvantageEffect)


def test_no_conditions_no_modifiers() -> None:
    svc = _svc()
    assert svc.collect_modifiers(_creature(), ModifierTargetKind.ATTACK_ROLL) == []

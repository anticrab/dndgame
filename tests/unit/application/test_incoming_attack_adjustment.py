"""ConditionService.incoming_attack_adjustment — cross-creature adv/disadv (T3)."""
from __future__ import annotations

from dnd.application.engine.condition_service import ConditionService
from dnd.domain.conditions.builtin import PARALYZED, PRONE, register_default_conditions
from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.attack_kind import AttackKind
from dnd.domain.values.ids import CreatureId


def _svc() -> ConditionService:
    reg = ConditionRegistry()
    register_default_conditions(reg)
    return ConditionService(reg)


def _c() -> Creature:
    return Creature.create(
        id_=CreatureId("t"), name="t",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10, armor_class=10, speed_ft=30,
    )


def test_paralyzed_grants_advantage_any_kind() -> None:
    t = _c()
    t.apply_condition(PARALYZED)
    assert _svc().incoming_attack_adjustment(
        t, distance_ft=30, attack_kind=AttackKind.RANGED
    ) == (True, False)


def test_prone_melee_point_blank_advantage() -> None:
    t = _c()
    t.apply_condition(PRONE)
    assert _svc().incoming_attack_adjustment(
        t, distance_ft=5, attack_kind=AttackKind.MELEE
    ) == (True, False)


def test_prone_ranged_disadvantage() -> None:
    t = _c()
    t.apply_condition(PRONE)
    assert _svc().incoming_attack_adjustment(
        t, distance_ft=30, attack_kind=AttackKind.RANGED
    ) == (False, True)


def test_no_condition_no_adjustment() -> None:
    assert _svc().incoming_attack_adjustment(
        _c(), distance_ft=5, attack_kind=AttackKind.MELEE
    ) == (False, False)

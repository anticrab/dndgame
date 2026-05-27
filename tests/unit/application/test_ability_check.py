"""Проверки характеристик и навыков (V)."""

from __future__ import annotations

from dnd.application.engine.ability_check import (
    ability_check_bonus,
    passive_score,
    skill_bonus,
)
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.skill import Skill


def _c() -> Creature:
    return Creature.create(
        id_=CreatureId("c"),
        name="c",
        abilities=AbilityScores.of(str_=16, dex=14, con=12, int_=10, wis=10, cha=8),
        max_hp=10,
        armor_class=12,
        speed_ft=30,
        proficiency_bonus=2,
    )


def test_skill_bonus_plain_is_ability_mod() -> None:
    # Атлетика (STR 16 → +3), без владения = только модификатор.
    assert skill_bonus(_c(), Skill.ATHLETICS) == 3


def test_skill_bonus_proficient_adds_prof() -> None:
    c = _c()
    c.skill_proficiencies = frozenset({Skill.ATHLETICS})
    assert skill_bonus(c, Skill.ATHLETICS) == 3 + 2  # +prof


def test_skill_bonus_expertise_doubles_prof() -> None:
    c = _c()
    c.skill_proficiencies = frozenset({Skill.ATHLETICS})
    c.skill_expertise = frozenset({Skill.ATHLETICS})
    assert skill_bonus(c, Skill.ATHLETICS) == 3 + 2 * 2  # +2×prof


def test_ability_check_bonus_raw() -> None:
    # Голая проверка Силы — только модификатор (без навыка/владения).
    assert ability_check_bonus(_c(), Ability.STR) == 3


def test_roll_ability_check_dc() -> None:
    from dnd.application.engine.ability_check import roll_ability_check_raw
    from dnd.composition import build_scripted_dependencies
    from dnd.domain.entities.battlefield import Battlefield

    deps, _b, _ = build_scripted_dependencies(battlefield=Battlefield(1, 1), rolls=[10])
    c = _c()  # Атлетика +3 (STR16)
    c.skill_proficiencies = frozenset({Skill.ATHLETICS})  # +2 → итог +5
    # d20=10 + 5 = 15 >= 15 → успех.
    assert (
        roll_ability_check_raw(
            c,
            skill=Skill.ATHLETICS,
            dc=15,
            dice_roller=deps.dice_roller,
            modifier_applier=deps.modifier_applier,
        )
        is True
    )


def test_roll_ability_check_poisoned_disadvantage() -> None:
    from dnd.application.engine.ability_check import roll_ability_check_raw
    from dnd.application.engine.condition_service import ConditionService
    from dnd.composition import build_scripted_dependencies
    from dnd.domain.conditions.builtin import POISONED, register_default_conditions
    from dnd.domain.conditions.registry import ConditionRegistry
    from dnd.domain.entities.battlefield import Battlefield

    reg = ConditionRegistry()
    register_default_conditions(reg)
    deps, _b, _ = build_scripted_dependencies(battlefield=Battlefield(1, 1), rolls=[18, 3])
    c = _c()
    c.apply_condition(POISONED)  # помеха на ABILITY_CHECK → 2 d20, берём 3
    # d20=3 + 3(STR) = 6 < 12 → провал (без помехи 18 → успех).
    assert (
        roll_ability_check_raw(
            c,
            ability=Ability.STR,
            dc=12,
            dice_roller=deps.dice_roller,
            modifier_applier=deps.modifier_applier,
            condition_service=ConditionService(reg),
        )
        is False
    )


def test_passive_score_base() -> None:
    c = _c()  # WIS 10 → +0, без владения
    assert passive_score(c, Skill.PERCEPTION) == 10  # 10 + 0


def test_passive_score_proficient() -> None:
    c = _c()
    c.skill_proficiencies = frozenset({Skill.PERCEPTION})
    assert passive_score(c, Skill.PERCEPTION) == 12  # 10 + 0 + prof 2

"""Проверки характеристик и навыков (V) — зеркало ``saving_throw.py``.

Бонус навыка: модификатор управляющей характеристики (+ ``proficiency_bonus``
при владении, ещё + ``proficiency_bonus`` при Экспертизе). Проверка —
``d20 + бонус + adjustments``; помехи/преимущество от состояний (Poisoned/
Frightened дают помеху на ``ABILITY_CHECK`` — T3) приходят через
``ConditionService.collect_modifiers``. Пассивное значение — без броска.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.application.dto.rolls import RollContext, RollPurpose
from dnd.domain.values.dice import DiceExpr
from dnd.domain.values.modifiers import ModifierTargetKind
from dnd.domain.values.skill import SKILL_ABILITY

if TYPE_CHECKING:
    from dnd.application.engine.condition_service import ConditionService
    from dnd.application.engine.modifier_applier import ModifierApplier
    from dnd.application.engine.turn_context import TurnContext
    from dnd.application.ports.dice_roller import DiceRoller
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ability import Ability
    from dnd.domain.values.skill import Skill


def ability_check_bonus(actor: Creature, ability: Ability) -> int:
    """Бонус голой проверки характеристики — только модификатор (без навыка)."""
    return actor.abilities.modifier(ability)


def skill_bonus(actor: Creature, skill: Skill) -> int:
    """Бонус проверки навыка: mod (+prof если владеет) (+prof если Экспертиза)."""
    bonus = actor.abilities.modifier(SKILL_ABILITY[skill])
    if skill in actor.skill_proficiencies:
        bonus += actor.proficiency_bonus
    if skill in actor.skill_expertise:
        bonus += actor.proficiency_bonus
    return bonus


def _check_bonus(actor: Creature, skill: Skill | None, ability: Ability | None) -> int:
    """Бонус проверки: по навыку (если задан) иначе по голой характеристике.
    Ровно одно из ``skill``/``ability`` должно быть задано."""
    if skill is not None:
        return skill_bonus(actor, skill)
    if ability is not None:
        return ability_check_bonus(actor, ability)
    raise ValueError("проверка требует skill ИЛИ ability")


def roll_ability_check_raw(
    actor: Creature,
    *,
    skill: Skill | None = None,
    ability: Ability | None = None,
    dc: int,
    dice_roller: DiceRoller,
    modifier_applier: ModifierApplier,
    condition_service: ConditionService | None = None,
    tags: tuple[str, ...] = ("ability_check",),
) -> bool:
    """Проверка ``d20 + бонус + adjustments`` ≥ dc. Ровно одно из skill/ability.
    Помехи/преимущество от состояний (Poisoned/Frightened → помеха на
    ``ABILITY_CHECK``) приходят через ``condition_service``."""
    bonus = _check_bonus(actor, skill, ability)
    mods = list(
        modifier_applier.collect(owner_id=actor.id, target_kind=ModifierTargetKind.ABILITY_CHECK)
    )
    if condition_service is not None:
        mods += condition_service.collect_modifiers(actor, ModifierTargetKind.ABILITY_CHECK)
    adj = modifier_applier.to_roll_adjustments(mods)
    roll = dice_roller.roll(
        DiceExpr.parse(f"d20{bonus + adj.numeric_bonus:+d}"),
        RollContext(
            purpose=RollPurpose.ABILITY_CHECK,
            actor_id=actor.id,
            advantage=adj.advantage,
            disadvantage=adj.disadvantage,
            extra_dice=adj.extra_dice,
            tags=tags,
        ),
    )
    return roll.total >= dc


def _check_total(
    actor: Creature,
    skill: Skill,
    dice_roller: DiceRoller,
    modifier_applier: ModifierApplier,
    condition_service: ConditionService | None,
) -> int:
    """Сырой итог проверки навыка ``d20 + бонус + adjustments`` (для состязаний)."""
    bonus = skill_bonus(actor, skill)
    mods = list(
        modifier_applier.collect(owner_id=actor.id, target_kind=ModifierTargetKind.ABILITY_CHECK)
    )
    if condition_service is not None:
        mods += condition_service.collect_modifiers(actor, ModifierTargetKind.ABILITY_CHECK)
    adj = modifier_applier.to_roll_adjustments(mods)
    roll = dice_roller.roll(
        DiceExpr.parse(f"d20{bonus + adj.numeric_bonus:+d}"),
        RollContext(
            purpose=RollPurpose.ABILITY_CHECK,
            actor_id=actor.id,
            advantage=adj.advantage,
            disadvantage=adj.disadvantage,
            extra_dice=adj.extra_dice,
            tags=("opposed_check",),
        ),
    )
    return roll.total


def opposed_check_raw(
    actor: Creature,
    actor_skill: Skill,
    target: Creature,
    target_skills: tuple[Skill, ...],
    *,
    dice_roller: DiceRoller,
    modifier_applier: ModifierApplier,
    condition_service: ConditionService | None = None,
) -> bool:
    """Состязание: актёр против лучшей из проверок цели. ``True``, если итог
    актёра СТРОГО больше — ничья остаётся за защищающимся (PHB-2024 стр. 11)."""
    a = _check_total(actor, actor_skill, dice_roller, modifier_applier, condition_service)
    best = max(
        _check_total(target, s, dice_roller, modifier_applier, condition_service)
        for s in target_skills
    )
    return a > best


def passive_score(
    actor: Creature,
    skill: Skill,
    *,
    modifier_applier: ModifierApplier | None = None,
    condition_service: ConditionService | None = None,
) -> int:
    """Пассивное значение проверки = ``10 + бонус навыка`` (+ numeric-модификаторы,
    ±5 за преимущество/помеху — PHB-2024 стр. 11). Без броска. Пассивная
    Внимательность = ``passive_score(actor, Skill.PERCEPTION)``."""
    score = 10 + skill_bonus(actor, skill)
    if modifier_applier is not None:
        mods = list(
            modifier_applier.collect(
                owner_id=actor.id, target_kind=ModifierTargetKind.ABILITY_CHECK
            )
        )
        if condition_service is not None:
            mods += condition_service.collect_modifiers(actor, ModifierTargetKind.ABILITY_CHECK)
        adj = modifier_applier.to_roll_adjustments(mods)
        score += adj.numeric_bonus
        if adj.advantage and not adj.disadvantage:
            score += 5
        elif adj.disadvantage and not adj.advantage:
            score -= 5
    return score


def roll_ability_check(
    actor: Creature,
    *,
    skill: Skill | None = None,
    ability: Ability | None = None,
    dc: int,
    ctx: TurnContext,
    tags: tuple[str, ...] = ("ability_check",),
) -> bool:
    """Проверка в контексте хода — делегирует в raw."""
    return roll_ability_check_raw(
        actor,
        skill=skill,
        ability=ability,
        dc=dc,
        dice_roller=ctx.dice_roller,
        modifier_applier=ctx.modifier_applier,
        condition_service=ctx.condition_service,
        tags=tags,
    )


__all__ = [
    "ability_check_bonus",
    "opposed_check_raw",
    "passive_score",
    "roll_ability_check",
    "roll_ability_check_raw",
    "skill_bonus",
]

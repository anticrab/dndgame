"""Единая точка броска спасброска (T1).

Учитывает бонус мастерства, если существо профициентно в этом спасброске
(PHB-2024 стр. 9): ``d20 + ability_mod (+ prof) + adjustments``, плюс
advantage/disadvantage/numeric от состояний. Так prof-логика не дублируется
в SaveSpellHandler и concentration-save (REV-1).

``saving_throw_bonus`` — общий расчёт модификатора (характеристика + prof);
``roll_saving_throw`` — полный бросок (нужен ``TurnContext``). Concentration-save
в Encounter (нет ctx) использует ``saving_throw_bonus`` напрямую.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.application.dto.rolls import RollContext, RollPurpose
from dnd.domain.values.dice import DiceExpr
from dnd.domain.values.modifiers import ModifierTargetKind

if TYPE_CHECKING:
    from dnd.application.engine.modifier_applier import ModifierApplier
    from dnd.application.engine.turn_context import TurnContext
    from dnd.application.ports.dice_roller import DiceRoller
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ability import Ability


def saving_throw_bonus(actor: Creature, ability: Ability) -> int:
    """Модификатор спасброска: характеристика + бонус мастерства, если
    существо профициентно в этом спасброске (PHB-2024 стр. 9)."""
    mod = actor.abilities.modifier(ability)
    if ability in actor.saving_throw_proficiencies:
        return mod + actor.proficiency_bonus
    return mod


def roll_saving_throw_raw(
    actor: Creature,
    ability: Ability,
    *,
    dc: int,
    dice_roller: DiceRoller,
    modifier_applier: ModifierApplier,
    tags: tuple[str, ...] = ("saving_throw",),
) -> bool:
    """Бросок спасброска без боевого ``TurnContext`` — нужен службам вне хода
    (OngoingEffectTracker, concentration). ``d20 + saving_throw_bonus +
    adjustments`` ≥ dc; учитывает advantage/disadvantage от состояний."""
    bonus = saving_throw_bonus(actor, ability)
    adj = modifier_applier.to_roll_adjustments(
        modifier_applier.collect(
            owner_id=actor.id, target_kind=ModifierTargetKind.SAVING_THROW
        )
    )
    roll = dice_roller.roll(
        DiceExpr.parse(f"d20{bonus + adj.numeric_bonus:+d}"),
        RollContext(
            purpose=RollPurpose.SAVE, actor_id=actor.id,
            advantage=adj.advantage, disadvantage=adj.disadvantage,
            extra_dice=adj.extra_dice, tags=tags,
        ),
    )
    return roll.total >= dc


def roll_saving_throw(
    actor: Creature,
    ability: Ability,
    *,
    dc: int,
    ctx: TurnContext,
    tags: tuple[str, ...] = ("saving_throw",),
) -> bool:
    """Бросок спасброска в контексте хода — делегирует в raw."""
    return roll_saving_throw_raw(
        actor, ability, dc=dc,
        dice_roller=ctx.dice_roller, modifier_applier=ctx.modifier_applier,
        tags=tags,
    )


__all__ = ["roll_saving_throw", "roll_saving_throw_raw", "saving_throw_bonus"]

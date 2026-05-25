"""Встроенные хендлеры эффектов заклинаний (этап P1).

Каждый класс обрабатывает один :class:`SpellEffect`. Регистрируются в
``defaults.default_spell_effect_registry``. Добавление нового типа воздействия —
новый класс здесь (или в плагине) + регистрация, без касания CastSpellAction.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.application.dto.engine_event import DamageDealt, HealingApplied
from dnd.application.dto.rolls import RollContext, RollPurpose
from dnd.domain.values.damage import DamageInstance
from dnd.domain.values.dice import DiceExpr
from dnd.domain.values.modifiers import (
    DiceBonusEffect,
    Modifier,
    ModifierSourceKind,
    ModifierTargetKind,
    NumericBonusEffect,
)

if TYPE_CHECKING:
    from dnd.application.engine.turn_context import TurnContext
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.spell import Spell


def _effective_ac(target: Creature, ctx: TurnContext) -> int:
    """КД цели с учётом модификаторов (баффы вроде Shield of Faith)."""
    ac_mods = ctx.modifier_applier.collect(
        owner_id=target.id, target_kind=ModifierTargetKind.ARMOR_CLASS
    )
    ac_adj = ctx.modifier_applier.to_roll_adjustments(ac_mods)
    return target.armor_class + ac_adj.numeric_bonus


class AttackSpellHandler:
    """ATTACK: бросок атаки заклинанием (d20 + spell attack) против КД."""

    def apply(
        self,
        caster: Creature,
        targets: tuple[Creature, ...],
        spell: Spell,
        ctx: TurnContext,
    ) -> None:
        assert spell.dice is not None and spell.damage_type is not None
        for target in targets:
            atk_bonus = caster.spell_attack_bonus()
            atk_mods = ctx.modifier_applier.collect(
                owner_id=caster.id, target_kind=ModifierTargetKind.ATTACK_ROLL
            )
            atk_adj = ctx.modifier_applier.to_roll_adjustments(atk_mods)
            roll = ctx.dice_roller.roll(
                DiceExpr.parse(f"d20{atk_bonus + atk_adj.numeric_bonus:+d}"),
                RollContext(
                    purpose=RollPurpose.ATTACK,
                    actor_id=caster.id,
                    target_id=target.id,
                    advantage=atk_adj.advantage,
                    disadvantage=atk_adj.disadvantage,
                    extra_dice=atk_adj.extra_dice,
                    tags=("spell_attack",),
                ),
            )
            is_crit = roll.is_natural_20()
            if is_crit:
                hit = True
            elif roll.is_natural_1():
                hit = False
            else:
                hit = roll.total >= _effective_ac(target, ctx)
            if not hit:
                continue
            dmg_roll = ctx.dice_roller.roll(
                DiceExpr.parse(spell.dice),
                RollContext(
                    purpose=RollPurpose.DAMAGE,
                    actor_id=caster.id,
                    target_id=target.id,
                    crit=is_crit,
                ),
            )
            raw = max(0, dmg_roll.total)
            result = target.take_damage(
                DamageInstance(amount=raw, type_=spell.damage_type),
                is_critical=is_crit,
            )
            ctx.event_bus.publish(
                DamageDealt(
                    attacker_id=caster.id,
                    target_id=target.id,
                    damage_roll_id=dmg_roll.roll_id,
                    damage_type=spell.damage_type,
                    raw_amount=raw,
                    final_amount=result.final_amount,
                    is_critical=is_crit,
                    hp_after=target.hit_points.current,
                    hp_max=target.hit_points.maximum,
                    was_lethal=result.was_lethal,
                )
            )


class SaveSpellHandler:
    """SAVE: цель кидает спасбросок против Сл. заклинания.

    Провал → полный урон; успех → половина (``save_for_half=True``) или ноль.
    """

    def apply(
        self,
        caster: Creature,
        targets: tuple[Creature, ...],
        spell: Spell,
        ctx: TurnContext,
    ) -> None:
        assert (
            spell.dice is not None
            and spell.damage_type is not None
            and spell.save_ability is not None
        )
        dc = caster.spell_save_dc()
        for target in targets:
            dmg_roll = ctx.dice_roller.roll(
                DiceExpr.parse(spell.dice),
                RollContext(
                    purpose=RollPurpose.DAMAGE,
                    actor_id=caster.id,
                    target_id=target.id,
                ),
            )
            save_mod = target.abilities.modifier(spell.save_ability)
            save_mods = ctx.modifier_applier.collect(
                owner_id=target.id, target_kind=ModifierTargetKind.SAVING_THROW
            )
            save_adj = ctx.modifier_applier.to_roll_adjustments(save_mods)
            save_roll = ctx.dice_roller.roll(
                DiceExpr.parse(f"d20{save_mod + save_adj.numeric_bonus:+d}"),
                RollContext(
                    purpose=RollPurpose.SAVE,
                    actor_id=target.id,
                    advantage=save_adj.advantage,
                    disadvantage=save_adj.disadvantage,
                    extra_dice=save_adj.extra_dice,
                    tags=("spell_save",),
                ),
            )
            full = max(0, dmg_roll.total)
            if save_roll.total < dc:
                amount = full              # провал — полный урон
            elif spell.save_for_half:
                amount = full // 2         # успех + save_for_half — половина
            else:
                amount = 0                 # успех без save_for_half — ноль
            result = target.take_damage(
                DamageInstance(amount=amount, type_=spell.damage_type)
            )
            ctx.event_bus.publish(
                DamageDealt(
                    attacker_id=caster.id,
                    target_id=target.id,
                    damage_roll_id=dmg_roll.roll_id,
                    damage_type=spell.damage_type,
                    raw_amount=amount,
                    final_amount=result.final_amount,
                    is_critical=False,
                    hp_after=target.hit_points.current,
                    hp_max=target.hit_points.maximum,
                    was_lethal=result.was_lethal,
                )
            )


class AutoSpellHandler:
    """AUTO: авто-попадание без броска атаки (Magic Missile)."""

    def apply(
        self,
        caster: Creature,
        targets: tuple[Creature, ...],
        spell: Spell,
        ctx: TurnContext,
    ) -> None:
        assert spell.dice is not None and spell.damage_type is not None
        for target in targets:
            dmg_roll = ctx.dice_roller.roll(
                DiceExpr.parse(spell.dice),
                RollContext(
                    purpose=RollPurpose.DAMAGE,
                    actor_id=caster.id,
                    target_id=target.id,
                ),
            )
            raw = max(0, dmg_roll.total)
            result = target.take_damage(
                DamageInstance(amount=raw, type_=spell.damage_type)
            )
            ctx.event_bus.publish(
                DamageDealt(
                    attacker_id=caster.id,
                    target_id=target.id,
                    damage_roll_id=dmg_roll.roll_id,
                    damage_type=spell.damage_type,
                    raw_amount=raw,
                    final_amount=result.final_amount,
                    is_critical=False,
                    hp_after=target.hit_points.current,
                    hp_max=target.hit_points.maximum,
                    was_lethal=result.was_lethal,
                )
            )


class HealSpellHandler:
    """HEAL: восстановление HP = бросок heal_dice + mod заклинательной хар-ки."""

    def apply(
        self,
        caster: Creature,
        targets: tuple[Creature, ...],
        spell: Spell,
        ctx: TurnContext,
    ) -> None:
        assert spell.heal_dice is not None and caster.spellcasting_ability is not None
        mod = caster.abilities.modifier(caster.spellcasting_ability)
        for target in targets:
            heal_roll = ctx.dice_roller.roll(
                DiceExpr.parse(spell.heal_dice),
                RollContext(
                    purpose=RollPurpose.OTHER,
                    actor_id=caster.id,
                    target_id=target.id,
                    tags=("heal",),
                ),
            )
            amount = max(0, heal_roll.total + mod)
            result = target.heal(amount)
            ctx.event_bus.publish(
                HealingApplied(
                    healer_id=caster.id,
                    target_id=target.id,
                    amount=result.final_amount,
                    hp_after=target.hit_points.current,
                    hp_max=target.hit_points.maximum,
                )
            )


def concentration_source(caster_id: object) -> str:
    """source_id для concentration-баффов кастера. Per-caster (не per-spell):
    одна концентрация на кастера, поэтому снять прежний эффект и почистить
    при срыве (Encounter._on_downed, MAJOR-1) можно зная только caster_id."""
    return f"concentration:{caster_id}"


class BuffSpellHandler:
    """BUFF: бафф цели (P1 — бонус КД, напр. Shield of Faith +2).

    Concentration-баффы регистрируются модификатором в ModifierApplier с
    source_id ``concentration:{caster}``; старт нового concentration-заклинания
    снимает прежний бафф (одна концентрация на кастера, PHB-2024 стр. 235).
    Срыв концентрации при падении кастера чистит этот же source в Encounter.
    """

    def apply(
        self,
        caster: Creature,
        targets: tuple[Creature, ...],
        spell: Spell,
        ctx: TurnContext,
    ) -> None:
        if spell.concentration and caster.concentration is not None:
            # Снять прежний concentration-эффект (заменяется новым).
            ctx.modifier_applier.remove_by_source(concentration_source(caster.id))
        if spell.concentration:
            caster.concentration = spell.id
        source_id = concentration_source(caster.id)
        for target in targets:
            for buff in spell.buffs:
                effect = (
                    DiceBonusEffect(dice=buff.dice_bonus)
                    if buff.dice_bonus is not None
                    else NumericBonusEffect(value=buff.numeric_bonus)
                )
                ctx.modifier_applier.add(
                    Modifier(
                        source_id=source_id,
                        source_kind=ModifierSourceKind.SPELL,
                        target_kind=buff.target,
                        effect=effect,
                        owner_id=target.id,
                        stack_key=str(spell.id),
                    )
                )


__all__ = [
    "AttackSpellHandler",
    "AutoSpellHandler",
    "BuffSpellHandler",
    "HealSpellHandler",
    "SaveSpellHandler",
]

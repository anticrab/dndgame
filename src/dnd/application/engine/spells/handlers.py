"""Встроенные хендлеры эффектов заклинаний (этап P1).

Каждый класс обрабатывает один :class:`SpellEffect`. Регистрируются в
``defaults.default_spell_effect_registry``. Добавление нового типа воздействия —
новый класс здесь (или в плагине) + регистрация, без касания CastSpellAction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.application.dto.engine_event import (
    BuffApplied,
    ConditionApplied,
    DamageDealt,
    HealingApplied,
)
from dnd.application.dto.rolls import RollContext, RollPurpose
from dnd.application.engine.saving_throw import roll_saving_throw
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
    from dnd.domain.values.spell_power import SpellPower


def _expires_at(spell: Spell, ctx: TurnContext) -> int | None:
    """Дедлайн снятия эффекта по часам (X0) — только для конечной положительной
    длительности. INSTANT (0) и безлимитные (None: PERMANENT / концентрация без
    потолка) → ``None``: эффект снимается своими триггерами (урон / повторный
    спасбросок / срыв концентрации), а не по времени. Длительность дополняет
    триггеры, не заменяет их."""
    return ctx.clock.expires_at(spell.duration) if spell.duration.to_rounds() else None


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
        power: SpellPower,
    ) -> None:
        assert spell.dice is not None and spell.damage_type is not None
        for target in targets:
            atk_bonus = power.attack_bonus
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
        power: SpellPower,
    ) -> None:
        assert (
            spell.dice is not None
            and spell.damage_type is not None
            and spell.save_ability is not None
        )
        dc = power.save_dc
        for target in targets:
            dmg_roll = ctx.dice_roller.roll(
                DiceExpr.parse(spell.dice),
                RollContext(
                    purpose=RollPurpose.DAMAGE,
                    actor_id=caster.id,
                    target_id=target.id,
                ),
            )
            # T1: единый бросок спасброска (учитывает prof класса цели).
            saved = roll_saving_throw(
                target,
                spell.save_ability,
                dc=dc,
                ctx=ctx,
                tags=("spell_save",),
            )
            full = max(0, dmg_roll.total)
            if not saved:
                amount = full  # провал — полный урон
            elif spell.save_for_half:
                amount = full // 2  # успех + save_for_half — половина
            else:
                amount = 0  # успех без save_for_half — ноль
            result = target.take_damage(DamageInstance(amount=amount, type_=spell.damage_type))
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
        power: SpellPower,  # единый протокол; AUTO power не использует
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
            result = target.take_damage(DamageInstance(amount=raw, type_=spell.damage_type))
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
    """HEAL: восстановление HP = бросок heal_dice + ``power.ability_mod``.

    В спелл-пути ``power`` берётся из кастера (мод заклинательной хар-ки), в
    item-пути зелья — ``power.potion()`` с ``ability_mod=0`` (зелье лечит ровно
    по кости, без мода пьющего)."""

    def apply(
        self,
        caster: Creature,
        targets: tuple[Creature, ...],
        spell: Spell,
        ctx: TurnContext,
        power: SpellPower,
    ) -> None:
        assert spell.heal_dice is not None
        mod = power.ability_mod
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
        power: SpellPower,  # единый протокол; BUFF power не использует
    ) -> None:
        if spell.concentration and caster.concentration is not None:
            # Снять прежний concentration-эффект (заменяется новым).
            ctx.modifier_applier.remove_by_source(concentration_source(caster.id))
        if spell.concentration:
            caster.concentration = spell.id
        expires_at_round = _expires_at(spell, ctx)
        for target in targets:
            # Концентрационный бафф — общий source на кастера (одна концентрация =
            # один source_id, чтобы срыв/смена концентрации снимали группу разом).
            # Не-концентрационный (зелье силы, эликсиры) — собственный per-spell/per-owner
            # source_id: независим от концентрации, не сносится её сменой (U3-1).
            source_id = (
                concentration_source(caster.id)
                if spell.concentration
                else f"buff:{spell.id}:{target.id}"
            )
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
            # X0: если длительность конечна — зарегистрировать дедлайн снятия по
            # часам (concentration-баффы без потолка снимаются срывом концентрации).
            if expires_at_round is not None:
                ctx.event_bus.publish(
                    BuffApplied(
                        owner_id=target.id,
                        source_id=source_id,
                        expires_at_round=expires_at_round,
                    )
                )


class ControlSpellHandler:
    """CONTROL: наложение состояния. Две ветки гейта (валидация — в Spell):

    * пул (``hp_pool_dice``, Sleep): кидаем пул хитов, усыпляем цели по
      возрастанию текущего HP, пока хватает; без спасброска;
    * спасбросок (``save_ability``, Hold Person): провал → состояние.

    Накладывает через ConditionService (каскад implies) и публикует
    ``ConditionApplied`` со всей метой снятия — её слушает OngoingEffectTracker.
    """

    def apply(
        self,
        caster: Creature,
        targets: tuple[Creature, ...],
        spell: Spell,
        ctx: TurnContext,
        power: SpellPower,
    ) -> None:
        assert spell.condition is not None
        if spell.hp_pool_dice is not None:
            affected = self._apply_pool(caster, targets, spell, ctx, power)
        else:
            affected = self._apply_save(caster, targets, spell, ctx, power)
        if affected and spell.concentration:
            caster.concentration = spell.id

    def _apply_pool(
        self,
        caster: Creature,
        targets: tuple[Creature, ...],
        spell: Spell,
        ctx: TurnContext,
        power: SpellPower,
    ) -> list[Creature]:
        assert spell.hp_pool_dice is not None
        pool_roll = ctx.dice_roller.roll(
            DiceExpr.parse(spell.hp_pool_dice),
            RollContext(purpose=RollPurpose.OTHER, actor_id=caster.id),
        )
        pool = pool_roll.total
        candidates = sorted(
            (t for t in targets if t.is_alive and not t.is_at_zero_hp),
            key=lambda c: c.hit_points.current,
        )
        affected: list[Creature] = []
        for cand in candidates:
            need = cand.hit_points.current
            if need > pool:
                break  # книга: первый, на кого не хватило пула, не засыпает
            pool -= need
            if self._apply_condition(caster, cand, spell, ctx, power):
                affected.append(cand)
        return affected

    def _apply_save(
        self,
        caster: Creature,
        targets: tuple[Creature, ...],
        spell: Spell,
        ctx: TurnContext,
        power: SpellPower,
    ) -> list[Creature]:
        assert spell.save_ability is not None
        dc = power.save_dc
        affected: list[Creature] = []
        for target in targets:
            if not target.is_alive or target.is_at_zero_hp:
                continue
            saved = roll_saving_throw(
                target,
                spell.save_ability,
                dc=dc,
                ctx=ctx,
                tags=("spell_save",),
            )
            if not saved and self._apply_condition(caster, target, spell, ctx, power):
                affected.append(target)
        return affected

    def _apply_condition(
        self,
        caster: Creature,
        target: Creature,
        spell: Spell,
        ctx: TurnContext,
        power: SpellPower,
    ) -> bool:
        assert spell.condition is not None
        result = ctx.condition_service.apply_with_implies(target, spell.condition)
        if not result.applied:
            return False
        dc = power.save_dc if spell.save_ability is not None else None
        ctx.event_bus.publish(
            ConditionApplied(
                caster_id=caster.id,
                target_id=target.id,
                spell_id=spell.id,
                conditions=result.applied,
                ends_on_damage=spell.condition_ends_on_damage,
                repeat_save_ability=(spell.save_ability if spell.condition_repeat_save else None),
                save_dc=dc if spell.condition_repeat_save else None,
                concentration=spell.concentration,
                expires_at_round=_expires_at(spell, ctx),
            )
        )
        return True


__all__ = [
    "AttackSpellHandler",
    "AutoSpellHandler",
    "BuffSpellHandler",
    "ControlSpellHandler",
    "HealSpellHandler",
    "SaveSpellHandler",
]

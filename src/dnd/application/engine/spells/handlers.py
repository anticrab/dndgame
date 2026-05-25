"""Встроенные хендлеры эффектов заклинаний (этап P1).

Каждый класс обрабатывает один :class:`SpellEffect`. Регистрируются в
``defaults.default_spell_effect_registry``. Добавление нового типа воздействия —
новый класс здесь (или в плагине) + регистрация, без касания CastSpellAction.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.application.dto.engine_event import DamageDealt
from dnd.application.dto.modifiers import ModifierTargetKind
from dnd.application.dto.rolls import RollContext, RollPurpose
from dnd.domain.values.damage import DamageInstance
from dnd.domain.values.dice import DiceExpr

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
            roll = ctx.dice_roller.roll(
                DiceExpr.parse(f"d20{atk_bonus:+d}"),
                RollContext(
                    purpose=RollPurpose.ATTACK,
                    actor_id=caster.id,
                    target_id=target.id,
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
                )
            )


__all__ = ["AttackSpellHandler"]

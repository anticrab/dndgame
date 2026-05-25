"""CastSpellAction — сотворение заклинания (этап P1).

Тонкое действие: проверяет кастера/слот/цель/экономику, публикует
:class:`SpellCast` и **делегирует** обработку эффекта реестру
:class:`SpellEffectRegistry` (open/closed — новый тип воздействия добавляется
хендлером, не правкой этого класса). Заклинания — data-driven (YAML).
"""
from __future__ import annotations

from dnd.application.dto.action import (
    ActionAvailability,
    ActionEconomyCost,
    ActionOutcome,
    ActionParams,
    Allowed,
    Forbidden,
    ForbiddenReason,
)
from dnd.application.dto.engine_event import SpellCast
from dnd.application.engine.spells.area import (
    AreaShapeRegistry,
    default_area_shape_registry,
)
from dnd.application.engine.spells.defaults import default_spell_effect_registry
from dnd.application.engine.spells.effect_handler import SpellEffectRegistry
from dnd.application.engine.turn_context import TurnContext
from dnd.application.ports.spell_repository import SpellRepository
from dnd.domain.entities.creature import Creature
from dnd.domain.values.direction import Direction
from dnd.domain.values.ids import ActionId, CreatureId, SpellId
from dnd.domain.values.spell import OriginMode, Spell, SpellEffect, TargetKind
from dnd.domain.values.square import Square


class CastSpellParams(ActionParams):
    spell_id: SpellId
    target_id: CreatureId | None = None
    # AoE (P2): точка прицеливания (AT_POINT) или направление (FROM_CASTER).
    target_point: Square | None = None
    direction: Direction | None = None


class CastSpellAction:
    """Сотворить заклинание из ``known_spells`` по данным каталога."""

    id_value = ActionId("cast_spell")
    economy_cost_value = ActionEconomyCost.ACTION

    def __init__(
        self,
        spell_repository: SpellRepository,
        effect_registry: SpellEffectRegistry | None = None,
        area_registry: AreaShapeRegistry | None = None,
    ) -> None:
        self._spells = spell_repository
        self._effects = effect_registry or default_spell_effect_registry()
        self._areas = area_registry or default_area_shape_registry()

    # --- helpers -------------------------------------------------------

    def _resolve_targets(
        self, spell: Spell, caster: Creature, params: CastSpellParams,
        ctx: TurnContext,
    ) -> tuple[Creature, ...]:
        spec = spell.targeting
        kind = spec.kind
        if kind is TargetKind.SELF:
            return (caster,)
        if kind is TargetKind.SINGLE:
            assert params.target_id is not None
            return (ctx.participants[params.target_id],)
        if kind is TargetKind.AREA:
            assert spec.shape is not None
            origin = (
                ctx.battlefield.position_of(caster.id)
                if spec.origin is OriginMode.FROM_CASTER
                else params.target_point
            )
            assert origin is not None
            squares = self._areas.get(spec.shape).squares(
                origin, params.direction, spec, ctx.battlefield
            )
            # Все живые существа в задетых клетках (friendly fire включён).
            return tuple(
                cr
                for cid, cr in ctx.participants.items()
                if cr.is_alive and ctx.battlefield.position_of(cid) in squares
            )
        # MULTI (pick-N) — этап P2b.
        raise NotImplementedError(f"targeting {kind} — этап P2b")

    # --- availability --------------------------------------------------

    def can_perform_against(
        self, actor: Creature, params: CastSpellParams, ctx: TurnContext
    ) -> ActionAvailability:
        if actor.spellcasting_ability is None:
            return Forbidden(
                reason=ForbiddenReason.CUSTOM, details="not a spellcaster"
            )
        if params.spell_id not in actor.known_spells:
            return Forbidden(
                reason=ForbiddenReason.CUSTOM,
                details=f"spell not known: {params.spell_id}",
            )
        if not self._spells.contains(params.spell_id):
            return Forbidden(reason=ForbiddenReason.NO_VALID_TARGETS)
        spell = self._spells.load(params.spell_id)
        if spell.effect not in self._effects:
            return Forbidden(
                reason=ForbiddenReason.CUSTOM,
                details=f"effect not supported: {spell.effect}",
            )
        if not ctx.can_spend(ActionEconomyCost.ACTION):
            return Forbidden(reason=ForbiddenReason.NO_ECONOMY_LEFT)
        if spell.level > 0 and not actor.has_spell_slot(spell.level):
            return Forbidden(
                reason=ForbiddenReason.CUSTOM,
                details=f"no spell slot of level {spell.level}",
            )
        # Цель.
        if spell.targeting.kind is TargetKind.SINGLE:
            if params.target_id is None or params.target_id not in ctx.participants:
                return Forbidden(reason=ForbiddenReason.NO_VALID_TARGETS)
            target = ctx.participants[params.target_id]
            # audit MAJOR-2: liveness-guard в Action, а не только в UI.
            # Урон-заклинания (ATTACK/SAVE/AUTO) — только по живой цели
            # (нельзя бить труп). Heal/buff — по живой ИЛИ умирающей (dying),
            # но не по окончательно мёртвой.
            offensive = spell.effect in (
                SpellEffect.ATTACK, SpellEffect.SAVE, SpellEffect.AUTO
            )
            if offensive:
                if not target.is_alive:
                    return Forbidden(reason=ForbiddenReason.TARGET_DOWN)
            elif not target.is_alive and not (
                target.death_saves is not None and not target.death_saves.is_dead
            ):
                return Forbidden(reason=ForbiddenReason.TARGET_DOWN)
            actor_pos = ctx.battlefield.position_of(actor.id)
            target_pos = ctx.battlefield.position_of(params.target_id)
            if actor_pos.distance_to_feet(target_pos) > spell.range_ft:
                return Forbidden(reason=ForbiddenReason.OUT_OF_RANGE)
        elif spell.targeting.kind is TargetKind.AREA:
            shape = spell.targeting.shape
            if shape is None or shape not in self._areas:
                return Forbidden(
                    reason=ForbiddenReason.CUSTOM,
                    details=f"area shape not supported: {shape}",
                )
            if spell.targeting.origin is OriginMode.AT_POINT:
                if params.target_point is None:
                    return Forbidden(reason=ForbiddenReason.NO_VALID_TARGETS)
                actor_pos = ctx.battlefield.position_of(actor.id)
                if actor_pos.distance_to_feet(params.target_point) > spell.range_ft:
                    return Forbidden(reason=ForbiddenReason.OUT_OF_RANGE)
            elif params.direction is None:  # FROM_CASTER требует направления
                return Forbidden(reason=ForbiddenReason.NO_VALID_TARGETS)
        return Allowed()

    # --- execution -----------------------------------------------------

    def execute(
        self, actor: Creature, params: ActionParams, ctx: TurnContext
    ) -> ActionOutcome:
        if not isinstance(params, CastSpellParams):
            raise TypeError(
                f"CastSpellAction expects CastSpellParams, got {type(params).__name__}"
            )
        avail = self.can_perform_against(actor, params, ctx)
        if isinstance(avail, Forbidden):
            return ActionOutcome(success=False, consumed=ActionEconomyCost.FREE)

        spell = self._spells.load(params.spell_id)
        targets = self._resolve_targets(spell, actor, params, ctx)

        actor.consume_spell_slot(spell.level)
        ctx.spend(ActionEconomyCost.ACTION)

        ctx.event_bus.publish(
            SpellCast(
                caster_id=actor.id,
                spell_id=str(spell.id),
                spell_name=spell.name,
                slot_level=spell.level,
                target_id=params.target_id,
            )
        )
        self._effects.get(spell.effect).apply(actor, targets, spell, ctx)
        return ActionOutcome(
            success=True,
            consumed=ActionEconomyCost.ACTION,
            notes=f"cast {spell.id}",
        )


__all__ = ["CastSpellAction", "CastSpellParams"]

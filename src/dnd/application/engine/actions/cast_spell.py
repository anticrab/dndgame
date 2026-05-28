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
from dnd.application.engine.spells.resolve import resolve_and_apply_spell
from dnd.application.engine.spells.targeting_validation import validate_spell_targeting
from dnd.application.engine.turn_context import TurnContext
from dnd.application.ports.spell_repository import SpellRepository
from dnd.domain.entities.creature import Creature
from dnd.domain.values.direction import Direction
from dnd.domain.values.ids import ActionId, CreatureId, SpellId
from dnd.domain.values.spell_power import SpellPower
from dnd.domain.values.square import Square


class CastSpellParams(ActionParams):
    spell_id: SpellId
    target_id: CreatureId | None = None
    # MULTI (P2b): мультимножество выбранных целей (дубли допустимы, порядок=выборы).
    target_ids: tuple[CreatureId, ...] = ()
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

    # --- availability --------------------------------------------------

    def can_perform_against(
        self, actor: Creature, params: CastSpellParams, ctx: TurnContext
    ) -> ActionAvailability:
        if actor.spellcasting_ability is None:
            return Forbidden(reason=ForbiddenReason.CUSTOM, details="not a spellcaster")
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
        targeting_err = validate_spell_targeting(
            actor,
            spell,
            ctx,
            target_id=params.target_id,
            target_ids=params.target_ids,
            target_point=params.target_point,
            direction=params.direction,
            areas=self._areas,
        )
        if targeting_err is not None:
            return targeting_err
        return Allowed()

    # --- execution -----------------------------------------------------

    def execute(self, actor: Creature, params: ActionParams, ctx: TurnContext) -> ActionOutcome:
        if not isinstance(params, CastSpellParams):
            raise TypeError(f"CastSpellAction expects CastSpellParams, got {type(params).__name__}")
        avail = self.can_perform_against(actor, params, ctx)
        if isinstance(avail, Forbidden):
            return ActionOutcome(success=False, consumed=ActionEconomyCost.FREE)

        spell = self._spells.load(params.spell_id)
        actor.consume_spell_slot(spell.level)
        ctx.spend(ActionEconomyCost.ACTION)

        ctx.event_bus.publish(
            SpellCast(
                caster_id=actor.id,
                spell_id=str(spell.id),
                spell_name=spell.name,
                slot_level=spell.level,
                target_id=params.target_id,
                target_ids=params.target_ids,
            )
        )
        resolve_and_apply_spell(
            actor,
            spell,
            ctx=ctx,
            power=SpellPower.from_caster(actor),
            target_id=params.target_id,
            target_ids=params.target_ids,
            target_point=params.target_point,
            direction=params.direction,
            effect_registry=self._effects,
            area_registry=self._areas,
        )
        return ActionOutcome(
            success=True,
            consumed=ActionEconomyCost.ACTION,
            notes=f"cast {spell.id}",
        )


__all__ = ["CastSpellAction", "CastSpellParams"]

"""UseItemAction — slotless-применение эффекта предмета (U2-4).

Зелья/свитки доставляют эффект-пакет через единое ядро
:func:`resolve_and_apply_spell`. Сам эффект описан **в каталоге заклинаний** —
предмет ссылается на него по ``effect_id`` (см. :class:`ItemUseSpec`). Никакого
дублирования логики хендлеров (HEAL/BUFF/ATTACK/SAVE/AUTO/CONTROL).

Отличие от :class:`CastSpellAction`:

* слот **не тратится** (свиток — заведомо slotless; для зелья слотов нет в
  принципе) — ``actor.consume_spell_slot`` не вызывается;
* экономика берётся **из данных** (``ItemUseSpec.economy``), не фиксирована
  ``ACTION``;
* «сила» эффекта подменяется: ``SpellPower.scroll(level)`` для свитка,
  ``SpellPower.potion()`` для зелья (см. :class:`SpellPower`);
* по факту применения публикуется :class:`ItemUsed`; если ``consumed`` —
  единица списывается из инвентаря.

Item грузим **из инвентаря** (он там уже лежит), не из ItemRepository.
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
from dnd.application.dto.engine_event import ItemUsed
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
from dnd.domain.values.ids import ActionId, CreatureId
from dnd.domain.values.item import ItemId
from dnd.domain.values.spell_power import SpellPower
from dnd.domain.values.square import Square


class UseItemParams(ActionParams):
    item_id: ItemId
    target_id: CreatureId | None = None
    # Для multi-эффект-пакета (если предмет ссылается на MULTI-заклинание).
    target_ids: tuple[CreatureId, ...] = ()
    # Для AoE-свитков: точка прицеливания (AT_POINT) или направление (FROM_CASTER).
    target_point: Square | None = None
    direction: Direction | None = None


class UseItemAction:
    """Применить эффект-пакет, на который ссылается ``Item.use`` из инвентаря."""

    id_value = ActionId("use_item")
    # Реальная экономика — из данных предмета; это значение для дефолтных
    # «расписаний экономики» (когда конкретного предмета нет под рукой).
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
        self, actor: Creature, params: UseItemParams, ctx: TurnContext
    ) -> ActionAvailability:
        stack = actor.inventory.find_by_id(params.item_id)
        if stack is None:
            return Forbidden(
                reason=ForbiddenReason.CUSTOM,
                details=f"item not in inventory: {params.item_id}",
            )
        item = stack.item
        if item.use is None:
            return Forbidden(
                reason=ForbiddenReason.CUSTOM,
                details=f"item is not usable: {params.item_id}",
            )
        use = item.use
        if not self._spells.contains(use.effect_id):
            return Forbidden(
                reason=ForbiddenReason.CUSTOM,
                details=f"unknown effect: {use.effect_id}",
            )
        spell = self._spells.load(use.effect_id)
        if spell.effect not in self._effects:
            return Forbidden(
                reason=ForbiddenReason.CUSTOM,
                details=f"effect not supported: {spell.effect}",
            )
        real_econ = ActionEconomyCost(use.economy)
        if not ctx.can_spend(real_econ):
            return Forbidden(reason=ForbiddenReason.NO_ECONOMY_LEFT)
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
        if not isinstance(params, UseItemParams):
            raise TypeError(f"UseItemAction expects UseItemParams, got {type(params).__name__}")
        avail = self.can_perform_against(actor, params, ctx)
        if isinstance(avail, Forbidden):
            return ActionOutcome(success=False, consumed=ActionEconomyCost.FREE)

        stack = actor.inventory.find_by_id(params.item_id)
        assert stack is not None  # гарантировано guard'ом can_perform
        item = stack.item
        assert item.use is not None
        use = item.use

        spell = self._spells.load(use.effect_id)
        real_econ = ActionEconomyCost(use.economy)
        power = SpellPower.scroll(spell.level) if use.is_scroll else SpellPower.potion()

        ctx.spend(real_econ)
        resolve_and_apply_spell(
            actor,
            spell,
            ctx=ctx,
            power=power,
            target_id=params.target_id,
            target_ids=params.target_ids,
            target_point=params.target_point,
            direction=params.direction,
            effect_registry=self._effects,
            area_registry=self._areas,
        )
        if use.consumed:
            actor.inventory.remove_one(params.item_id)
        ctx.event_bus.publish(
            ItemUsed(
                actor_id=actor.id,
                item_id=item.id,
                item_name=item.name,
                effect=str(spell.effect.value),
                target_id=params.target_id,
                consumed=use.consumed,
                is_scroll=use.is_scroll,
            )
        )
        return ActionOutcome(
            success=True,
            consumed=real_econ,
            notes=f"used {item.id}",
        )


__all__ = ["UseItemAction", "UseItemParams"]

"""PickupAction — забрать предмет из контейнера (этап O-8).

Контейнер сейчас — только CHEST (на этапе O-7 добавится corpse).
Семантика: free object interaction (1/ход), reach 5 ft. Если сундук
заперт — Forbidden. Если пуст / нужного item_id нет — Forbidden.

PickupAction отличается от InteractAction.OPEN тем, что не открывает
содержимое целиком, а берёт **конкретный** ItemStack по item_id +
optional qty. Это даёт UI выбор — игрок может взять не всё.

State chest хранит ``contents`` в сыром YAML-формате (canonical/legacy);
PickupAction перепарсивает через parse_loot, обновляет нужный стак,
сериализует обратно через dump_loot_entries.
"""

from __future__ import annotations

from typing import ClassVar

from dnd.application.dto.action import (
    ActionAvailability,
    ActionEconomyCost,
    ActionOutcome,
    ActionParams,
    Allowed,
    Forbidden,
    ForbiddenReason,
)
from dnd.application.dto.engine_event import ItemPickedUp
from dnd.application.engine.turn_context import TurnContext
from dnd.application.inventory.loot_helpers import (
    dump_loot_entries,
    parse_loot,
)
from dnd.application.ports.item_repository import ItemRepository
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ids import ActionId, ObjectId
from dnd.domain.values.item import ItemId
from dnd.domain.values.object_kind import ObjectKind

# Используем same constants как InteractAction для согласованности.
_REACH_FT = 5


class PickupParams(ActionParams):
    """Параметры PickupAction.

    ``qty=None`` — взять весь стак (для UI «забрать всё одной кнопкой»);
    ``qty>=1`` — взять указанное количество (если в стаке меньше —
    берём сколько есть, не Forbidden).
    """

    target_object_id: ObjectId
    item_id: ItemId
    qty: int | None = None


class PickupAction:
    """Забрать предмет из контейнера в инвентарь актора."""

    id_value: ClassVar[ActionId] = ActionId("pickup")
    name_key_value: ClassVar[str] = "action.pickup"
    economy_cost_value: ClassVar[ActionEconomyCost] = ActionEconomyCost.FREE

    def __init__(self, item_repository: ItemRepository) -> None:
        self._items = item_repository

    @property
    def id(self) -> ActionId:
        return self.id_value

    @property
    def name_key(self) -> str:
        return self.name_key_value

    @property
    def economy_cost(self) -> ActionEconomyCost:
        return self.economy_cost_value

    def can_perform(self, actor: Creature, ctx: TurnContext) -> ActionAvailability:
        # Pickup тратит free object interaction (1/ход) — как Interact.
        # Если уже потрачено в этом ходу, Forbidden.
        if not ctx.can_use_object_interaction():
            return Forbidden(reason=ForbiddenReason.NO_ECONOMY_LEFT)
        return Allowed()

    def can_perform_against(
        self,
        actor: Creature,
        params: PickupParams,
        ctx: TurnContext,
    ) -> ActionAvailability:
        base = self.can_perform(actor, ctx)
        if isinstance(base, Forbidden):
            return base
        bf = ctx.battlefield
        try:
            obj = bf.object_at(params.target_object_id)
        except KeyError:
            return Forbidden(reason=ForbiddenReason.NO_VALID_TARGETS)
        actor_pos = bf.position_of(actor.id)
        if actor_pos.distance_to_feet(obj.pos) > _REACH_FT:
            return Forbidden(reason=ForbiddenReason.OUT_OF_RANGE)
        # Лутать можно из сундука (O) и из трупа (Q-8): у обоих
        # open/locked/contents-семантика и они открываются Interact'ом.
        if obj.kind not in (ObjectKind.CHEST, ObjectKind.CORPSE):
            return Forbidden(
                reason=ForbiddenReason.CUSTOM,
                details=f"cannot pickup from {obj.kind.value}",
            )
        if obj.state.get("locked"):
            return Forbidden(
                reason=ForbiddenReason.CUSTOM,
                details=f"{obj.kind.value} is locked",
            )
        # Audit MAJOR-1: pickup из ЗАКРЫТОГО сундука был разрешён,
        # хотя по правилам сначала нужно его открыть (InteractAction.OPEN).
        # Иначе семантика «open» теряется — игрок забирает лут без
        # открытия. Открытие — отдельный free interaction (тоже 1/ход).
        if not obj.state.get("open"):
            return Forbidden(
                reason=ForbiddenReason.CUSTOM,
                details="chest is closed (Interact-open first)",
            )
        # Парсим contents и проверяем наличие item_id.
        loot = parse_loot(obj.state.get("contents"), self._items)
        if not any(s.item.id == params.item_id for s in loot):
            return Forbidden(
                reason=ForbiddenReason.NO_VALID_TARGETS,
                details=f"no {params.item_id} in chest",
            )
        return Allowed()

    def execute(
        self,
        actor: Creature,
        params: ActionParams,
        ctx: TurnContext,
    ) -> ActionOutcome:
        if not isinstance(params, PickupParams):
            raise TypeError(f"PickupAction expects PickupParams, got {type(params).__name__}")
        bf = ctx.battlefield
        # ВАЖНО: не списываем free object interaction до того, как
        # убедимся, что pickup реально случится. Audit MAJOR-3 фикс:
        # иначе игрок терял free action из-за полного рюкзака и не
        # мог даже открыть дверь в этом ходу.
        obj = bf.object_at(params.target_object_id)

        loot = list(parse_loot(obj.state.get("contents"), self._items))
        # Найти стак с нужным item_id (parse_loot уже стакует stackable).
        idx = next(
            (i for i, s in enumerate(loot) if s.item.id == params.item_id),
            None,
        )
        assert idx is not None, "can_perform_against должен был проверить наличие"
        stack = loot[idx]
        # Сколько берём: qty=None → весь стак; иначе min(qty, stack.qty).
        take_qty = stack.qty if params.qty is None else min(params.qty, stack.qty)
        # Кладём в инвентарь актора.
        overflow = actor.inventory.add(stack.item, qty=take_qty)
        actually_picked = take_qty - overflow
        if actually_picked <= 0:
            # Не влезло ни одного — Forbidden по факту (encumbrance).
            # Free interaction НЕ списан — игрок видит fail и может в
            # тот же ход открыть дверь / сменить оружие.
            return ActionOutcome(
                success=False,
                consumed=ActionEconomyCost.FREE,
                events_published=(),
                notes=f"pickup failed: inventory full ({stack.item.id})",
            )
        # Снимаем со стака то, что реально подняли. Стак с qty==0 удаляем.
        if stack.item.stackable:
            new_qty = stack.qty - actually_picked
            if new_qty <= 0:
                loot.pop(idx)
            else:
                loot[idx] = type(stack)(stack.item, qty=new_qty)
        else:
            # non-stackable: всегда qty=1, забираем стак целиком.
            loot.pop(idx)
        obj.state["contents"] = dump_loot_entries(tuple(loot))
        # Только теперь — после реального движения предмета — списываем
        # free interaction.
        ctx.use_object_interaction()

        ctx.event_bus.publish(
            ItemPickedUp(
                actor_id=actor.id,
                item_id=stack.item.id,
                item_name=stack.item.name,
                qty=actually_picked,
                source=f"chest:{obj.id}",
            )
        )
        notes = f"pickup: {actually_picked}× {stack.item.id} from {obj.id}"
        if overflow > 0:
            notes += f" (overflow {overflow} — inventory full)"
        return ActionOutcome(
            success=True,
            consumed=ActionEconomyCost.FREE,
            events_published=("inventory.item_picked_up",),
            notes=notes,
        )


__all__ = ["PickupAction", "PickupParams"]

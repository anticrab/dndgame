"""Чистое ядро резолва и применения эффекта заклинания (U1-3).

Вынесено из ``CastSpellAction``: содержит резолв целей (SELF/SINGLE/MULTI/AREA) +
вызов хендлера эффекта. **Без** ``consume_spell_slot``/``ctx.spend`` и **без**
публикации ``SpellCast`` — этим управляют вызывающие действия
(``CastSpellAction`` тратит слот/экономику + публикует событие; ``UseItemAction``
тратит экономику предмета + публикует ``ItemUsed``, **слот не трогает**).

Тот же ``resolve_and_apply_spell`` исполняет и заклинание волшебника, и эффект
свитка/зелья — единый slotless-каст эффект-пакета (см. `project_unified_effects`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.domain.values.ids import FeatureId
from dnd.domain.values.spell import OriginMode, TargetKind

if TYPE_CHECKING:
    from dnd.application.engine.spells.area import AreaShapeRegistry
    from dnd.application.engine.spells.effect_handler import SpellEffectRegistry
    from dnd.application.engine.turn_context import TurnContext
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.direction import Direction
    from dnd.domain.values.ids import CreatureId
    from dnd.domain.values.spell import Spell
    from dnd.domain.values.spell_power import SpellPower
    from dnd.domain.values.square import Square


def resolve_and_apply_spell(
    caster: Creature,
    spell: Spell,
    *,
    ctx: TurnContext,
    power: SpellPower,
    target_id: CreatureId | None,
    target_ids: tuple[CreatureId, ...],
    target_point: Square | None,
    direction: Direction | None,
    effect_registry: SpellEffectRegistry,
    area_registry: AreaShapeRegistry,
) -> None:
    """Применить эффект-пакет ``spell`` от ``caster`` к выбранным целям.

    Slotless и без правок экономики — только резолв целей и вызов хендлера.
    Валидность параметров (range/known/slot/economy) — забота вызывающего.
    """
    targets = _resolve_targets(
        spell,
        caster,
        ctx=ctx,
        area_registry=area_registry,
        target_id=target_id,
        target_ids=target_ids,
        target_point=target_point,
        direction=direction,
    )
    effect_registry.get(spell.effect).apply(caster, targets, spell, ctx, power)


def _resolve_targets(
    spell: Spell,
    caster: Creature,
    *,
    ctx: TurnContext,
    area_registry: AreaShapeRegistry,
    target_id: CreatureId | None,
    target_ids: tuple[CreatureId, ...],
    target_point: Square | None,
    direction: Direction | None,
) -> tuple[Creature, ...]:
    spec = spell.targeting
    kind = spec.kind
    if kind is TargetKind.SELF:
        return (caster,)
    if kind is TargetKind.SINGLE:
        assert target_id is not None
        return (ctx.participants[target_id],)
    if kind is TargetKind.AREA:
        assert spec.shape is not None
        origin = (
            ctx.battlefield.position_of(caster.id)
            if spec.origin is OriginMode.FROM_CASTER
            else target_point
        )
        assert origin is not None
        squares = area_registry.get(spec.shape).squares(origin, direction, spec, ctx.battlefield)
        # Все живые существа в задетых клетках (friendly fire включён).
        in_area = [
            (cid, cr)
            for cid, cr in ctx.participants.items()
            if cr.is_alive and ctx.battlefield.position_of(cid) in squares
        ]
        # T4: Школа Воплощения (Sculpt Spells) — союзники кастера авто-исключаются
        # из его AoE (PHB-2024; упрощение «все союзники невредимы»).
        if FeatureId("subclass_evoker") in caster.features:
            caster_faction = ctx.factions.get(caster.id)
            in_area = [(cid, cr) for cid, cr in in_area if ctx.factions.get(cid) != caster_faction]
        return tuple(cr for _cid, cr in in_area)
    # MULTI (P2b): мультимножество выборов — дубли = повторные «попадания».
    assert kind is TargetKind.MULTI
    return tuple(ctx.participants[cid] for cid in target_ids)


__all__ = ["resolve_and_apply_spell"]

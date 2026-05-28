"""Валидация таргетинга заклинания/эффект-пакета (U-post-review #1).

Общая для :class:`CastSpellAction` и :class:`UseItemAction`: оба используют
одни и те же правила «можно ли применить эффект ``spell`` к выбранным целям» —
range, liveness (дамаг по трупу нельзя; heal/buff по dying-ally можно), форма
зоны, лимиты MULTI. До выноса блок был продублирован 1-в-1, любая правка
(LoS, friendly-fire по данным, новый ``OriginMode``) требовала синхронной
правки в двух местах.

Контракт: возвращает ``Forbidden`` с конкретной причиной или ``None``
(валидно). Вызывающий сам строит ``Allowed()``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.application.dto.action import Forbidden, ForbiddenReason
from dnd.domain.values.spell import OriginMode, SpellEffect, TargetKind

if TYPE_CHECKING:
    from dnd.application.engine.spells.area import AreaShapeRegistry
    from dnd.application.engine.turn_context import TurnContext
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.direction import Direction
    from dnd.domain.values.ids import CreatureId
    from dnd.domain.values.spell import Spell
    from dnd.domain.values.square import Square


def validate_spell_targeting(
    actor: Creature,
    spell: Spell,
    ctx: TurnContext,
    *,
    target_id: CreatureId | None,
    target_ids: tuple[CreatureId, ...],
    target_point: Square | None,
    direction: Direction | None,
    areas: AreaShapeRegistry,
) -> Forbidden | None:
    """Проверить, что выбранные параметры таргетинга валидны для ``spell``.

    Возвращает ``Forbidden(...)`` с причиной или ``None`` при успехе.

    Покрывает:

    * **SINGLE** — есть target_id, цель в participants, liveness (offensive
      только по живой; heal/buff по живой ИЛИ dying), дистанция ≤ range.
    * **AREA** — shape известен реестру форм; ``AT_POINT`` требует
      target_point в range; ``FROM_CASTER`` требует direction.
    * **MULTI** — непустой target_ids, не больше max_targets, без повторов
      если ``allow_repeat_target=False``; каждая цель — в participants и
      в range; liveness как у SINGLE.
    * **SELF** — без дополнительных проверок (всегда валиден).
    """
    spec = spell.targeting
    kind = spec.kind
    if kind is TargetKind.SELF:
        return None
    offensive = spell.effect in (SpellEffect.ATTACK, SpellEffect.SAVE, SpellEffect.AUTO)
    if kind is TargetKind.SINGLE:
        if target_id is None or target_id not in ctx.participants:
            return Forbidden(reason=ForbiddenReason.NO_VALID_TARGETS)
        target = ctx.participants[target_id]
        liveness = _check_liveness(target, offensive=offensive)
        if liveness is not None:
            return liveness
        actor_pos = ctx.battlefield.position_of(actor.id)
        target_pos = ctx.battlefield.position_of(target_id)
        if actor_pos.distance_to_feet(target_pos) > spell.range_ft:
            return Forbidden(reason=ForbiddenReason.OUT_OF_RANGE)
        return None
    if kind is TargetKind.AREA:
        shape = spec.shape
        if shape is None or shape not in areas:
            return Forbidden(
                reason=ForbiddenReason.CUSTOM,
                details=f"area shape not supported: {shape}",
            )
        if spec.origin is OriginMode.AT_POINT:
            if target_point is None:
                return Forbidden(reason=ForbiddenReason.NO_VALID_TARGETS)
            actor_pos = ctx.battlefield.position_of(actor.id)
            if actor_pos.distance_to_feet(target_point) > spell.range_ft:
                return Forbidden(reason=ForbiddenReason.OUT_OF_RANGE)
        elif direction is None:  # FROM_CASTER требует направления
            return Forbidden(reason=ForbiddenReason.NO_VALID_TARGETS)
        return None
    # MULTI
    assert kind is TargetKind.MULTI
    if not target_ids:
        return Forbidden(reason=ForbiddenReason.NO_VALID_TARGETS)
    if len(target_ids) > spec.max_targets:
        return Forbidden(
            reason=ForbiddenReason.CUSTOM,
            details=f"too many targets (max {spec.max_targets})",
        )
    unique = set(target_ids)
    if not spec.allow_repeat_target and len(unique) != len(target_ids):
        return Forbidden(
            reason=ForbiddenReason.CUSTOM,
            details="repeat targets not allowed",
        )
    actor_pos = ctx.battlefield.position_of(actor.id)
    for cid in unique:
        if cid not in ctx.participants:
            return Forbidden(reason=ForbiddenReason.NO_VALID_TARGETS)
        target = ctx.participants[cid]
        liveness = _check_liveness(target, offensive=offensive)
        if liveness is not None:
            return liveness
        if actor_pos.distance_to_feet(ctx.battlefield.position_of(cid)) > spell.range_ft:
            return Forbidden(reason=ForbiddenReason.OUT_OF_RANGE)
    return None


def _check_liveness(target: Creature, *, offensive: bool) -> Forbidden | None:
    """Liveness-guard цели (audit MAJOR-2).

    Урон-заклинания (ATTACK/SAVE/AUTO) — только по живой цели (нельзя бить
    труп). Heal/buff — по живой ИЛИ умирающей (dying), но не по окончательно
    мёртвой.
    """
    if offensive:
        if not target.is_alive:
            return Forbidden(reason=ForbiddenReason.TARGET_DOWN)
        return None
    if not target.is_alive and not (
        target.death_saves is not None and not target.death_saves.is_dead
    ):
        return Forbidden(reason=ForbiddenReason.TARGET_DOWN)
    return None


__all__ = ["validate_spell_targeting"]

"""Аудит-смок X0: бафф концентрации истекает по временно́му потолку (X0-7).

Сценарий: бафф с дедлайном через 10 раундов (Bless — концентрация до 1 минуты);
часы двигаются по одному раунду через ``RoundEnded``; на 10-м раунде публикуется
``BuffExpired`` и модификатор снят — даже без срыва концентрации. Так временной
потолок концентрации работает поверх событийных триггеров (закрытие долга T2).
"""

from __future__ import annotations

from dnd.application.dto.engine_event import BuffApplied, BuffExpired, RoundEnded
from dnd.application.engine.effects.ongoing_effect_tracker import OngoingEffectTracker
from dnd.composition import build_scripted_runtime_services
from dnd.domain.entities.game_clock import GameClock
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.modifiers import (
    Modifier,
    ModifierSourceKind,
    ModifierTargetKind,
    NumericBonusEffect,
)


def test_concentration_buff_expires_by_time_cap() -> None:
    services, bus, _ = build_scripted_runtime_services(rolls=[])
    mods = services.modifier_applier
    clock = GameClock()
    tracker = OngoingEffectTracker(
        {},
        bus,
        dice_roller=services.dice_roller,
        modifier_applier=mods,
        condition_service=services.condition_service,
        clock=clock,
    )
    tracker.subscribe()
    owner = CreatureId("hero")
    src = f"concentration:{CreatureId('caster')}"
    mods.add(
        Modifier(
            source_id=src,
            source_kind=ModifierSourceKind.SPELL,
            target_kind=ModifierTargetKind.ATTACK_ROLL,
            effect=NumericBonusEffect(value=1),
            owner_id=owner,
            stack_key=src,
        )
    )
    expired: list[BuffExpired] = []
    bus.subscribe(BuffExpired, expired.append)

    # Bless: потолок концентрации 1 минута = 10 раундов.
    bus.publish(BuffApplied(owner_id=owner, source_id=src, expires_at_round=10))

    for r in range(1, 10):  # раунды 1..9 — бафф ещё держится
        clock.advance(1)
        bus.publish(RoundEnded(round_number=r))
        assert not expired
        assert mods.collect(owner_id=owner, target_kind=ModifierTargetKind.ATTACK_ROLL)

    clock.advance(1)  # now_round = 10 → дедлайн достигнут
    bus.publish(RoundEnded(round_number=10))
    assert expired and expired[-1].source_id == src
    assert mods.collect(owner_id=owner, target_kind=ModifierTargetKind.ATTACK_ROLL) == []

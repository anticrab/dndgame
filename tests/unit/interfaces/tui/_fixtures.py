"""Маленькие фабрики для TUI-юнит-тестов.

Только то, что переиспользуется. Чтобы не тащить за собой огромные
build_*_dependencies, собираем `TurnContext` через :func:`build_minimal_ctx`
с минимальным набором сервисов.
"""

from __future__ import annotations

from dnd.application.engine.turn_context import TurnContext
from dnd.composition import build_default_runtime_services
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature


def build_minimal_ctx(*, actor: Creature, battlefield: Battlefield) -> TurnContext:
    """``TurnContext`` для тестов виджетов — без реального боя.

    Сервисы — default (RealRNG, InMemoryEventBus); их использовать не
    обязательно, тестам важны только actor / battlefield / счётчики.
    """
    services = build_default_runtime_services()
    deps = services.with_battlefield(battlefield)
    return TurnContext(
        actor_id=actor.id,
        battlefield=deps.battlefield,
        dice_roller=deps.dice_roller,
        modifier_applier=deps.modifier_applier,
        condition_service=deps.condition_service,
        event_bus=deps.event_bus,
        rng=deps.rng,
        participants={actor.id: actor},
        movement_remaining_ft=actor.speed_ft,
    )

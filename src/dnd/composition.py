"""Composition root — сборка зависимостей движка.

Один публичный helper :func:`build_default_dependencies` собирает все
сервисы боя в готовый ``EncounterDependencies``. Это место, где
пересекаются «слои» (domain ← application ← infrastructure); никакой
бизнес-логики тут нет — только wiring.

Для тестов/смок-сценариев есть :func:`build_scripted_dependencies` —
принимает фиксированную последовательность d20-бросков, чтобы бой
был детерминированным.
"""

from __future__ import annotations

from collections.abc import Sequence

from dnd.application.engine.condition_service import ConditionService
from dnd.application.engine.dice_roller import ComputerDiceRoller
from dnd.application.engine.encounter import EncounterDependencies
from dnd.application.engine.modifier_applier import ModifierApplier, ModifierBag
from dnd.application.ports.event_bus import EventBus
from dnd.domain.conditions.builtin import register_default_conditions
from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.ports.rng import RNG
from dnd.infrastructure.events.in_memory_event_bus import InMemoryEventBus
from dnd.infrastructure.rng.real_rng import RealRNG
from dnd.infrastructure.rng.scripted_rng import ScriptedRNG


def build_default_dependencies(
    *,
    battlefield: Battlefield,
    rng: RNG | None = None,
    event_bus: EventBus | None = None,
) -> EncounterDependencies:
    """Сборка зависимостей для реального боя.

    * ``rng`` по умолчанию — ``RealRNG`` (system random).
    * ``event_bus`` — ``InMemoryEventBus`` (FIFO, синхронный).
    * ``ConditionService`` — с зарегистрированными базовыми условиями.
    * ``ModifierApplier`` — с пустым ``ModifierBag``.
    """
    rng_used: RNG = rng if rng is not None else RealRNG()
    bus_used: EventBus = event_bus if event_bus is not None else InMemoryEventBus()
    registry = ConditionRegistry()
    register_default_conditions(registry)
    return EncounterDependencies(
        battlefield=battlefield,
        dice_roller=ComputerDiceRoller(rng=rng_used, event_bus=bus_used),
        modifier_applier=ModifierApplier(ModifierBag()),
        condition_service=ConditionService(registry),
        event_bus=bus_used,
        rng=rng_used,
    )


def build_scripted_dependencies(
    *,
    battlefield: Battlefield,
    rolls: Sequence[int],
) -> tuple[EncounterDependencies, InMemoryEventBus, ScriptedRNG]:
    """Сборка зависимостей для тестового / smoke-сценария.

    Возвращает кортеж (deps, bus, rng) — bus и rng доступны вызывающему,
    чтобы он мог подписываться на события и доскриптить броски.
    """
    bus = InMemoryEventBus()
    rng = ScriptedRNG(list(rolls))
    deps = build_default_dependencies(
        battlefield=battlefield, rng=rng, event_bus=bus
    )
    return deps, bus, rng


__all__ = [
    "build_default_dependencies",
    "build_scripted_dependencies",
]

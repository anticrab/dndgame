"""Composition root — сборка зависимостей движка.

Два уровня зависимостей (аудит 15 CL-A001):

* :class:`EncounterRuntimeServices` — «инфраструктурные» сервисы,
  не зависящие от карты боя: DiceRoller / ModifierApplier /
  ConditionService / EventBus / RNG. Создаётся один раз на сессию;
  переиспользуется между Encounter'ами.
* :class:`EncounterDependencies` — RuntimeServices + ``Battlefield``
  конкретного боя. Собирается, когда карта известна (например, в
  ``build_encounter_from_scenario``).

Публичные helper'ы:

* :func:`build_default_runtime_services` — production (RealRNG,
  InMemoryEventBus).
* :func:`build_scripted_runtime_services` — тесты (ScriptedRNG,
  фиксированные броски).
* :func:`build_default_dependencies` / :func:`build_scripted_dependencies`
  — обёртки для случаев, когда карта известна заранее (старые тесты;
  pre-scenario сборка).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from dnd.application.engine.condition_service import ConditionService
from dnd.application.engine.dice_roller import ComputerDiceRoller
from dnd.application.engine.encounter import EncounterDependencies
from dnd.application.engine.modifier_applier import ModifierApplier, ModifierBag
from dnd.application.ports.dice_roller import DiceRoller
from dnd.application.ports.event_bus import EventBus
from dnd.domain.conditions.builtin import register_default_conditions
from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.ports.rng import RNG
from dnd.infrastructure.events.in_memory_event_bus import InMemoryEventBus
from dnd.infrastructure.rng.real_rng import RealRNG
from dnd.infrastructure.rng.scripted_rng import ScriptedRNG


@dataclass(slots=True)
class EncounterRuntimeServices:
    """Сервисы боя без привязки к конкретной карте.

    Аудит 15 CL-A001: разделено с ``EncounterDependencies``, чтобы
    composition root не передавал placeholder Battlefield и потом
    его не выбрасывал.
    """

    dice_roller: DiceRoller
    modifier_applier: ModifierApplier
    condition_service: ConditionService
    event_bus: EventBus
    rng: RNG

    def with_battlefield(self, battlefield: Battlefield) -> EncounterDependencies:
        """Дополнить услуги конкретной картой → готовый
        ``EncounterDependencies`` для ``Encounter``."""
        return EncounterDependencies(
            battlefield=battlefield,
            dice_roller=self.dice_roller,
            modifier_applier=self.modifier_applier,
            condition_service=self.condition_service,
            event_bus=self.event_bus,
            rng=self.rng,
        )


def build_default_runtime_services(
    *,
    rng: RNG | None = None,
    event_bus: EventBus | None = None,
) -> EncounterRuntimeServices:
    """Production-сервисы (RealRNG, InMemoryEventBus, базовые conditions)."""
    rng_used: RNG = rng if rng is not None else RealRNG()
    bus_used: EventBus = event_bus if event_bus is not None else InMemoryEventBus()
    registry = ConditionRegistry()
    register_default_conditions(registry)
    return EncounterRuntimeServices(
        dice_roller=ComputerDiceRoller(rng=rng_used, event_bus=bus_used),
        modifier_applier=ModifierApplier(ModifierBag()),
        condition_service=ConditionService(registry),
        event_bus=bus_used,
        rng=rng_used,
    )


def build_scripted_runtime_services(
    *,
    rolls: Sequence[int],
) -> tuple[EncounterRuntimeServices, InMemoryEventBus, ScriptedRNG]:
    """Сервисы для тестов: ScriptedRNG + InMemoryEventBus.

    Возвращает кортеж (services, bus, rng) — bus и rng доступны
    вызывающему для подписки и доскрипта.
    """
    bus = InMemoryEventBus()
    rng = ScriptedRNG(list(rolls))
    services = build_default_runtime_services(rng=rng, event_bus=bus)
    return services, bus, rng


# ---- legacy/удобство: сразу собрать EncounterDependencies ------------


def build_default_dependencies(
    *,
    battlefield: Battlefield,
    rng: RNG | None = None,
    event_bus: EventBus | None = None,
) -> EncounterDependencies:
    """Сборка ``EncounterDependencies`` сразу с битфилдом.

    Подходит для случаев, когда карта известна до создания services
    (старые тесты, ручные сценарии). Если карта строится сценарием —
    используйте :func:`build_default_runtime_services` +
    ``services.with_battlefield(bf)``.
    """
    return build_default_runtime_services(rng=rng, event_bus=event_bus).with_battlefield(
        battlefield
    )


def build_scripted_dependencies(
    *,
    battlefield: Battlefield,
    rolls: Sequence[int],
) -> tuple[EncounterDependencies, InMemoryEventBus, ScriptedRNG]:
    """Сборка ``EncounterDependencies`` для тестов с конкретной картой."""
    services, bus, rng = build_scripted_runtime_services(rolls=rolls)
    return services.with_battlefield(battlefield), bus, rng


__all__ = [
    "EncounterRuntimeServices",
    "build_default_dependencies",
    "build_default_runtime_services",
    "build_scripted_dependencies",
    "build_scripted_runtime_services",
]

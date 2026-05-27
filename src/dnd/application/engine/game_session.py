"""GameSession (X0) — рантайм кампании поверх боёв.

Держит партию + общие игровые часы + сервисы. Бой (``Encounter``) создаётся из
сессии и делит её часы (через ``EncounterRuntimeServices.with_battlefield`` →
``EncounterDependencies.clock``): по ``EncounterEnded`` управление возвращается в
сессию, часы и активные эффекты сохраняются. Часы двигает только ``Encounter`` на
границе раунда — сессия лишь владеет общим объектом (двойного advance нет).

Режим исследования (переходы локаций, отдых, обыск двигают часы по стоимости
действий) — этап X. Сейчас сессия оборачивает бой и фиксирует, что время и
длительности эффектов едины поверх отдельных боёв.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from dnd.composition import EncounterRuntimeServices
    from dnd.domain.entities.creature import Creature
    from dnd.domain.entities.game_clock import GameClock
    from dnd.domain.values.ids import CreatureId


class GameSession:
    """Партия + общие часы + сервисы поверх отдельных боёв."""

    def __init__(
        self,
        *,
        party: Mapping[CreatureId, Creature],
        services: EncounterRuntimeServices,
    ) -> None:
        self.party = dict(party)
        self._services = services

    @property
    def services(self) -> EncounterRuntimeServices:
        return self._services

    @property
    def clock(self) -> GameClock:
        """Общие игровые часы сессии — тот же объект, что получает каждый
        ``Encounter`` (через ``services.with_battlefield``) и трекер эффектов."""
        return self._services.clock


__all__ = ["GameSession"]

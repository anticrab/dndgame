"""ScriptedIntentProvider — тестовый источник намерений.

Принимает в конструкторе очередь intent'ов и отдаёт их по одному.
По исчерпании очереди возвращает :class:`EndTurnIntent`, чтобы
ход безопасно закрывался (помогает в смешанных сценариях, где
тест задаёт «два действия за ход, затем end»).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from dnd.application.dto.player_intent import EndTurnIntent, PlayerIntent
from dnd.application.engine.encounter import Encounter
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.entities.creature import Creature


class ScriptedIntentProvider:
    """Скриптованная очередь намерений для тестов / детерминированных
    смок-сценариев."""

    def __init__(self, intents: Iterable[PlayerIntent]) -> None:
        self._queue: deque[PlayerIntent] = deque(intents)

    def next_intent(
        self,
        actor: Creature,
        ctx: TurnContext,
        encounter: Encounter,
    ) -> PlayerIntent:
        # Аргументы не используются — провайдер не знает контекста,
        # вызывающий тест собрал очередь заранее.
        del actor, ctx, encounter
        if not self._queue:
            return EndTurnIntent()
        return self._queue.popleft()


__all__ = ["ScriptedIntentProvider"]

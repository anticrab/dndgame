"""PlayerIntentProvider — Port для источника намерений игрока.

Реализации:

* :class:`~dnd.interfaces.cli.scripted_provider.ScriptedIntentProvider`
  — заскриптованная очередь для тестов.
* (планируется) :class:`ConsoleIntentProvider` — questionary-prompt'ы.
* (планируется) ``HotseatProvider`` / ``LiveMasterProvider`` —
  killer-feature пост-MVP.

Контракт:

* **stateless с точки зрения GameRunner** — провайдер сам решает,
  как хранить state (очередь, prompt, AI).
* ``next_intent`` вызывается **многократно за один ход**: пока
  не вернётся ``EndTurnIntent``.
* Провайдер видит ``Creature`` actor'а, ``TurnContext`` (с
  оставшейся экономикой), ``Encounter`` (для лукапа целей и
  фракций), и список уже опубликованных событий не получает —
  это задача UI-renderer'а.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from dnd.application.dto.player_intent import PlayerIntent
    from dnd.application.engine.encounter import Encounter
    from dnd.application.engine.turn_context import TurnContext
    from dnd.domain.entities.creature import Creature


@runtime_checkable
class PlayerIntentProvider(Protocol):
    """Источник намерений игрока на ход."""

    def next_intent(
        self,
        actor: Creature,
        ctx: TurnContext,
        encounter: Encounter,
    ) -> PlayerIntent: ...


__all__ = ["PlayerIntentProvider"]

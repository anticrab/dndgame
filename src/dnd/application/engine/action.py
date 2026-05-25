"""Action Protocol — базовый контракт действий движка.

См. ``docs/ACTIONS.md`` §2. Конкретные действия живут в модулях
``application/engine/actions/*.py`` (этапы E2…E6) и реализуют этот
Protocol.

Контракт:

* ``can_perform`` — pure-функция, без побочных эффектов, возвращает
  ``ActionAvailability`` (Allowed | Forbidden);
* ``execute`` — выполняет действие (публикует события, мутирует
  ``ctx``), возвращает ``ActionOutcome``;
* контракт «execute не валидирует повторно то, что проверил can_perform»
  — вызывающий обязан вызвать can_perform до execute.

Protocol намеренно не-generic: разные действия принимают разные
``ActionParams``-потомки, и Python без runtime-проверок не выиграет
от ``Action[P]`` (mypy подскажет на use-site через ``cast``/конкретные
типы). На уровне реестра действий это даёт единый тип
``dict[ActionId, Action]``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from dnd.application.dto.action import (
    ActionAvailability,
    ActionEconomyCost,
    ActionOutcome,
    ActionParams,
)
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ids import ActionId


@runtime_checkable
class Action(Protocol):
    """Контракт действия. Все конкретные действия реализуют его.

    Поля экземпляра (id, name_key, economy_cost) описывают «что это за
    действие» и не зависят от actor/ctx. Они доступны до ``can_perform``
    — UI/AI используют их для меню действий.
    """

    @property
    def id(self) -> ActionId: ...

    @property
    def name_key(self) -> str: ...

    @property
    def economy_cost(self) -> ActionEconomyCost: ...

    def can_perform(
        self, actor: Creature, ctx: TurnContext
    ) -> ActionAvailability: ...

    def execute(
        self,
        actor: Creature,
        params: ActionParams,
        ctx: TurnContext,
    ) -> ActionOutcome: ...


__all__ = ["Action"]

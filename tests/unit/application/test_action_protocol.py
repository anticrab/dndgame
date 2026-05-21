"""Тест-фиксация контракта Action Protocol.

Action — runtime_checkable Protocol. Конформность конкретного класса
проверяется через ``isinstance`` (для smoke) и через mypy (для строгой
типизации). Здесь — smoke: stub-реализация удовлетворяет Protocol.

Цель — не дать рефакторингу Protocol тихо потерять метод/атрибут.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from dnd.application.dto.action import (
    ActionEconomyCost,
    ActionOutcome,
    ActionParams,
    Allowed,
)
from dnd.application.dto.ids import ActionId
from dnd.application.engine.action import Action
from dnd.application.engine.turn_context import TurnContext


class _StubAction:
    """Минимальная конформная реализация Action для проверки Protocol."""

    @property
    def id(self) -> ActionId:
        return ActionId("stub")

    @property
    def name_key(self) -> str:
        return "action.stub"

    @property
    def economy_cost(self) -> ActionEconomyCost:
        return ActionEconomyCost.ACTION

    def can_perform(self, actor: object, ctx: TurnContext) -> Allowed:  # type: ignore[override]
        return Allowed()

    def execute(
        self, actor: object, params: ActionParams, ctx: TurnContext
    ) -> ActionOutcome:
        return ActionOutcome(success=True, consumed=ActionEconomyCost.ACTION)


def test_stub_is_action_protocol_conformant() -> None:
    """Smoke: класс с правильным набором атрибутов признаётся Action."""
    stub = _StubAction()
    assert isinstance(stub, Action)


def test_action_protocol_has_required_attributes() -> None:
    """Не-конформный класс не должен проходить isinstance(Action)."""

    class NotAnAction:
        pass

    assert not isinstance(NotAnAction(), Action)


def test_stub_can_perform_returns_allowed() -> None:
    stub = _StubAction()
    av = stub.can_perform(actor=MagicMock(), ctx=MagicMock())
    assert isinstance(av, Allowed)


def test_stub_execute_returns_outcome() -> None:
    stub = _StubAction()
    outcome = stub.execute(
        actor=MagicMock(), params=ActionParams(), ctx=MagicMock()
    )
    assert outcome.success is True
    assert outcome.consumed is ActionEconomyCost.ACTION

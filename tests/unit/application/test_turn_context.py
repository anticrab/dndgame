"""Тесты TurnContext — экономика действий и счётчики хода/раунда.

Цели:

* счётчики корректно списываются через ``spend`` / ``spend_movement``;
* двойная трата ловится ValueError;
* ``can_spend`` не мутирует;
* ``start_new_round`` сбрасывает только reaction (а не action/bonus);
* движение проверяет кратность 5 и неотрицательность;
* object interaction — 1 в ход.

Зависимости (battlefield/dice/event_bus/etc.) — мокаем минимально: им
TurnContext-полей касается только сам факт «есть атрибут».
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dnd.application.dto.action import ActionEconomyCost
from dnd.application.dto.ids import CreatureId
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.entities.battlefield import Battlefield


def _make_ctx(movement_ft: int = 30) -> TurnContext:
    """Фабрика TurnContext с заглушками зависимостей."""
    return TurnContext(
        actor_id=CreatureId("aelar"),
        battlefield=Battlefield(5, 5),
        dice_roller=MagicMock(),
        modifier_applier=MagicMock(),
        condition_service=MagicMock(),
        event_bus=MagicMock(),
        rng=MagicMock(),
        movement_remaining_ft=movement_ft,
    )


# -- can_spend / spend ---------------------------------------------------


def test_initial_state_all_resources_free() -> None:
    ctx = _make_ctx()
    assert ctx.can_spend(ActionEconomyCost.ACTION) is True
    assert ctx.can_spend(ActionEconomyCost.BONUS_ACTION) is True
    assert ctx.can_spend(ActionEconomyCost.REACTION) is True
    assert ctx.can_use_object_interaction() is True


def test_spend_action_sets_flag() -> None:
    ctx = _make_ctx()
    ctx.spend(ActionEconomyCost.ACTION)
    assert ctx.action_used is True
    assert ctx.can_spend(ActionEconomyCost.ACTION) is False


def test_spend_bonus_and_action_independent() -> None:
    """Action и BonusAction — независимые ресурсы (PHB-2024 стр. 21)."""
    ctx = _make_ctx()
    ctx.spend(ActionEconomyCost.ACTION)
    assert ctx.can_spend(ActionEconomyCost.BONUS_ACTION) is True
    ctx.spend(ActionEconomyCost.BONUS_ACTION)
    assert ctx.action_used is True
    assert ctx.bonus_action_used is True


def test_double_spend_raises() -> None:
    ctx = _make_ctx()
    ctx.spend(ActionEconomyCost.ACTION)
    with pytest.raises(ValueError, match="no economy budget"):
        ctx.spend(ActionEconomyCost.ACTION)


def test_reaction_spend_tracked() -> None:
    ctx = _make_ctx()
    ctx.spend(ActionEconomyCost.REACTION)
    assert ctx.reaction_used is True
    with pytest.raises(ValueError):
        ctx.spend(ActionEconomyCost.REACTION)


def test_can_spend_is_pure() -> None:
    """can_spend не должен мутировать состояние."""
    ctx = _make_ctx()
    ctx.can_spend(ActionEconomyCost.ACTION)
    assert ctx.action_used is False


def test_spend_movement_does_nothing_in_spend() -> None:
    """spend(MOVEMENT) — no-op, для футов есть spend_movement."""
    ctx = _make_ctx(movement_ft=30)
    ctx.spend(ActionEconomyCost.MOVEMENT)
    assert ctx.movement_remaining_ft == 30


def test_spend_free_does_nothing() -> None:
    ctx = _make_ctx()
    ctx.spend(ActionEconomyCost.FREE)
    assert ctx.free_object_interaction_used is False


# -- movement ----------------------------------------------------------


def test_can_move_within_budget() -> None:
    ctx = _make_ctx(movement_ft=30)
    assert ctx.can_move(30) is True
    assert ctx.can_move(25) is True


def test_can_move_over_budget_is_false() -> None:
    ctx = _make_ctx(movement_ft=30)
    assert ctx.can_move(35) is False


def test_can_move_rejects_non_multiple_of_5() -> None:
    ctx = _make_ctx(movement_ft=30)
    with pytest.raises(ValueError, match="multiple of 5"):
        ctx.can_move(7)


def test_can_move_rejects_negative() -> None:
    ctx = _make_ctx(movement_ft=30)
    with pytest.raises(ValueError, match="non-negative"):
        ctx.can_move(-5)


def test_spend_movement_deducts() -> None:
    ctx = _make_ctx(movement_ft=30)
    ctx.spend_movement(15)
    assert ctx.movement_remaining_ft == 15


def test_spend_movement_over_budget_raises() -> None:
    ctx = _make_ctx(movement_ft=30)
    with pytest.raises(ValueError, match="not enough movement"):
        ctx.spend_movement(35)


def test_spend_movement_zero_is_noop() -> None:
    ctx = _make_ctx(movement_ft=30)
    ctx.spend_movement(0)
    assert ctx.movement_remaining_ft == 30


def test_spend_movement_can_drain_to_zero() -> None:
    ctx = _make_ctx(movement_ft=30)
    ctx.spend_movement(30)
    assert ctx.movement_remaining_ft == 0
    assert ctx.can_move(5) is False


# -- object interaction -----------------------------------------------


def test_object_interaction_once_per_turn() -> None:
    """PHB-2024 стр. 21: одно бесплатное взаимодействие в ход."""
    ctx = _make_ctx()
    ctx.use_object_interaction()
    assert ctx.can_use_object_interaction() is False
    with pytest.raises(ValueError, match="object interaction"):
        ctx.use_object_interaction()


# -- start_new_round --------------------------------------------------


def test_start_new_round_resets_reaction_only() -> None:
    """Реакция переживает между ходами в раунде; новый раунд её сбрасывает.

    Action / bonus_action / movement / object_interaction принадлежат
    конкретному ходу: они не «переносятся», но и не сбрасываются методом
    start_new_round — TurnContext пересоздаётся для каждого хода.
    """
    ctx = _make_ctx()
    ctx.spend(ActionEconomyCost.ACTION)
    ctx.spend(ActionEconomyCost.BONUS_ACTION)
    ctx.spend(ActionEconomyCost.REACTION)
    ctx.use_object_interaction()
    ctx.spend_movement(10)

    ctx.start_new_round()

    # reaction сбросилась
    assert ctx.reaction_used is False
    # round_number инкрементировался
    assert ctx.round_number == 2
    # action / bonus / movement / interaction — НЕ сбрасываются
    # (это задача создания нового TurnContext для следующего хода)
    assert ctx.action_used is True
    assert ctx.bonus_action_used is True
    assert ctx.free_object_interaction_used is True
    assert ctx.movement_remaining_ft == 20


# -- история (вспомогательная) ----------------------------------------


def test_history_default_empty_and_mutable() -> None:
    ctx = _make_ctx()
    assert ctx.history == []
    ctx.history.append("noop")
    assert ctx.history == ["noop"]

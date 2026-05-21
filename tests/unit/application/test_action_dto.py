"""Тесты DTO системы действий.

Покрывает:

* ``ActionEconomyCost`` — корректный enum.
* ``ActionParams`` / ``NoParams`` — frozen + forbid extra.
* ``ActionAvailability`` discriminated union — pydantic корректно
  выбирает Allowed/Forbidden по полю ``kind``.
* ``ActionOutcome`` — frozen + дефолты.
* ``ForbiddenReason`` — закрытый enum, CUSTOM с обязательным details
  (соглашение — проверяется на use-site, не схемой).
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from dnd.application.dto.action import (
    ActionAvailability,
    ActionEconomyCost,
    ActionOutcome,
    ActionParams,
    Allowed,
    Forbidden,
    ForbiddenReason,
    NoParams,
)

# -- ActionEconomyCost --------------------------------------------------


def test_economy_cost_values_match_book() -> None:
    """PHB-2024 стр. 21: action / bonus_action / reaction / movement / free."""
    assert ActionEconomyCost.ACTION.value == "action"
    assert ActionEconomyCost.BONUS_ACTION.value == "bonus_action"
    assert ActionEconomyCost.REACTION.value == "reaction"
    assert ActionEconomyCost.MOVEMENT.value == "movement"
    assert ActionEconomyCost.FREE.value == "free"


# -- ActionParams / NoParams --------------------------------------------


def test_no_params_is_frozen() -> None:
    p = NoParams()
    with pytest.raises(ValidationError):
        p.extra_field = 1  # type: ignore[attr-defined]


def test_no_params_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        NoParams(target_id="x")  # type: ignore[call-arg]


def test_action_params_subclass_inherits_frozen_and_forbid() -> None:
    """Потомки ActionParams должны автоматически быть frozen+forbid."""

    class MyParams(ActionParams):
        target_id: str

    p = MyParams(target_id="aelar")
    with pytest.raises(ValidationError):
        p.target_id = "other"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        MyParams(target_id="x", weapon_id="y")  # type: ignore[call-arg]


# -- ActionAvailability discriminated union ----------------------------


def test_allowed_default_kind() -> None:
    a = Allowed()
    assert a.kind == "allowed"


def test_forbidden_requires_reason() -> None:
    with pytest.raises(ValidationError):
        Forbidden()  # type: ignore[call-arg]


def test_forbidden_with_reason() -> None:
    f = Forbidden(reason=ForbiddenReason.OUT_OF_RANGE)
    assert f.reason is ForbiddenReason.OUT_OF_RANGE
    assert f.details == ""


def test_availability_discriminator_picks_allowed() -> None:
    """TypeAdapter должен по полю ``kind`` выбрать правильный класс."""
    adapter: TypeAdapter[ActionAvailability] = TypeAdapter(ActionAvailability)
    parsed = adapter.validate_python({"kind": "allowed"})
    assert isinstance(parsed, Allowed)


def test_availability_discriminator_picks_forbidden() -> None:
    adapter: TypeAdapter[ActionAvailability] = TypeAdapter(ActionAvailability)
    parsed = adapter.validate_python(
        {"kind": "forbidden", "reason": "no_economy_left"}
    )
    assert isinstance(parsed, Forbidden)
    assert parsed.reason is ForbiddenReason.NO_ECONOMY_LEFT


def test_availability_rejects_unknown_kind() -> None:
    adapter: TypeAdapter[ActionAvailability] = TypeAdapter(ActionAvailability)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "maybe"})


# -- ForbiddenReason ---------------------------------------------------


def test_forbidden_reason_is_closed_enum() -> None:
    """ForbiddenReason — закрытый список. Незнакомое значение → ошибка."""
    with pytest.raises(ValueError):
        ForbiddenReason("unknown_reason")


def test_custom_reason_allows_details() -> None:
    f = Forbidden(reason=ForbiddenReason.CUSTOM, details="rule from homebrew")
    assert f.details == "rule from homebrew"


# -- ActionOutcome -----------------------------------------------------


def test_outcome_minimal() -> None:
    o = ActionOutcome(success=True, consumed=ActionEconomyCost.ACTION)
    assert o.success is True
    assert o.consumed is ActionEconomyCost.ACTION
    assert o.events_published == ()
    assert o.movement_spent_ft == 0
    assert o.notes == ""


def test_outcome_with_events_tuple() -> None:
    o = ActionOutcome(
        success=True,
        consumed=ActionEconomyCost.ACTION,
        events_published=("attack.rolled", "damage.dealt"),
    )
    assert o.events_published == ("attack.rolled", "damage.dealt")


def test_outcome_is_frozen() -> None:
    o = ActionOutcome(success=True, consumed=ActionEconomyCost.ACTION)
    with pytest.raises(ValidationError):
        o.success = False  # type: ignore[misc]


def test_outcome_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        ActionOutcome(
            success=True,
            consumed=ActionEconomyCost.ACTION,
            unknown_field=1,  # type: ignore[call-arg]
        )

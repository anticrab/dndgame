"""DTO системы действий — экономика, params, availability, outcome.

См. ``docs/ACTIONS.md`` для общего описания контрактов.

Здесь:

* :class:`ActionEconomyCost` — что тратит действие (Action / BonusAction /
  Reaction / Movement / Free).
* :class:`ActionParams` — база для типизированных параметров конкретных
  действий (потомки — в модулях самих действий).
* :class:`ActionAvailability` — результат ``can_perform``: discriminated
  union (``Allowed`` / ``Forbidden``).
* :class:`ForbiddenReason` — закрытый enum причин отказа.
* :class:`ActionOutcome` — «расписка» о завершении действия.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ActionEconomyCost(StrEnum):
    """Бюджет, который действие тратит из хода/раунда.

    PHB-2024 стр. 21: смешанных стоимостей нет — действие тратит
    **ровно один** ресурс. Movement как «фоновый» бюджет — тоже
    отдельная категория: Move-действие тратит футы, не Action.
    """

    ACTION = "action"
    BONUS_ACTION = "bonus_action"
    REACTION = "reaction"
    MOVEMENT = "movement"
    FREE = "free"


class ActionParams(BaseModel):
    """База параметров действия. Конкретные действия наследуют и добавляют
    свои поля (target_id, weapon_id, path и т.п.).

    Frozen + forbid extra — параметры собираются на стороне UI/AI и
    передаются в ``Action.execute``; защищаемся от опечаток.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class NoParams(ActionParams):
    """Параметров нет (Dodge, Dash, Disengage и подобные stance-actions)."""


class ForbiddenReason(StrEnum):
    """Закрытый список причин отказа в действии.

    Закрытый — чтобы UI мог локализовать каждую причину явно; для редких
    кейсов есть ``CUSTOM`` с обязательным ``details``.
    """

    NO_ECONOMY_LEFT = "no_economy_left"
    INCAPACITATED = "incapacitated"
    NO_VALID_TARGETS = "no_valid_targets"
    OUT_OF_RANGE = "out_of_range"
    NO_LINE_OF_SIGHT = "no_line_of_sight"
    TARGET_HAS_TOTAL_COVER = "target_has_total_cover"
    NOT_ENOUGH_MOVEMENT = "not_enough_movement"
    CONDITION_BLOCKS_ACTION = "condition_blocks_action"
    CUSTOM = "custom"


class Allowed(BaseModel):
    """can_perform → действие можно выполнить."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["allowed"] = "allowed"


class Forbidden(BaseModel):
    """can_perform → действие нельзя выполнить, с причиной."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["forbidden"] = "forbidden"
    reason: ForbiddenReason
    # Детали обязательны только для CUSTOM; в остальных случаях
    # причина — самодостаточный enum, UI берёт локализацию по нему.
    details: str = ""


ActionAvailability = Annotated[
    Allowed | Forbidden,
    Field(discriminator="kind"),
]
"""Discriminated union — pydantic корректно сериализует и валидирует.

В коде проверяется через ``isinstance(av, Allowed)`` — это самый
короткий и type-safe способ ветвления.
"""


class ActionOutcome(BaseModel):
    """«Расписка» о завершении действия.

    Поле ``success=True`` означает «действие выполнено», а не
    «попало по цели». Содержательные результаты (попадание, урон) —
    в опубликованных событиях шины. ``events_published`` хранит
    ``event_type`` строки для аудита/тестов; сами события подписчики
    уже получили синхронно.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    success: bool
    consumed: ActionEconomyCost
    events_published: tuple[str, ...] = ()
    movement_spent_ft: int = 0
    notes: str = ""


__all__ = [
    "ActionAvailability",
    "ActionEconomyCost",
    "ActionOutcome",
    "ActionParams",
    "Allowed",
    "Forbidden",
    "ForbiddenReason",
    "NoParams",
]

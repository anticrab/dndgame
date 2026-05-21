"""EngineEvent — базовый класс события движка.

События выпускаются движком (через ``EventBus``) и подписчиками
(сценарий, журнал, UI, DiceStatistics, мастерский лог) обрабатываются
синхронно по правилам ``docs/ENGINE.md`` §5.2.

Конкретные события — это **подклассы** ``EngineEvent``: каждый описывает
свой набор полей (например, ``AttackRolled`` — атакующий, цель,
``EngineRollResult``). Здесь — только база.

Все события — pydantic-модели с `frozen=True` (иммутабельны после
создания) и `extra="forbid"` (защита от опечаток в полях).
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from dnd.application.dto.rolls import EngineRollResult


class EngineEvent(BaseModel):
    """База всех событий движка."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # `event_type` подкласс заполняет константой (например, "attack.rolled"),
    # чтобы можно было дискриминировать события в логе и в сериализации
    # без зависимости от Python-классов.
    event_type: ClassVar[str] = "engine.event"

    tags: tuple[str, ...] = Field(
        default=(),
        description=(
            "Свободные метки события — для аудита (например, "
            "'master_intervention') и фильтрации в UI / логе."
        ),
    )


class RollIssued(EngineEvent):
    """Бросок инициирован, но ещё не применён к состоянию.

    Между ``RollIssued`` и ``RollApplied`` мастер может вмешаться
    (``MasterIntent.reroll`` / ``set_roll``). В MVP вмешательства нет —
    события следуют последовательно. См. ``docs/ENGINE.md`` §7.4.

    ``DiceStatisticsService`` подписывается именно на ``RollIssued``,
    чтобы статистика считалась по «честному» броску до master-фаджа.
    """

    event_type: ClassVar[str] = "roll.issued"
    result: EngineRollResult


class RollApplied(EngineEvent):
    """Бросок применён к состоянию (атака попала/промахнулась, спасбросок
    прошёл/провалился). ``result`` может отличаться от ``RollIssued`` по
    содержимому, если мастер вмешался (одинаковый ``roll_id``)."""

    event_type: ClassVar[str] = "roll.applied"
    result: EngineRollResult

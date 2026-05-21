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

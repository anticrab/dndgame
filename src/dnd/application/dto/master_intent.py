"""MasterIntent — discriminated union вмешательств мастера.

Контракт зафиксирован в ``docs/MASTER.md`` §3 (полный список 25
операций) и ``docs/ENGINE.md`` §6.1 (DTO как тип).

В MVP реализованы только три типа — этого достаточно, чтобы движок и
сейв-формат были готовы к остальным. Добавление нового интента =
новый pydantic-класс + новая ветка union. Существующий код, читающий
``MasterIntent``, должен сужать тип через ``match intent.kind``.

Серилизация:

    from dnd.application.dto.master_intent import MasterIntentAdapter
    blob = MasterIntentAdapter.dump_json(intent)
    intent_back = MasterIntentAdapter.validate_json(blob)
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from dnd.application.dto.ids import CreatureId, PlayerId, RollId


class _MasterIntentBase(BaseModel):
    """Поля, общие для всех вмешательств мастера."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str = Field(
        min_length=1,
        description="Человеко-читаемая причина вмешательства — обязательна.",
    )
    issued_by: PlayerId = Field(description="PlayerId мастера, инициировавшего интент.")


class RerollIntent(_MasterIntentBase):
    """Перебросить указанный бросок до его применения.

    Возможно только между событиями ``RollIssued`` и ``RollApplied``
    (см. ``docs/ENGINE.md`` §7.4 двухфазная модель).
    """

    kind: Literal["reroll"] = "reroll"
    roll_id: RollId


class SetHpIntent(_MasterIntentBase):
    """Жёстко задать текущие HP существа.

    Прямое изменение состояния, минуя обычный урон/лечение. Полезно
    для боссов на скриптовых триггерах («у дракона осталось 1 HP —
    он сдаётся»).
    """

    kind: Literal["set_hp"] = "set_hp"
    creature_id: CreatureId
    value: int = Field(ge=0, description="Новое значение текущих HP, не выше maximum.")


class NarrateIntent(_MasterIntentBase):
    """Вкинуть текст-описание в лог боя.

    Не меняет состояние; влияет только на UI лога. Аудиенция
    регулируется ``audience`` (всем игрокам, конкретному PC, или
    скрыто — только в master log).
    """

    kind: Literal["narrate"] = "narrate"
    text: str = Field(min_length=1)
    audience: Literal["all", "master_only"] | CreatureId = "all"


MasterIntent = Annotated[
    RerollIntent | SetHpIntent | NarrateIntent,
    Field(discriminator="kind"),
]

# TypeAdapter — единая точка валидации/сериализации union снаружи.
# Например, при загрузке master_intervention из GameLog:
#   intent = MasterIntentAdapter.validate_python(record["payload"])
MasterIntentAdapter: TypeAdapter[MasterIntent] = TypeAdapter(MasterIntent)

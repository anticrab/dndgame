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

from dnd.application.dto.ids import CreatureId, RollId
from dnd.application.dto.rolls import EngineRollResult
from dnd.domain.values.damage import DamageType


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


# -- События боевых действий ------------------------------------------
#
# Эти события публикует ``AttackAction.execute`` (см. ACTIONS.md §2 и
# ENGINE.md §4). Поток событий одной атаки:
#
#   1) RollIssued / RollApplied      — за to-hit бросок (от DiceRoller)
#   2) AttackRolled                  — связывает roll_id с attacker/target
#   3) RollIssued / RollApplied      — за damage-бросок (если попал)
#   4) DamageDealt                   — финальный применённый урон
#   5) AttackResolved                — итог атаки (попадание/крит/смерть)
#
# По roll_id'ам можно восстановить полную картину; AttackRolled и
# AttackResolved нужны UI и логу, чтобы не вычислять hit/miss из сырых
# d20.


class AttackRolled(EngineEvent):
    """Бросок атаки выполнен; связывает roll_id с участниками и целевым
    КД (с уже учтённым cover/AC-модификаторами).

    Публикуется ПОСЛЕ ``RollApplied`` за то же roll_id — чтобы
    подписчики увидели роллер сначала, а потом контекст. Не
    "перерасчёт" — только проекция в логе атаки.
    """

    event_type: ClassVar[str] = "attack.rolled"
    attacker_id: CreatureId
    target_id: CreatureId
    attack_roll_id: RollId
    effective_ac: int  # КД цели с учётом cover и модификаторов
    is_critical_hit: bool
    is_critical_miss: bool  # natural 1
    hit: bool


class DamageDealt(EngineEvent):
    """Цель получила урон. Публикуется ПОСЛЕ ``Creature.take_damage``.

    ``final_amount`` — урон уже после resistance/vulnerability/immunity
    (= ``DamageResult.final_amount``). ``raw_amount`` — что выпало на
    кубах до применения мультипликаторов.
    """

    event_type: ClassVar[str] = "damage.dealt"
    attacker_id: CreatureId
    target_id: CreatureId
    damage_roll_id: RollId
    damage_type: DamageType
    raw_amount: int
    final_amount: int
    is_critical: bool


class AttackResolved(EngineEvent):
    """Итог атаки. Финальное событие в потоке одной атаки.

    ``downed=True``, если цель упала в 0 HP именно этой атакой
    (``DamageResult.was_lethal``). ``concentration_save_dc != None``,
    если цель держала концентрацию и движок должен запросить CON-save.
    """

    event_type: ClassVar[str] = "attack.resolved"
    attacker_id: CreatureId
    target_id: CreatureId
    attack_roll_id: RollId
    hit: bool
    is_critical: bool
    downed: bool = False
    concentration_save_dc: int | None = None

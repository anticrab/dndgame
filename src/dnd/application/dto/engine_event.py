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

from dnd.application.dto.ids import CreatureId, ObjectId, RollId
from dnd.application.dto.initiative import InitiativeEntry
from dnd.application.dto.rolls import EngineRollResult
from dnd.domain.values.damage import DamageType
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square


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
    # Прозрачность броска — чтобы UI/лог мог показать «d20=18 +5 → 23
    # adv vs AC 16», а не только итог hit/miss.
    d20_raw: int  # сырой d20 (для adv/dis — выбранный из двух)
    total: int  # d20 + бонусы (что сравнивалось с effective_ac)
    advantage: bool = False
    disadvantage: bool = False


class DamageDealt(EngineEvent):
    """Цель получила урон. Публикуется ПОСЛЕ ``Creature.take_damage``.

    ``final_amount`` — урон уже после resistance/vulnerability/immunity
    (= ``DamageResult.final_amount``). ``raw_amount`` — что выпало на
    кубах до применения мультипликаторов.

    ``hp_after`` / ``hp_max`` — снапшот HP цели после применения, чтобы
    UI мог показывать `(HP 8/20)` сразу в строке урона без отдельного
    лукапа Creature.
    """

    event_type: ClassVar[str] = "damage.dealt"
    attacker_id: CreatureId
    target_id: CreatureId
    damage_roll_id: RollId
    damage_type: DamageType
    raw_amount: int
    final_amount: int
    is_critical: bool
    hp_after: int
    hp_max: int


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


# -- События движения --------------------------------------------------
#
# Публикует ``MoveAction.execute`` (этап E3). Поток одного шага:
#
#   (опц.) OpportunityAttackProvoked    — за каждого угрожающего, кому
#                                         предоставился триггер
#   MoveStepTaken                       — после фактического перемещения
#
# После последнего шага — MoveCompleted с агрегатами.


class MoveStepTaken(EngineEvent):
    """Один шаг движения по клетке. Публикуется ПОСЛЕ перемещения и
    списания футов из бюджета."""

    event_type: ClassVar[str] = "move.step_taken"
    actor_id: CreatureId
    frm: Square
    to: Square
    cost_ft: int  # 5 для обычной клетки, 10 для difficult terrain
    difficult: bool


class MoveCompleted(EngineEvent):
    """Завершение MoveAction. ``steps`` — сколько клеток пройдено,
    ``total_spent_ft`` — суммарная стоимость."""

    event_type: ClassVar[str] = "move.completed"
    actor_id: CreatureId
    start_pos: Square
    end_pos: Square
    steps: int
    total_spent_ft: int


# -- События боя (Encounter lifecycle, этап F) -------------------------


class InitiativeRolled(EngineEvent):
    """Инициатива брошена; ``order`` — финальный порядок ходов в раунде.

    Публикуется один раз в начале боя (``Encounter.start``). Содержит
    все participants' бросков, включая мёртвых на момент старта (на MVP
    их в order не помещаем). См. ``docs/ENCOUNTER.md`` §2.
    """

    event_type: ClassVar[str] = "encounter.initiative_rolled"
    order: tuple[InitiativeEntry, ...]


class RoundStarted(EngineEvent):
    """Начался раунд n. После публикации reactions у всех participants
    обнулены."""

    event_type: ClassVar[str] = "encounter.round_started"
    round_number: int


class RoundEnded(EngineEvent):
    """Закончился раунд n. Все участники в order отходили (живые или нет)."""

    event_type: ClassVar[str] = "encounter.round_ended"
    round_number: int


class TurnStarted(EngineEvent):
    """Начался ход actor'а. Stances actor'а сброшены, свежий TurnContext
    создан, экономия обнулена."""

    event_type: ClassVar[str] = "encounter.turn_started"
    actor_id: CreatureId
    round_number: int
    skipped: bool = False  # True если existo не может ходить (0 HP и т.п.)


class TurnEnded(EngineEvent):
    """Закончился ход actor'а."""

    event_type: ClassVar[str] = "encounter.turn_ended"
    actor_id: CreatureId
    round_number: int


class EncounterEnded(EngineEvent):
    """Бой завершён.

    ``winners`` — победившая фракция, или ``None`` если живых из
    обеих воюющих сторон уже нет (одновременный нокаут) либо остались
    только NEUTRAL.

    StrEnum ``Faction`` сериализуется как строка автоматически —
    pydantic сохраняет тип и при `.model_dump()` подписчик получает
    `str` (для логов), при доступе через атрибут — `Faction` enum.
    Аудит 13 EN-R005.
    """

    event_type: ClassVar[str] = "encounter.ended"
    winners: Faction | None
    round_number: int
    survivors: tuple[CreatureId, ...]


class HelpGranted(EngineEvent):
    """Help-action: ``helper`` готов содействовать ``ally`` в следующей
    атаке по ``target`` (PHB-2024 стр. 22). Сам бонус — advantage на
    следующую атаку ally — реализован читателем поля
    ``Creature.helped_against`` в ``AttackAction``."""

    event_type: ClassVar[str] = "help.granted"
    helper_id: CreatureId
    ally_id: CreatureId
    target_id: CreatureId


class SearchPerformed(EngineEvent):
    """Search-action: бросок ABILITY_CHECK Wisdom (PHB-2024 стр. 357 —
    Insight / Medicine / Perception / Survival; все четыре — Wisdom).
    Скрытие/обнаружение чего конкретно — решает сценарий (подписчик)
    через сравнение ``total`` с DC.
    """

    event_type: ClassVar[str] = "search.performed"
    actor_id: CreatureId
    skill_kind: str  # "insight" | "medicine" | "perception" | "survival"
    roll_id: RollId
    total: int


class StanceTaken(EngineEvent):
    """Actor встал в одну из стоек (Dodge / Dash / Disengage).
    Подписчик (EventPrinter) пишет, например, `aelar takes Dodge`.

    ``stance`` — строковое имя из ``CombatStance`` (StrEnum). Не несём
    весь enum, чтобы DTO не зависел от domain.entities. Подписчик
    форматирует по строке.
    """

    event_type: ClassVar[str] = "stance.taken"
    actor_id: CreatureId
    stance: str  # "dodging" | "dashing" | "disengaged"


class ObjectInteracted(EngineEvent):
    """Игрок взаимодействовал с интерактивным объектом.

    PHB-2024 стр. 21: free object interaction (1/ход) — открыть дверь,
    взять предмет, и т.п.
    """

    event_type: ClassVar[str] = "object.interacted"
    actor_id: CreatureId
    object_id: ObjectId
    kind: str  # "open" | "close" | "examine"
    loot: tuple[str, ...] = ()  # для CHEST: содержимое


class ObjectDamaged(EngineEvent):
    """Объект получил урон (BreakAction). Если broken=True — объект
    сломан (HP=0)."""

    event_type: ClassVar[str] = "object.damaged"
    attacker_id: CreatureId
    object_id: ObjectId
    raw_amount: int
    final_amount: int
    hp_after: int
    broken: bool


class OpportunityAttackProvoked(EngineEvent):
    """Атакующий покидает клетку, на которой его удерживал в зоне
    угрозы threatener. Само разрешение реакции — задача обработчиков
    (E6 OpportunityAttack); это событие — триггер.

    PHB-2024 стр. 22 («Перемещение около других существ»): провокация
    случается ОДИН раз за движение per threatener (как только existo
    впервые покидает его reach), не на каждый шаг внутри.
    """

    event_type: ClassVar[str] = "opportunity_attack.provoked"
    actor_id: CreatureId  # тот, кто двигается
    threatener_id: CreatureId  # тот, кто получает реакцию
    leaving_square: Square  # клетка, из которой actor вышел из зоны


# === O-5: Inventory events ============================================
#
# События для логирования операций с инвентарём. Сами действия (Pickup/
# Drop/Equip) ещё нет (O-8); события готовы заранее, чтобы EventPrinter
# мог писать в лог уже на этапе O-6 (chest loot).


class ItemPickedUp(EngineEvent):
    """Существо подобрало предмет (из chest, с трупа, с пола)."""

    event_type: ClassVar[str] = "inventory.item_picked_up"
    actor_id: CreatureId
    item_id: str
    item_name: str
    qty: int
    source: str  # "chest:<obj_id>" | "corpse:<creature_id>" | "ground"


class ItemDropped(EngineEvent):
    """Существо выбросило предмет (в инвентарь не влезает / вручную)."""

    event_type: ClassVar[str] = "inventory.item_dropped"
    actor_id: CreatureId
    item_id: str
    item_name: str
    qty: int


class ItemEquipped(EngineEvent):
    """Существо экипировало предмет (WEAPON / ARMOR)."""

    event_type: ClassVar[str] = "inventory.item_equipped"
    actor_id: CreatureId
    item_id: str
    item_name: str


class ItemUnequipped(EngineEvent):
    """Существо сняло предмет с экипировки."""

    event_type: ClassVar[str] = "inventory.item_unequipped"
    actor_id: CreatureId
    item_id: str
    item_name: str

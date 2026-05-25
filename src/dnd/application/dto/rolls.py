"""DTO для бросков движка.

Используются ``DiceRoller`` (`application/engine/dice_roller.py`) и
правилами домена (``attack_roll``, ``save``, ``ability_check``).
Контракт — ``docs/ENGINE.md`` §7.

* :class:`RollPurpose` — *что* за бросок (атака / спасбросок / тест /
  урон / инициатива / hit dice / спасбросок от смерти / прочее).
* :class:`RollContext` — вход для ``DiceRoller.roll``: участники,
  флаги преимущества/помехи, доп. кости от модификаторов, теги.
* :class:`EngineRollResult` — выход. Иммутабельный pydantic. Содержит
  ``roll_id: UUID`` для master-перебросов и полный набор «сырых»
  данных для аудита и статистики (см. ``DiceStatisticsService``).
"""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from dnd.domain.values.ids import CreatureId, RollId

# RollPurpose переехал в domain (доменное понятие); реэкспортим здесь для
# совместимости — многие импортят его из dnd.application.dto.rolls.
from dnd.domain.values.roll_purpose import RollPurpose


class RollContext(BaseModel):
    """Семантический контекст броска.

    Иммутабельный pydantic. Передаётся в ``DiceRoller.roll(expr, ctx)``,
    оседает в ``EngineRollResult.context``, попадает в события
    ``RollIssued``/``RollApplied`` и в ``GameLog``.

    ``extra_dice`` — список выражений костей, добавляемых ModifierApplier'ом
    (например, +1d4 от заклинания Bless). Каждый член — сериализованный
    ``DiceExpr`` (например, ``"1d4"``), потому что DiceExpr — это
    domain-VO, а ContextDTO живёт в application-слое.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    purpose: RollPurpose
    actor_id: CreatureId | None = None
    target_id: CreatureId | None = None
    advantage: bool = False
    disadvantage: bool = False
    crit: bool = False
    extra_dice: tuple[str, ...] = Field(
        default=(),
        description=(
            "Сериализованные DiceExpr доп. костей (Bless +1d4, Sneak Attack "
            "2d6 и т.п.), которые добавляет ModifierApplier."
        ),
    )
    tags: tuple[str, ...] = Field(
        default=(),
        description="Свободные метки: 'master_intervention', 'reroll', ...",
    )


class EngineRollResult(BaseModel):
    """Результат броска от ``DiceRoller``. Иммутабельный pydantic.

    Все поля присутствуют всегда: ``raw`` / ``kept`` / ``modifier`` /
    ``total`` дают полную трассировку. ``roll_id`` нужен мастеру для
    переброса (``MasterIntent.reroll``) и для соответствия событий
    ``RollIssued`` ↔ ``RollApplied``.

    ``d20_raw`` — сырой результат одиночного d20 без бонусов, для
    статистики «удачи» (``DiceStatisticsService``); None для бросков
    другого вида (2d6, 4d6kh3, ...).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    roll_id: RollId
    expr: str = Field(description="Сериализованное DiceExpr вида '2d6+3'.")
    raw: tuple[int, ...]
    kept: tuple[int, ...]
    modifier: int
    extra_dice_rolls: tuple[int, ...] = Field(
        default=(),
        description=(
            "Отдельно — кости от RollContext.extra_dice (Bless +1d4 и т.п.). "
            "Включены в `total`; выделены, чтобы UI/лог мог показать их отдельно."
        ),
    )
    total: int
    advantage: bool = False
    disadvantage: bool = False
    crit: bool = False
    context: RollContext

    @property
    def d20_raw(self) -> int | None:
        """Для одиночного d20 — выпавшее значение без модификаторов.

        Используется ``DiceStatisticsService`` для расчёта «удачи».
        Для не-d20 (2d6, 4d6kh3) возвращает None.

        Эвристика: если выражение начинается с ``1d20`` или ``d20`` и
        ``kept`` содержит ровно одно значение — берём его.
        """
        # Парсим только префикс — этого достаточно. Точная нотация
        # известна: DiceExpr.__str__ всегда даёт "{count}d{sides}..."
        normalized = self.expr.lower()
        is_single_d20 = (
            normalized.startswith("1d20") and "kh" not in normalized and "kl" not in normalized
        )
        if is_single_d20 and len(self.kept) == 1:
            return self.kept[0]
        return None

    def is_natural_20(self) -> bool:
        return self.d20_raw == 20

    def is_natural_1(self) -> bool:
        return self.d20_raw == 1


def make_roll_id() -> RollId:
    """Сгенерировать новый ``RollId``. Отдельная функция, чтобы в тестах
    можно было monkeypatch'нуть на детерминированный."""
    return RollId(uuid4())


__all__ = [
    "EngineRollResult",
    "RollContext",
    "RollPurpose",
    "make_roll_id",
]

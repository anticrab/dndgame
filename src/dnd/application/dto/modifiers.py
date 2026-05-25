"""DTO для системы модификаторов.

Спецификация — ``docs/MODIFIERS.md``. Здесь — MVP-подмножество,
покрывающее реальные нужды первого боя:

* :class:`NumericBonusEffect` — +N к броску атаки, КД, спасброскам,
  тестам, скорости, инициативе (Талисман Стойкости +1 КД, +2 спасброски
  Тел.).
* :class:`DiceBonusEffect` — добавляет дополнительные кости в бросок
  (Bless +1d4 к атаке, Sneak Attack 2d6 к урону).
* :class:`AdvantageEffect` — преимущество на конкретный класс бросков.
* :class:`DisadvantageEffect` — помеха (Poisoned, Frightened).

Остальные категории из MODIFIERS.md §1 (resistance, condition,
ability_override, replacement, trigger_override) добавятся при первом
заклинании/предмете, которое их требует. Архитектура к этому готова —
``ModifierEffect`` это discriminated union на pydantic.

Цели (``ModifierTarget``) — пока узкий список из MVP:

* ``ATTACK_ROLL`` — броски атаки.
* ``DAMAGE_ROLL`` — броски урона.
* ``SAVING_THROW`` — спасброски (опционально с фильтром по ability).
* ``ABILITY_CHECK`` — проверки характеристик/навыков.
* ``ARMOR_CLASS`` — КД (не бросок, а значение, но обрабатывается тут же).

``StackingPolicy`` — по правилу книги «бонусы одного типа не складываются»
(книга 2024 стр. 12, «Бонус не складывается»). По умолчанию ``BEST_ONLY``:
из всех модификаторов одного source_kind/target берём наибольший.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from dnd.application.dto.rolls import RollPurpose
from dnd.domain.values.ids import CreatureId

# -- ModifierTarget -------------------------------------------------------


class ModifierTargetKind(StrEnum):
    """Категория цели, на которую действует модификатор."""

    ATTACK_ROLL = "attack_roll"
    DAMAGE_ROLL = "damage_roll"
    SAVING_THROW = "saving_throw"
    ABILITY_CHECK = "ability_check"
    ARMOR_CLASS = "armor_class"
    INITIATIVE = "initiative"
    SPEED = "speed"


# -- Effects --------------------------------------------------------------


class _EffectBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NumericBonusEffect(_EffectBase):
    """Числовой бонус/штраф к броску или значению.

    Талисман Стойкости: ``NumericBonusEffect(value=+1)`` к ``ARMOR_CLASS``;
    проф. бонус: ``NumericBonusEffect(value=+2)`` к ``ATTACK_ROLL``
    конкретного оружия (через ``stack_key="proficiency"``).
    """

    kind: Literal["numeric_bonus"] = "numeric_bonus"
    value: int


class DiceBonusEffect(_EffectBase):
    """Дополнительные кости к броску.

    Bless: ``DiceBonusEffect(dice="1d4")`` к ``ATTACK_ROLL`` или
    ``SAVING_THROW``. Sneak Attack плута 1-го уровня:
    ``DiceBonusEffect(dice="1d6")`` к ``DAMAGE_ROLL`` (при выполнении
    условий — это уже Specification).

    ``dice`` — сериализованное DiceExpr (например, ``"1d4"`` или ``"2d6"``).
    Валидируется парсингом в момент применения через ``DiceRoller``;
    модель здесь не парсит, чтобы не тянуть domain-импорт в DTO.
    """

    kind: Literal["dice_bonus"] = "dice_bonus"
    dice: str = Field(min_length=2, description="Сериализованный DiceExpr, например '1d4'.")


class AdvantageEffect(_EffectBase):
    """Преимущество на конкретный класс бросков (только d20).

    Книга стр. 11: преимущество применимо только к броскам ``ATTACK_ROLL``,
    ``SAVING_THROW``, ``ABILITY_CHECK`` (это всё d20-тесты). Применить
    advantage к ``DAMAGE_ROLL`` — программная ошибка вызывающего
    (ModifierApplier должен это проверять).
    """

    kind: Literal["advantage"] = "advantage"


class DisadvantageEffect(_EffectBase):
    """Помеха. Симметрично advantage.

    Poisoned: ``DisadvantageEffect`` к ``ATTACK_ROLL`` и
    ``ABILITY_CHECK``. Frightened: ``DisadvantageEffect`` к
    ``ATTACK_ROLL`` и ``ABILITY_CHECK`` (с дополнительным условием
    «источник страха в поле зрения», см. ``ModifierCondition`` пост-MVP).
    """

    kind: Literal["disadvantage"] = "disadvantage"


ModifierEffect = Annotated[
    NumericBonusEffect | DiceBonusEffect | AdvantageEffect | DisadvantageEffect,
    Field(discriminator="kind"),
]


# -- StackingPolicy -------------------------------------------------------


class StackingPolicy(StrEnum):
    """Как ведут себя одинаковые модификаторы.

    Книга 2024 стр. 12, «Бонус не складывается»: «ваш бонус мастерства
    не может быть добавлен к броску… более одного раза». Расширенное
    правило: разные источники одного «класса» бонуса (например, два
    магических меча с +1) не суммируются — берётся один.

    Поэтому дефолт — ``BEST_ONLY``: из всех модификаторов с одинаковым
    ``stack_key`` берём наибольший. ``STACK_ALL`` — для случаев, где
    суммирование явно разрешено (Bless +1d4 и Inspire Heroics +1d8 —
    они от разных источников и разных классов; см. MODIFIERS.md §2.6).
    """

    BEST_ONLY = "best_only"
    STACK_ALL = "stack_all"
    REPLACE = "replace"


# -- Modifier -------------------------------------------------------------


class ModifierSourceKind(StrEnum):
    """Откуда взялся модификатор. Влияет на stacking и master-видимость."""

    ITEM = "item"  # магический предмет, расходник
    SPELL = "spell"  # активное заклинание
    FEATURE = "feature"  # классовая особенность
    CONDITION = "condition"  # активное состояние (Poisoned и т.п.)
    BACKGROUND = "background"  # черта от предыстории
    SCENARIO = "scenario"  # триггер сценария
    MASTER_INTERVENTION = "master_intervention"  # вмешательство мастера
    EXHAUSTION = "exhaustion"  # уровни истощения (см. Q34)


class Modifier(BaseModel):
    """Описывает один эффект, влияющий на броски и значения.

    Иммутабельный pydantic-DTO. Хранится в ``GameState.modifiers`` или
    собирается на лету Conditions/Features. Применяется к конкретному
    броску через :class:`ModifierApplier`.

    Поля:

    * ``source_id`` / ``source_kind`` — кто породил (для аудита, UI,
      stacking).
    * ``target_kind`` — на какой класс бросков/значений действует.
    * ``effect`` — что именно делает (discriminated union).
    * ``stack_key`` — ключ для группировки при ``BEST_ONLY``. Например,
      `"proficiency"`, `"magic_weapon"`, `"bless"`. Модификаторы с
      одинаковым ключом борются по политике; разные ключи стэкаются.
    * ``stacking`` — стратегия stacking (по умолчанию BEST_ONLY).
    * ``applies_to_purpose`` — опциональный фильтр по конкретной
      категории броска (например, ``ATTACK_ROLL`` модификатор всё ещё
      выдаётся только при ``RollPurpose.ATTACK``; обычно совпадает с
      ``target_kind``, но для INITIATIVE / SPEED / ARMOR_CLASS отдельная
      проверка).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(
        min_length=1,
        description=(
            "Идентификатор источника, например 'item:talisman-of-fortitude' или 'spell:bless'."
        ),
    )
    source_kind: ModifierSourceKind
    target_kind: ModifierTargetKind
    effect: ModifierEffect
    owner_id: CreatureId
    """ID существа, к которому модификатор применяется (на чьи броски/значения)."""

    stack_key: str = Field(
        default="",
        description=(
            "Группа stacking. Модификаторы с одним stack_key борются по "
            "stacking policy; разные ключи стэкаются всегда. Пустая строка = "
            "уникальная группа (источник сам по себе)."
        ),
    )
    stacking: StackingPolicy = StackingPolicy.BEST_ONLY


# -- RollAdjustments — результат collect+to_roll_adjustments --------------


class RollAdjustments(BaseModel):
    """Результат свёртки модификаторов в параметры броска.

    Передаётся правилами (``attack_roll``, ``save``) в ``RollContext`` →
    ``DiceRoller``.

    * ``numeric_bonus`` — итоговый числовой бонус к броску (с учётом
      stacking).
    * ``extra_dice`` — список сериализованных DiceExpr доп. костей
      (Bless +1d4, Sneak Attack 2d6).
    * ``advantage`` / ``disadvantage`` — флаги. По правилам книги
      «не суммируются»: если есть хотя бы один advantage и хотя бы
      один disadvantage, оба гасятся (см. книгу стр. 11). Решение
      принимается в ``to_roll_adjustments``.

    Возвращается в :class:`RollContext` через `RollContext` или
    напрямую правилами.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    numeric_bonus: int = 0
    extra_dice: tuple[str, ...] = ()
    advantage: bool = False
    disadvantage: bool = False
    sources: tuple[str, ...] = Field(
        default=(),
        description="source_id всех применённых модификаторов — для аудит-лога.",
    )


__all__ = [
    "AdvantageEffect",
    "DiceBonusEffect",
    "DisadvantageEffect",
    "Modifier",
    "ModifierEffect",
    "ModifierSourceKind",
    "ModifierTargetKind",
    "NumericBonusEffect",
    "RollAdjustments",
    "RollPurpose",  # re-export для удобства
    "StackingPolicy",
]

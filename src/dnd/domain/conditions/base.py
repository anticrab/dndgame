"""Базовый интерфейс состояния (Condition).

Условия — это **плагины**: Python-классы, реализующие протокол
:class:`Condition` и зарегистрированные в
:class:`~dnd.domain.conditions.registry.ConditionRegistry`.

Состав плагина:

* ``id`` — стабильный строковый идентификатор (``"poisoned"``,
  ``"prone"`` и т.д.). Совпадает с ``ConditionId`` в коде, попадает
  в сейв и в YAML.
* ``provides_modifiers(owner_id)`` — список ``Modifier``, которые
  состояние накладывает на броски/значения существа. Например,
  Poisoned → DisadvantageEffect на ATTACK_ROLL и ABILITY_CHECK.
* ``implies`` — список других состояний, которые автоматически
  активируются вместе (Paralyzed → Incapacitated; Stunned →
  Incapacitated; Unconscious → Incapacitated + Prone — Книга 2024,
  глоссарий состояний).

Состояние **не** хранит per-existo state (как долго наложено, кто
наложил). Это будет в ``ConditionInstance`` (по Q38, пост-MVP).
В MVP — простое множество ``Creature.conditions: set[ConditionId]``.

Книга 2024, стр. 27 «Без накопления»: «эффект состояния не ухудшается;
вы либо находитесь под действием состояния, либо нет». Поэтому базовый
интерфейс stateless — состояние «есть/нет», что бы его ни накладывало.
"""

from __future__ import annotations

from typing import Protocol

from dnd.domain.values.ids import ConditionId, CreatureId
from dnd.domain.values.modifiers import Modifier


class Condition(Protocol):
    """Контракт плагина-состояния."""

    id: ConditionId
    """Стабильный идентификатор. Уникален в ConditionRegistry."""

    implies: frozenset[ConditionId]
    """Другие состояния, которые автоматически активируются вместе.

    Книга 2024 стр. 367 (глоссарий, «Бессознательный»): «существо
    в этом состоянии также Incapacitated и Prone». Аналогично для
    Paralyzed и Stunned. Используется ``apply_condition`` для
    каскадного применения.
    """

    def provides_modifiers(self, owner_id: CreatureId) -> tuple[Modifier, ...]:
        """Какие модификаторы налагает это состояние на броски существа.

        Пример: Poisoned → DisadvantageEffect на ATTACK_ROLL и
        ABILITY_CHECK; Prone → DisadvantageEffect на ATTACK_ROLL.

        Возвращает кортеж (иммутабельно), source_id вида
        ``"condition:<id>"``. ``ModifierApplier`` собирает их вместе с
        другими модификаторами при сборке RollAdjustments.
        """

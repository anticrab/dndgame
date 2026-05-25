"""Module-level реестр Conditions (Q23).

Регистрация — **явная**, не через декораторы при импорте. Это
сознательное решение (см. ``docs/ARCHITECTURE.md`` §3.12): декораторы
создают скрытое глобальное состояние и порядок-импортов-зависимую
инициализацию.

Использование:

1. В composition root (``interfaces/cli/composition.py``) вызывается
   ``register_default_conditions(registry)``, который добавляет все
   8 базовых состояний MVP.
2. Тесты создают свой ``ConditionRegistry()`` — изолировано, никаких
   глобальных side-effect'ов.
3. ``ContentService.validate()`` при старте проверяет, что все
   ``ConditionId``, на которые ссылается контент (yaml монстры/
   заклинания), зарегистрированы.
"""

from __future__ import annotations

from collections.abc import Iterator

from dnd.domain.conditions.base import Condition
from dnd.domain.values.ids import ConditionId


class ConditionRegistry:
    """Хранит плагины состояний по их ``ConditionId``.

    Не singleton — каждый ``compose_root`` собирает свой, можно
    создавать в тестах с урезанным набором.
    """

    def __init__(self) -> None:
        self._items: dict[ConditionId, Condition] = {}

    def register(self, condition: Condition) -> None:
        """Зарегистрировать плагин-состояние.

        При повторной регистрации того же id — ValueError, чтобы
        ловить конфликты на старте, а не в рантайме.
        """
        if condition.id in self._items:
            raise ValueError(f"condition {condition.id!r} is already registered")
        self._items[condition.id] = condition

    def get(self, condition_id: ConditionId) -> Condition:
        try:
            return self._items[condition_id]
        except KeyError as exc:
            raise KeyError(
                f"condition {condition_id!r} is not registered in ConditionRegistry"
            ) from exc

    def has(self, condition_id: ConditionId) -> bool:
        return condition_id in self._items

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Condition]:
        return iter(self._items.values())

    def ids(self) -> frozenset[ConditionId]:
        return frozenset(self._items)

"""AbilityRegistry — runtime-реестр доступных умений.

Простой in-memory index по :class:`AbilityId`. Регистрация дубликатов
запрещена (опечатка в `register_default_abilities` упала бы тихо и
переопределила существующее умение). Метод :meth:`all` возвращает
кортеж, а не итератор — итератор сжигается после первого прохода и
ловит пользователя на «почему второй цикл пустой» (нам это не нужно).
"""
from __future__ import annotations

from dnd.application.abilities.ability import Ability, AbilityId


class AbilityRegistry:
    def __init__(self) -> None:
        self._by_id: dict[AbilityId, Ability] = {}

    def register(self, ability: Ability) -> None:
        if ability.id in self._by_id:
            raise ValueError(f"Ability {ability.id!r} already registered")
        self._by_id[ability.id] = ability

    def get(self, id_: AbilityId) -> Ability:
        return self._by_id[id_]

    def all(self) -> tuple[Ability, ...]:
        return tuple(self._by_id.values())


__all__ = ["AbilityRegistry"]

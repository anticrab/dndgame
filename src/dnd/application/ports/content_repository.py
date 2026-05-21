"""ContentRepository — Port для каталога контента (оружие, монстры,
сценарии).

Адаптеры:

* :class:`~dnd.infrastructure.content.yaml_repository.YamlContentRepository`
  — грузит из ``data/content/*.yaml`` (MVP).
* SQLite-адаптер — поверх схемы content.sqlite (H-этап позднее).

Контракт:

* **read-only** — никаких ``add``/``remove``; контент задаётся вне игры.
* **eager** — загрузка при старте, кэш в памяти. Игровой цикл не должен
  ждать ввода-вывода.
* lookup по id; возвращает шаблон или поднимает ``KeyError``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from dnd.application.dto.templates import (
    MonsterTemplate,
    ScenarioTemplate,
    WeaponTemplate,
)


@runtime_checkable
class ContentRepository(Protocol):
    """Доступ к каталогу контента."""

    def weapons(self) -> Sequence[WeaponTemplate]:
        """Все оружия."""

    def weapon_by_id(self, weapon_id: str) -> WeaponTemplate:
        """Один по id; ``KeyError`` если нет."""

    def monsters(self) -> Sequence[MonsterTemplate]:
        """Все монстры."""

    def monster_by_id(self, monster_id: str) -> MonsterTemplate:
        """Один по id; ``KeyError`` если нет."""

    def scenarios(self) -> Sequence[ScenarioTemplate]:
        """Все сценарии."""

    def scenario_by_id(self, scenario_id: str) -> ScenarioTemplate:
        """Один по id; ``KeyError`` если нет."""


__all__ = ["ContentRepository"]

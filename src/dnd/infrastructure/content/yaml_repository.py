"""YamlContentRepository — загрузка контента из YAML-каталога.

Каталог имеет фиксированный layout:

::

    data/content/
      weapons.yaml      # список WeaponTemplate
      monsters.yaml     # список MonsterTemplate
      scenarios.yaml    # список ScenarioTemplate

Все файлы загружаются один раз при создании репозитория; после этого
доступ — in-memory словарь, ~O(1) на лукап. Перезагрузка контента в
рантайме — пост-MVP (через ``invalidate_cache()``, который пока не
реализован).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TypeVar

import yaml  # type: ignore[import-untyped]
from pydantic import TypeAdapter

from dnd.application.dto.templates import (
    MonsterTemplate,
    ScenarioTemplate,
    WeaponTemplate,
)

T = TypeVar("T")

_WEAPONS_ADAPTER = TypeAdapter(list[WeaponTemplate])
_MONSTERS_ADAPTER = TypeAdapter(list[MonsterTemplate])
_SCENARIOS_ADAPTER = TypeAdapter(list[ScenarioTemplate])


class YamlContentRepository:
    """In-memory кэш над YAML-файлами.

    Чтение происходит в конструкторе — failure-fast: если контент битый,
    мы узнаём об этом до начала игры.
    """

    def __init__(self, content_dir: Path) -> None:
        if not content_dir.is_dir():
            raise FileNotFoundError(
                f"content_dir does not exist or is not a directory: {content_dir}"
            )

        self._weapons: dict[str, WeaponTemplate] = {
            w.id: w for w in _load_yaml_list(content_dir / "weapons.yaml", _WEAPONS_ADAPTER)
        }
        self._monsters: dict[str, MonsterTemplate] = {
            m.id: m for m in _load_yaml_list(content_dir / "monsters.yaml", _MONSTERS_ADAPTER)
        }
        self._scenarios: dict[str, ScenarioTemplate] = {
            s.id: s for s in _load_yaml_list(content_dir / "scenarios.yaml", _SCENARIOS_ADAPTER)
        }

    # --- weapons ------------------------------------------------------

    def weapons(self) -> Sequence[WeaponTemplate]:
        return tuple(self._weapons.values())

    def weapon_by_id(self, weapon_id: str) -> WeaponTemplate:
        try:
            return self._weapons[weapon_id]
        except KeyError as exc:
            raise KeyError(f"unknown weapon id: {weapon_id!r}") from exc

    # --- monsters -----------------------------------------------------

    def monsters(self) -> Sequence[MonsterTemplate]:
        return tuple(self._monsters.values())

    def monster_by_id(self, monster_id: str) -> MonsterTemplate:
        try:
            return self._monsters[monster_id]
        except KeyError as exc:
            raise KeyError(f"unknown monster id: {monster_id!r}") from exc

    # --- scenarios ----------------------------------------------------

    def scenarios(self) -> Sequence[ScenarioTemplate]:
        return tuple(self._scenarios.values())

    def scenario_by_id(self, scenario_id: str) -> ScenarioTemplate:
        try:
            return self._scenarios[scenario_id]
        except KeyError as exc:
            raise KeyError(f"unknown scenario id: {scenario_id!r}") from exc


def _load_yaml_list(path: Path, adapter: TypeAdapter[list[T]]) -> list[T]:
    """Загрузить и провалидировать YAML-список. Пустой файл → [].

    Если файла нет — пустой список (контент опциональный по mvp).
    """
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected YAML top-level list, got {type(raw).__name__}")
    return adapter.validate_python(raw)


__all__ = ["YamlContentRepository"]

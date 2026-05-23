"""YamlSpriteRegistry — читает data/content/sprites/{cat}/*.yaml.

Layout:

::

    sprites/
      terrain/{id}.yaml
      features/{id}.yaml
      objects/{id}.yaml   (на будущее, K6/K7)
      creatures/{id}.yaml (на будущее, K6/K7)

Failure-fast: битый YAML или невалидная схема → ошибка в ``__init__``.
Отсутствующий каталог — это норма (контент опционален в раннем MVP),
просто пустой реестр.
"""
from __future__ import annotations

from pathlib import Path
from typing import TypeVar

import yaml  # type: ignore[import-untyped]
from pydantic import TypeAdapter

from dnd.application.ports.sprite_registry import SpriteCategory
from dnd.domain.values.sprite_meta import FeatureKind, TerrainBase

_TERRAIN_ADAPTER = TypeAdapter(TerrainBase)
_FEATURE_ADAPTER = TypeAdapter(FeatureKind)

_T = TypeVar("_T", TerrainBase, FeatureKind)


class YamlSpriteRegistry:
    """In-memory кэш sprite-YAMLs.

    В K2 реализованы только TERRAIN и FEATURE — OBJECT и CREATURE
    sprite-meta появятся в K6/K7 как отдельные subclasses.
    """

    def __init__(self, sprites_dir: Path) -> None:
        self._terrains: dict[str, TerrainBase] = {}
        self._features: dict[str, FeatureKind] = {}
        if sprites_dir.is_dir():
            self._terrains = _load_dir(
                sprites_dir / "terrain", _TERRAIN_ADAPTER
            )
            self._features = _load_dir(
                sprites_dir / "features", _FEATURE_ADAPTER
            )

    def get_terrain(self, id_: str) -> TerrainBase:
        try:
            return self._terrains[id_]
        except KeyError as exc:
            raise KeyError(f"unknown terrain sprite: {id_!r}") from exc

    def get_feature(self, id_: str) -> FeatureKind:
        try:
            return self._features[id_]
        except KeyError as exc:
            raise KeyError(f"unknown feature sprite: {id_!r}") from exc

    def list_by_category(
        self, category: SpriteCategory
    ) -> tuple[TerrainBase | FeatureKind, ...]:
        if category is SpriteCategory.TERRAIN:
            return tuple(self._terrains.values())
        if category is SpriteCategory.FEATURE:
            return tuple(self._features.values())
        # OBJECT / CREATURE — пока не реализованы (K6/K7).
        return ()


def _load_dir(dir_path: Path, adapter: TypeAdapter[_T]) -> dict[str, _T]:
    """Прочитать все ``*.yaml`` из каталога и провалидировать adapter-ом.

    Поле ``category`` в YAML — документационное (для CLI / human readability),
    модели его не знают, поэтому удаляем перед валидацией.
    """
    result: dict[str, _T] = {}
    if not dir_path.is_dir():
        return result
    for yaml_path in sorted(dir_path.glob("*.yaml")):
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw.pop("category", None)
        meta = adapter.validate_python(raw)
        result[meta.id] = meta
    return result


__all__ = ["YamlSpriteRegistry"]

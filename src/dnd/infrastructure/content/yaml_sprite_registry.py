"""YamlSpriteRegistry — читает data/content/sprites/{cat}/*.yaml.

Layout:

::

    sprites/
      terrain/{id}.yaml
      features/{id}.yaml
      objects/{id}.yaml
      creatures/{id}.yaml

Failure-fast: битый YAML или невалидная схема → ошибка в ``__init__``.
Отсутствующий каталог — это норма (контент опционален в раннем MVP),
просто пустой реестр.

K9 S1-2: objects/ и creatures/ грузятся как ``FeatureKind`` (у них
такой же набор полей: glyph, cover, blocks_los, blocks_passage_dirs,
passable_cost_ft) и сохраняются отдельно от ``_features``, чтобы CLI
``sprite list --category object|creature`` правильно категоризировал
вывод. Все четыре словаря открыты через ``get_feature`` (единый лукап
для legacy-вызовов) и ``list_by_category`` (для CLI).
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

    Хранит четыре категории отдельно (terrain / feature / object /
    creature), но object и creature валидируются той же схемой
    ``FeatureKind``: концептуально это «фичи на клетке» с тем же
    набором флагов (cover/LoS/passability). Единое API ``get_feature``
    ищет по объединению feature+object+creature — этого достаточно
    для editor'a и Battlefield, который оперирует Tile.features.
    """

    def __init__(self, sprites_dir: Path) -> None:
        self._terrains: dict[str, TerrainBase] = {}
        self._features: dict[str, FeatureKind] = {}
        self._objects: dict[str, FeatureKind] = {}
        self._creatures: dict[str, FeatureKind] = {}
        if sprites_dir.is_dir():
            self._terrains = _load_dir(sprites_dir / "terrain", _TERRAIN_ADAPTER)
            self._features = _load_dir(sprites_dir / "features", _FEATURE_ADAPTER)
            self._objects = _load_dir(sprites_dir / "objects", _FEATURE_ADAPTER)
            self._creatures = _load_dir(sprites_dir / "creatures", _FEATURE_ADAPTER)

    def get_terrain(self, id_: str) -> TerrainBase:
        try:
            return self._terrains[id_]
        except KeyError as exc:
            raise KeyError(f"unknown terrain sprite: {id_!r}") from exc

    def get_feature(self, id_: str) -> FeatureKind:
        # K9 S1-2: features + objects + creatures — единое пространство
        # имён для лукапа (editor / Tile-композиция). Конфликт ID между
        # категориями недопустим — упадёт раньше, в _load_dir.
        for src in (self._features, self._objects, self._creatures):
            if id_ in src:
                return src[id_]
        raise KeyError(f"unknown feature sprite: {id_!r}")

    def list_by_category(self, category: SpriteCategory) -> tuple[TerrainBase | FeatureKind, ...]:
        if category is SpriteCategory.TERRAIN:
            return tuple(self._terrains.values())
        if category is SpriteCategory.FEATURE:
            return tuple(self._features.values())
        if category is SpriteCategory.OBJECT:
            return tuple(self._objects.values())
        if category is SpriteCategory.CREATURE:
            return tuple(self._creatures.values())
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

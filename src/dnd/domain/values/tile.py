"""Tile — клетка карты как композит base + features.

Это центральный value-object новой картографической модели (этап K).
Заменяет старый плоский ``Terrain`` (который остаётся как
backwards-compatibility alias через готовые Tile-константы — см.
``tile_aliases.py``).

Семантика клетки (passable/LoS/cover/cost) **читается** из data,
а не наследуется. Никаких side-effects: Tile — pure frozen value.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from dnd.domain.values.direction import Direction
from dnd.domain.values.sprite_meta import FeatureKind, TerrainBase
from dnd.domain.values.terrain import CoverLevel


class Tile(BaseModel):
    """Композит: пол + наклеенные features.

    ``features`` — tuple для иммутабельности и хешируемости.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    base: TerrainBase
    features: tuple[FeatureKind, ...] = ()

    def allows_entry_from(self, direction: Direction) -> bool:
        """Можно ли войти в клетку с указанного направления.

        Возвращает False если:
        * база не passable (например, вода);
        * хоть один feature блокирует это направление
          (direction ∈ feature.blocks_passage_dirs).

        Колонна (`blocks_passage_dirs = все 4 ортогонала`) автоматически
        блокирует любой ortho-вход через per-direction-проверку.
        """
        if not self.base.passable:
            return False
        return all(direction not in f.blocks_passage_dirs for f in self.features)

    @property
    def blocks_los(self) -> bool:
        """Блокирует ли LoS любая из features. Base пол LoS не блокирует."""
        return any(f.blocks_los for f in self.features)

    def aggregate_cover(self) -> CoverLevel:
        """Максимальная cover из всех features (PHB-2024 стр. 25: «применяется
        только наиболее защищающая степень»)."""
        if not self.features:
            return CoverLevel.NONE
        return max((f.cover for f in self.features), key=lambda c: c.rank)

    def movement_cost_ft(self) -> int:
        """Стоимость входа в клетку (PHB-2024 стр. 23 «Difficult Terrain»).

        Правило книги: difficult НЕ стакается — клетка либо difficult, либо
        нет, независимо от количества источников. Берём максимум стоимости
        среди (base, *features), исключая 0-cost (непроходимые — отдельно
        через allows_entry_from).
        """
        candidates = [10 if self.base.difficult else 5]
        for f in self.features:
            if f.passable_cost_ft > 0:
                candidates.append(f.passable_cost_ft)
        return max(candidates)


__all__ = ["Tile"]

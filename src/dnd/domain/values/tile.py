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

_COVER_RANK: dict[CoverLevel, int] = {
    CoverLevel.NONE: 0,
    CoverLevel.HALF: 1,
    CoverLevel.THREE_QUARTERS: 2,
    CoverLevel.TOTAL: 3,
}


class Tile(BaseModel):
    """Композит: пол + наклеенные features.

    ``features`` — tuple для иммутабельности и хешируемости.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    base: TerrainBase
    features: tuple[FeatureKind, ...] = ()

    def allows_entry_from(self, direction: Direction) -> bool:
        """Можно ли войти в клетку с указанного направления.

        Семантика: если хоть один feature на клетке блокирует это
        направление — нельзя. Также если хоть один feature имеет
        ``passable_cost_ft=0`` И блокирует все 4 ортогонала — это
        непроходимая «масса» (column/wall full), любой вход блокирован.
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
        return max(
            (f.cover for f in self.features), key=lambda c: _COVER_RANK[c]
        )

    def movement_cost_ft(self) -> int:
        """Стоимость входа в клетку (PHB-2024). Базовый 5 фт;
        difficult terrain → 10 фт; features могут добавить (например,
        мебель — +5).

        Если хоть один feature ``passable_cost_ft == 0`` — клетка
        непроходима в принципе; вызывающий должен дополнительно
        проверять через ``allows_entry_from``.
        """
        base_cost = 10 if self.base.difficult else 5
        extra = sum(
            max(0, f.passable_cost_ft - 5)  # surplus сверх стандарта
            for f in self.features
            if f.passable_cost_ft > 0  # 0 = непроходимо, не считаем
        )
        return base_cost + extra


__all__ = ["Tile"]

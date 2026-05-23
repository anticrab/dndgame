"""Pure-функции для рендера Tile.

Без Textual — только данные → ASCII. Тестируется без поднятия app.
Используется в MapWidget (K5-T2) и CLI `dnd map show --zoom=medium`.
"""
from __future__ import annotations

from dnd.domain.values.tile import Tile


def render_tile_5x3(tile: Tile) -> tuple[str, str, str]:
    """Композит 5×3 ASCII клетки.

    Алгоритм: берём ``base.glyph_5x3`` как «фон»; features накладываются
    сверху в порядке tuple — не-пробельный символ feature перекрывает
    base. Несколько features на клетке — последний non-space побеждает.
    """
    rows = [list(r) for r in tile.base.glyph_5x3]
    for f in tile.features:
        for i, frow in enumerate(f.glyph_5x3):
            for j, ch in enumerate(frow):
                if ch != " ":
                    rows[i][j] = ch
    return ("".join(rows[0]), "".join(rows[1]), "".join(rows[2]))


__all__ = ["render_tile_5x3"]

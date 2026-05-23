"""MapWidget — ASCII-карта боя на small-zoom (1 клетка = 1 ячейка).

См. ``docs/TUI.md`` §6.1 и ``docs/UI.md`` §3 (визуальный язык).

Зачем здесь pure-функция :func:`render_battlefield`: она строит карту
по чистым данным (Battlefield + позиции фракций + cursor) и не
завязана на Textual. Это позволяет тестировать рендер юнит-тестом
без поднятия приложения. Сам виджет — тонкая обёртка над ней.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.widgets import Static

from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
from dnd.domain.values.terrain import CoverLevel, Terrain

if TYPE_CHECKING:
    from dnd.application.dto.ids import CreatureId
    from dnd.domain.entities.battlefield import Battlefield


# Выбираем символ по **свойствам** Terrain, а не по identity: каноничные
# константы (`WALL`/`CLOSED_DOOR`, `DIFFICULT`/`PIT`) могут совпадать
# по value (frozen dataclass с теми же полями), и dict[Terrain, str]
# схлопывал бы их к одной записи. Свойственный подход стабилен и не
# зависит от внутреннего реестра террейна.
def _terrain_glyph(terrain: Terrain) -> str:
    if not terrain.passable:
        if terrain.blocks_los:
            return "#"  # стена / закрытая дверь
        return "H"  # high cover (колонна / парапет)
    if terrain.cover is CoverLevel.HALF:
        return "="  # low cover (бортик / стол)
    if terrain.difficult:
        return ","  # difficult / pit — оба difficult, на small-zoom неразличимы
    return "."

_FACTION_GLYPH: dict[Faction, str] = {
    Faction.PARTY: "@",
    Faction.MONSTERS: "g",
    Faction.NEUTRAL: "n",
}

_FACTION_COLOR_TAG: dict[Faction, str] = {
    Faction.PARTY: "yellow",
    Faction.MONSTERS: "red",
    Faction.NEUTRAL: "cyan",
}

# Приоритет фракций для стека на одной клетке: PC > friendly > enemy >
# neutral > terrain. См. UI.md §3 и mockup B.1 (stack rendering).
_FACTION_PRIORITY: dict[Faction, int] = {
    Faction.PARTY: 3,
    Faction.NEUTRAL: 2,
    Faction.MONSTERS: 1,
}


def render_battlefield(
    battlefield: Battlefield,
    factions: dict[CreatureId, Faction],
    *,
    cursor: Square | None = None,
) -> Text:
    """Сформировать ``rich.Text`` с ASCII-картой.

    Алгоритм по клетке (x, y):

    1. Если на клетке есть существа — рисуем символ фракции с
       максимальным приоритетом. Если в стеке больше одного — вторая
       цифра не помещается на small-zoom, поэтому ставим символ
       старшего; стек в FOCUS-панели (пост-MVP).
    2. Иначе если есть `cursor == (x, y)` — рисуем ``X`` в инверсии.
    3. Иначе по типу террейна: стена / труднопроходимая / дверь /
       укрытие / яма / иначе `.` (пол).

    Возвращает ``rich.Text`` с inline-разметкой цветов; вставляется в
    Textual ``Static`` через ``widget.update(text)``.
    """
    out = Text()
    for y in range(battlefield.height):
        for x in range(battlefield.width):
            sq = Square(x, y)
            glyph, style = _cell_glyph(battlefield, factions, sq, cursor)
            out.append(glyph, style=style)
        if y < battlefield.height - 1:
            out.append("\n")
    return out


def _cell_glyph(
    battlefield: Battlefield,
    factions: dict[CreatureId, Faction],
    sq: Square,
    cursor: Square | None,
) -> tuple[str, str]:
    occupants = battlefield.creatures_at(sq)
    if occupants:
        top = _pick_top_creature(occupants, factions)
        faction = factions.get(top, Faction.NEUTRAL)
        glyph = _FACTION_GLYPH[faction]
        style = _FACTION_COLOR_TAG[faction]
        if sq == cursor:
            style = f"{style} reverse"
        return (glyph, style)

    if sq == cursor:
        return ("X", "magenta reverse")

    terrain = battlefield.terrain_at(sq)
    glyph = _terrain_glyph(terrain)
    style = "" if glyph == "." else "white"
    return (glyph, style)


def _pick_top_creature(
    occupants: tuple[CreatureId, ...],
    factions: dict[CreatureId, Faction],
) -> CreatureId:
    """Выбрать существо для рендера в стеке: по приоритету фракции,
    при равенстве — первое по порядку постановки (Battlefield хранит
    occupancy в order-preserving списке)."""
    return max(
        occupants,
        key=lambda cid: _FACTION_PRIORITY.get(factions.get(cid, Faction.NEUTRAL), 0),
    )


class MapWidget(Static):
    """Textual-обёртка над :func:`render_battlefield`.

    Перерисовка — через :meth:`refresh_from`. Виджет хранит ссылку
    на battlefield/factions/cursor; вызывающий слой (event_renderer)
    дёргает refresh_from после каждого хода или передвижения.
    """

    DEFAULT_CSS = ""

    def refresh_from(
        self,
        battlefield: Battlefield,
        factions: dict[CreatureId, Faction],
        *,
        cursor: Square | None = None,
    ) -> None:
        self.update(render_battlefield(battlefield, factions, cursor=cursor))


__all__ = ["MapWidget", "render_battlefield"]

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
from dnd.interfaces.tui.widgets.tile_renderer import render_tile_5x3

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
    with_color: bool = True,
    zoom: str = "small",
) -> Text:
    """Сформировать ``rich.Text`` с ASCII-картой.

    Алгоритм по клетке (x, y) для ``zoom='small'``:

    1. Если на клетке есть существа — рисуем символ фракции с
       максимальным приоритетом. Если в стеке больше одного — вторая
       цифра не помещается на small-zoom, поэтому ставим символ
       старшего; стек в FOCUS-панели (пост-MVP).
    2. Иначе если есть `cursor == (x, y)` — рисуем ``X`` в инверсии.
    3. Иначе по типу террейна: стена / труднопроходимая / дверь /
       укрытие / яма / иначе `.` (пол).

    ``with_color=False`` отключает цветовую разметку — клетки печатаются
    plain'ом + reverse/bold там, где это семантически (курсор).
    Этим путём идёт monochrome-тема (UI.md §3.2): семантика передаётся
    яркостью, не цветом.

    ``zoom='small'`` (default): 1 клетка = 1 ячейка терминала.
    ``zoom='medium'``: 1 клетка = 5×3 ячеек через
    :func:`render_tile_5x3` (K5-T1). Overlay существ/курсора —
    в центральной ячейке клетки (row=1, col=2).
    """
    if zoom == "medium":
        return _render_medium(
            battlefield, factions, cursor=cursor, with_color=with_color
        )
    out = Text()
    for y in range(battlefield.height):
        for x in range(battlefield.width):
            sq = Square(x, y)
            glyph, style = _cell_glyph(
                battlefield, factions, sq, cursor, with_color=with_color
            )
            out.append(glyph, style=style)
        if y < battlefield.height - 1:
            out.append("\n")
    return out


def _render_medium(
    battlefield: Battlefield,
    factions: dict[CreatureId, Faction],
    *,
    cursor: Square | None = None,
    with_color: bool = True,
) -> Text:
    """5×3 ячеек на клетку, без рамок (UI.md §3.1 «sprites склеиваются»).

    Алгоритм:
    * Каждая Tile рендерится через :func:`render_tile_5x3` → 3 строки
      по 5 chars.
    * Поверх — overlay creature (центр клетки) или cursor.
    * Строки клеток конкатенируются горизонтально; затем выводятся
      последовательно по 3 строки на ряд клеток.
    """
    del with_color  # цвета через CSS-классы в виджете; в pure-render — пусто
    out = Text()
    for y in range(battlefield.height):
        cell_rows: list[list[str]] = [[], [], []]
        for x in range(battlefield.width):
            sq = Square(x, y)
            tile = battlefield.tile_at(sq)
            glyphs = render_tile_5x3(tile)
            cells = [list(r) for r in glyphs]
            # Overlay: creature → центр 5×3 (row=1, col=2)
            occupants = battlefield.creatures_at(sq)
            if occupants:
                top = _pick_top_creature(occupants, factions)
                faction = factions.get(top, Faction.NEUTRAL)
                cells[1][2] = _FACTION_GLYPH[faction]
            elif cursor == sq:
                cells[1][2] = "X"
            for i in range(3):
                cell_rows[i].append("".join(cells[i]))
        for i, parts in enumerate(cell_rows):
            line = "".join(parts)
            out.append(line, style="")
            if not (y == battlefield.height - 1 and i == 2):
                out.append("\n")
    return out


def _cell_glyph(
    battlefield: Battlefield,
    factions: dict[CreatureId, Faction],
    sq: Square,
    cursor: Square | None,
    *,
    with_color: bool,
) -> tuple[str, str]:
    occupants = battlefield.creatures_at(sq)
    if occupants:
        top = _pick_top_creature(occupants, factions)
        faction = factions.get(top, Faction.NEUTRAL)
        glyph = _FACTION_GLYPH[faction]
        if with_color:
            style = _FACTION_COLOR_TAG[faction]
            if sq == cursor:
                style = f"{style} reverse"
        else:
            # monochrome: PC — bold; враг — reverse; нейтрал — обычный.
            base = {
                Faction.PARTY: "bold",
                Faction.MONSTERS: "reverse",
                Faction.NEUTRAL: "",
            }[faction]
            style = f"{base} reverse" if sq == cursor and base else (
                "reverse" if sq == cursor else base
            )
        return (glyph, style)

    if sq == cursor:
        return ("X", "magenta reverse") if with_color else ("X", "reverse")

    terrain = battlefield.terrain_at(sq)
    glyph = _terrain_glyph(terrain)
    if glyph == ".":
        return (glyph, "")
    return (glyph, "white") if with_color else (glyph, "dim")


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

    ``with_color`` определяется на лету по активной теме приложения
    (`color` → True, `monochrome` → False), чтобы тема реально
    влияла на содержимое карты, не только на рамку.
    """

    DEFAULT_CSS = ""

    def refresh_from(
        self,
        battlefield: Battlefield,
        factions: dict[CreatureId, Faction],
        *,
        cursor: Square | None = None,
    ) -> None:
        with_color = self._is_color_theme()
        self.update(
            render_battlefield(
                battlefield, factions, cursor=cursor, with_color=with_color
            )
        )

    def _is_color_theme(self) -> bool:
        # Theme name живёт в TuiApp как self.app._theme; если виджет
        # используется вне TuiApp (например, MovePicker под Pilot
        # без TuiApp) — fallback на True (цветной).
        app = self.app
        theme = getattr(app, "_theme", None)
        return theme != "monochrome"


__all__ = ["MapWidget", "render_battlefield"]

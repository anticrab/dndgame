"""MapWidget — ASCII-карта боя на small-zoom (1 клетка = 1 ячейка).

См. ``docs/TUI.md`` §6.1 и ``docs/UI.md`` §3 (визуальный язык).

Зачем здесь pure-функция :func:`render_battlefield`: она строит карту
по чистым данным (Battlefield + позиции фракций + cursor) и не
завязана на Textual. Это позволяет тестировать рендер юнит-тестом
без поднятия приложения. Сам виджет — тонкая обёртка над ней.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from rich.text import Text
from textual.widgets import Static

from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
from dnd.domain.values.terrain import CoverLevel, Terrain
from dnd.interfaces.tui.widgets.tile_renderer import render_tile_5x3

if TYPE_CHECKING:
    from dnd.domain.entities.battlefield import Battlefield
    from dnd.domain.values.ids import CreatureId


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
    visible_rect: tuple[int, int, int, int] | None = None,
    highlights: dict[Square, str] | None = None,
    path_preview: tuple[Square, ...] = (),
    path_styles: dict[Square, str] | None = None,
    is_alive: Callable[[CreatureId], bool] | None = None,
) -> Text:
    """Сформировать ``rich.Text`` с ASCII-картой.

    Алгоритм по клетке (x, y) для ``zoom='small'``:

    1. Если клетка входит в ``path_preview`` и на ней нет существ и она
       не курсор — рисуем ``·`` (зелёный при color, пустой стиль при mono).
    2. Иначе если на клетке есть существа — рисуем символ фракции с
       максимальным приоритетом. Если в стеке больше одного — вторая
       цифра не помещается на small-zoom, поэтому ставим символ
       старшего; стек в FOCUS-панели (пост-MVP).
    3. Иначе если есть `cursor == (x, y)` — рисуем ``X`` в инверсии.
    4. Иначе по типу террейна: стена / труднопроходимая / дверь /
       укрытие / яма / иначе `.` (пол).
    5. Поверх — применяем ``highlights[sq]`` (суммируем к style).

    ``with_color=False`` отключает цветовую разметку — клетки печатаются
    plain'ом + reverse/bold там, где это семантически (курсор).
    Этим путём идёт monochrome-тема (UI.md §3.2): семантика передаётся
    яркостью, не цветом.

    ``zoom='small'`` (default): 1 клетка = 1 ячейка терминала.
    ``zoom='medium'``: 1 клетка = 5×3 ячеек через
    :func:`render_tile_5x3` (K5-T1). Overlay существ/курсора —
    в центральной ячейке клетки (row=1, col=2).

    ``visible_rect`` — (x0, y0, x1, y1) окно видимой части в координатах
    битфилда. При ``None`` рендерится весь битфилд.

    ``path_preview`` — маршрут движения: клетки рисуются символом ``·``.
    Существа и курсор имеют приоритет над точками пути.

    ``highlights`` — подсветка целей: ``{sq: style}`` суммируется к стилю
    glyph'а (символ не меняется). Используется в TARGET mode (L1-T8).
    """
    if zoom == "medium":
        return _render_medium(
            battlefield, factions, cursor=cursor, with_color=with_color
        )
    if visible_rect is None:
        x0, y0, x1, y1 = 0, 0, battlefield.width, battlefield.height
    else:
        x0, y0, x1, y1 = visible_rect
        x1 = min(x1, battlefield.width)
        y1 = min(y1, battlefield.height)
    out = Text()
    path_set: frozenset[Square] = frozenset(path_preview)
    for y in range(y0, y1):
        for x in range(x0, x1):
            sq = Square(x, y)
            # path preview только если на клетке нет существа и она не курсор
            if sq in path_set and sq != cursor and not battlefield.creatures_at(sq):
                if path_styles and sq in path_styles:
                    style = path_styles[sq] if with_color else ""
                else:
                    style = "green" if with_color else ""
                out.append("·", style=style)
                continue
            glyph, style = _cell_glyph(
                battlefield, factions, sq, cursor,
                with_color=with_color, is_alive=is_alive,
            )
            if highlights and sq in highlights:
                extra = highlights[sq]
                style = f"{style} {extra}".strip() if style else extra
            out.append(glyph, style=style)
        if y < y1 - 1:
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
    is_alive: Callable[[CreatureId], bool] | None = None,
) -> tuple[str, str]:
    occupants = battlefield.creatures_at(sq)
    if occupants:
        # Если есть живой — показываем его (живой важнее трупа).
        # Если все на клетке мёртвые — рисуем труп (roguelike `%`).
        # is_alive=None ⇒ старое поведение (все живые); это нужно для
        # рендер-тестов без participants-контекста.
        living = [
            c for c in occupants if (is_alive is None or is_alive(c))
        ]
        if not living:
            # Все мёртвые — труп. Тёмно-красный приглушённый, чтобы не
            # «пёкло глаза» как живой враг и не сливалось с фоном.
            glyph = "%"
            if with_color:
                style = "red dim"
                if sq == cursor:
                    style = "red dim reverse"
            else:
                style = "reverse dim" if sq == cursor else "dim"
            return (glyph, style)
        top = _pick_top_creature(tuple(living), factions)
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

    Viewer-state хранится здесь (не в EventRenderer), чтобы hotkey-
    handler в :class:`BattleScreen` мог поменять zoom, не таская
    encounter через себя. L1: возврат к 1×1 — default ``"small"``
    (тактический обзор); medium 5×3 включается по `+`/`-`/`=`.
    """

    DEFAULT_CSS = ""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._zoom: str = "small"
        self._camera: Square = Square(0, 0)
        self._viewport_w: int = 80
        self._viewport_h: int = 24
        self._world_w: int = 0
        self._world_h: int = 0

    @property
    def zoom(self) -> str:
        return self._zoom

    def set_zoom(self, zoom: str) -> None:
        """Переключить zoom. Допустимы только ``"small"`` и ``"medium"``;
        иначе — :class:`ValueError` (защита от опечатки в коде-вызывателе).
        Перерисовка — за вызывающим (refresh_from случится на следующем
        event'е движка)."""
        if zoom not in ("small", "medium"):
            raise ValueError(f"unknown zoom: {zoom!r}")
        self._zoom = zoom

    def toggle_zoom(self) -> None:
        """Инвертировать zoom — удобство для hotkey'ев `+`/`-`/`=`."""
        self._zoom = "small" if self._zoom == "medium" else "medium"

    @property
    def camera(self) -> Square:
        return self._camera

    def set_viewport_size(self, w: int, h: int) -> None:
        """Размер видимой области в клетках. Вызывается из refresh_from
        на основе self.size (Textual layout). Tests дёргают напрямую."""
        if w < 1 or h < 1:
            raise ValueError(f"viewport size must be positive, got {w}×{h}")
        self._viewport_w = w
        self._viewport_h = h

    def set_world_size(self, w: int, h: int) -> None:
        """Размер мира (битфилда) в клетках. Нужен для clamp camera."""
        self._world_w = w
        self._world_h = h

    def pan(self, dx: int, dy: int) -> None:
        """Сместить камеру на (dx, dy). Clamp к [0, world-viewport]."""
        max_x = max(0, self._world_w - self._viewport_w)
        max_y = max(0, self._world_h - self._viewport_h)
        nx = max(0, min(self._camera.x + dx, max_x))
        ny = max(0, min(self._camera.y + dy, max_y))
        self._camera = Square(nx, ny)

    def center_on(self, sq: Square) -> None:
        """Центрировать viewport на клетке. Clamp к границам."""
        cx = sq.x - self._viewport_w // 2
        cy = sq.y - self._viewport_h // 2
        max_x = max(0, self._world_w - self._viewport_w)
        max_y = max(0, self._world_h - self._viewport_h)
        self._camera = Square(
            max(0, min(cx, max_x)),
            max(0, min(cy, max_y)),
        )

    def visible_rect(self) -> tuple[int, int, int, int]:
        """(x0, y0, x1, y1) — диапазон видимых клеток в координатах битфилда."""
        return (
            self._camera.x,
            self._camera.y,
            self._camera.x + self._viewport_w,
            self._camera.y + self._viewport_h,
        )

    def refresh_from(
        self,
        battlefield: Battlefield,
        factions: dict[CreatureId, Faction],
        *,
        cursor: Square | None = None,
        highlights: dict[Square, str] | None = None,
        path_preview: tuple[Square, ...] = (),
        path_styles: dict[Square, str] | None = None,
        follow: Square | None = None,
        is_alive: Callable[[CreatureId], bool] | None = None,
    ) -> None:
        self.set_world_size(battlefield.width, battlefield.height)
        # авто-расчёт viewport под размер виджета (если layout уже выполнен)
        if self.size.width and self.size.height:
            self.set_viewport_size(self.size.width, self.size.height)
        if follow is not None:
            self._auto_follow(follow)
        with_color = self._is_color_theme()
        self.update(render_battlefield(
            battlefield, factions,
            cursor=cursor, with_color=with_color, zoom=self._zoom,
            visible_rect=self.visible_rect() if self._zoom == "small" else None,
            highlights=highlights, path_preview=path_preview,
            path_styles=path_styles, is_alive=is_alive,
        ))

    def _auto_follow(self, target: Square) -> None:
        """Если target вышел за safe-zone (3 клетки от края viewport) — pan."""
        x0, y0, x1, y1 = self.visible_rect()
        safe = 3
        if (target.x < x0 + safe or target.x >= x1 - safe
                or target.y < y0 + safe or target.y >= y1 - safe):
            self.center_on(target)

    def _is_color_theme(self) -> bool:
        # Theme name живёт в TuiApp как self.app._theme; если виджет
        # используется вне TuiApp (например, в standalone-тестах рендера
        # под Pilot без TuiApp) — fallback на True (цветной).
        app = self.app
        theme = getattr(app, "_theme", None)
        return theme != "monochrome"


__all__ = ["MapWidget", "render_battlefield"]

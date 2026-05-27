"""EditorScreen — TUI-режим редактирования карты.

См. docs/TUI.md §7 (план в spec). Управление:

* arrows — двигать курсор по карте.
* enter — нанести current sprite (палитра) на клетку под курсором.

  - Для TERRAIN-палитры: меняет ``base``.
  - Для FEATURE-палитры: добавляет в ``features`` (toggle: если уже есть — убирает).

* tab — переключить TERRAIN ↔ FEATURE в палитре.
* s — сохранить через MapRepository.
* q — выход (без сохранения).

Дизайн: editor — отдельный Screen (не модал), нет связи с engine/encounter.
Состояние хранится локально (``_tiles``), сейв синхронный через переданный
:class:`MapRepository`. Карта рендерится через временный
:class:`Battlefield`, собранный из ``_tiles`` (без существ / без objects).
"""

from __future__ import annotations

import contextlib
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Label

from dnd.application.dto.map_dto import MapDocument, MapTileDoc
from dnd.application.ports.map_repository import MapRepository
from dnd.application.ports.sprite_registry import SpriteCategory, SpriteRegistry
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.square import Square
from dnd.domain.values.tile import Tile
from dnd.interfaces.tui.widgets import MapWidget
from dnd.interfaces.tui.widgets.palette_widget import PaletteWidget


class EditorScreen(Screen[None]):
    """Редактор карты — палитра слева, карта справа, статус снизу."""

    # priority=True: иначе ListView палитры (он фокусируется по
    # умолчанию) перехватывает стрелки/enter — paint и движение курсора
    # никогда бы не сработали. Приоритетные bindings экрана срабатывают
    # ПЕРЕД focused-виджетом. Навигация по самой палитре — Shift+стрелки
    # (см. action_palette_next/prev): editor — это map-edit, не list-pick.
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "move_cursor(0,-1)", "Up", priority=True),
        Binding("down", "move_cursor(0,1)", "Down", priority=True),
        Binding("left", "move_cursor(-1,0)", "Left", priority=True),
        Binding("right", "move_cursor(1,0)", "Right", priority=True),
        Binding("enter", "paint", "Paint", priority=True),
        Binding("tab", "toggle_category", "Cat", priority=True),
        Binding("shift+up", "palette_prev", "Palette↑", priority=True),
        Binding("shift+down", "palette_next", "Palette↓", priority=True),
        Binding("s", "save", "Save"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        *,
        doc: MapDocument,
        repo: MapRepository,
        sprites: SpriteRegistry,
    ) -> None:
        super().__init__()
        self._doc = doc
        self._repo = repo
        self._sprites = sprites
        self._cursor = Square(0, 0)
        self._tiles: list[MapTileDoc] = list(doc.tiles)
        self._dirty = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal():
            yield PaletteWidget(self._sprites, id="palette")
            with Vertical():
                yield MapWidget(id="map")
        yield Label("", id="editor-status")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_map()
        self._refresh_status()

    # --- actions ----------------------------------------------------

    def action_move_cursor(self, dx: int, dy: int) -> None:
        nx = max(0, min(self._doc.width - 1, self._cursor.x + dx))
        ny = max(0, min(self._doc.height - 1, self._cursor.y + dy))
        self._cursor = Square(nx, ny)
        self._refresh_map()
        self._refresh_status()

    def action_paint(self) -> None:
        palette = self.query_one("#palette", PaletteWidget)
        sprite_id = palette.selected_sprite_id()
        if sprite_id is None:
            return
        idx = next(
            (
                i
                for i, t in enumerate(self._tiles)
                if t.x == self._cursor.x and t.y == self._cursor.y
            ),
            None,
        )
        if palette.category is SpriteCategory.TERRAIN:
            base = sprite_id
            features: tuple[str, ...] = () if idx is None else self._tiles[idx].features
        else:  # FEATURE: toggle
            base = "floor" if idx is None else self._tiles[idx].base
            current_features: tuple[str, ...] = () if idx is None else self._tiles[idx].features
            if sprite_id in current_features:
                features = tuple(f for f in current_features if f != sprite_id)
            else:
                features = (*current_features, sprite_id)
        new_tile = MapTileDoc(x=self._cursor.x, y=self._cursor.y, base=base, features=features)
        if idx is None:
            self._tiles.append(new_tile)
        else:
            self._tiles[idx] = new_tile
        self._dirty = True
        self._refresh_map()
        self._refresh_status()

    def action_toggle_category(self) -> None:
        palette = self.query_one("#palette", PaletteWidget)
        palette.toggle_category()
        self._refresh_status()

    def action_palette_next(self) -> None:
        palette = self.query_one("#palette", PaletteWidget)
        palette.select_next()
        self._refresh_status()

    def action_palette_prev(self) -> None:
        palette = self.query_one("#palette", PaletteWidget)
        palette.select_prev()
        self._refresh_status()

    def action_save(self) -> None:
        new_doc = MapDocument(
            id=self._doc.id,
            name=self._doc.name,
            width=self._doc.width,
            height=self._doc.height,
            tiles=tuple(self._tiles),
            objects=self._doc.objects,
        )
        self._repo.save(new_doc)
        self._doc = new_doc
        self._dirty = False
        self._refresh_status()

    def action_quit(self) -> None:
        self.app.exit()

    # --- helpers ----------------------------------------------------

    def _refresh_map(self) -> None:
        # Соберём temporary Battlefield из текущих _tiles для render.
        bf = Battlefield(self._doc.width, self._doc.height)
        for t in self._tiles:
            try:
                base = self._sprites.get_terrain(t.base)
            except KeyError:
                continue
            features = []
            for fid in t.features:
                with contextlib.suppress(KeyError):
                    features.append(self._sprites.get_feature(fid))
            bf.set_tile(Square(t.x, t.y), Tile(base=base, features=tuple(features)))
        mw = self.query_one("#map", MapWidget)
        mw.refresh_from(bf, {}, cursor=self._cursor)

    def _refresh_status(self) -> None:
        status = self.query_one("#editor-status", Label)
        palette = self.query_one("#palette", PaletteWidget)
        sprite_id = palette.selected_sprite_id() or "(none)"
        dirty = "*" if self._dirty else " "
        status.update(
            f"[{dirty}] cursor: {self._cursor}  cat: {palette.category.value}  "
            f"sprite: {sprite_id}  tiles: {len(self._tiles)}  "
            f"[s] save  [q] quit  [tab] cat  [enter] paint"
        )


__all__ = ["EditorScreen"]

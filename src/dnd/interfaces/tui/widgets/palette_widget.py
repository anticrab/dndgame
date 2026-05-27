"""PaletteWidget — выбор sprite для editor.

Показывает плоский список доступных sprites текущей категории
(terrain/feature). Пользователь выбирает текущий sprite через ↑/↓,
переключает категорию через Tab.

Виджет — тонкая обёртка над ``ListView`` + лейблом категории; никакой
бизнес-логики (выбор/применение) тут нет — это делает EditorScreen,
обращаясь к :meth:`selected_sprite_id` и :meth:`toggle_category`.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, ListItem, ListView

from dnd.application.ports.sprite_registry import SpriteCategory, SpriteRegistry


class PaletteWidget(Vertical):
    """Палитра sprites: категория + список."""

    DEFAULT_CSS = ""

    def __init__(
        self,
        registry: SpriteRegistry,
        *,
        category: SpriteCategory = SpriteCategory.TERRAIN,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._registry = registry
        self._category = category

    def compose(self) -> ComposeResult:
        yield Label(f"Palette: {self._category.value}", id="palette-cat")
        sprites = self._registry.list_by_category(self._category)
        yield ListView(
            *(ListItem(Label(f"{s.glyph_1x1} {s.id}")) for s in sprites),
            id="palette-list",
        )

    def selected_sprite_id(self) -> str | None:
        """Текущий выбранный sprite id, или None если список пуст.

        ListView до первой навигации хранит ``index=None`` — но в editor
        это вынуждало бы игрока «прокликать» список перед первым paint.
        Поэтому treat ``None`` как «первый элемент»: интуитивно совпадает
        с визуальным выделением первой строки сразу после монтирования.
        """
        sprites = self._registry.list_by_category(self._category)
        if not sprites:
            return None
        lv = self.query_one("#palette-list", ListView)
        idx = lv.index if lv.index is not None else 0
        if 0 <= idx < len(sprites):
            return sprites[idx].id
        return None

    def toggle_category(self) -> None:
        """Переключить TERRAIN ↔ FEATURE (object/creature пока не редактируем)."""
        self._category = (
            SpriteCategory.FEATURE
            if self._category is SpriteCategory.TERRAIN
            else SpriteCategory.TERRAIN
        )
        # Перерисовка через recompose
        from contextlib import suppress

        with suppress(Exception):
            self.query_one("#palette-cat", Label).update(f"Palette: {self._category.value}")
            lv = self.query_one("#palette-list", ListView)
            lv.clear()
            for s in self._registry.list_by_category(self._category):
                lv.append(ListItem(Label(f"{s.glyph_1x1} {s.id}")))

    def select_next(self) -> None:
        """Сдвинуть выделение в палитре на следующий sprite (с wrap)."""
        sprites = self._registry.list_by_category(self._category)
        if not sprites:
            return
        lv = self.query_one("#palette-list", ListView)
        cur = lv.index if lv.index is not None else 0
        lv.index = (cur + 1) % len(sprites)

    def select_prev(self) -> None:
        """Сдвинуть выделение в палитре на предыдущий sprite (с wrap)."""
        sprites = self._registry.list_by_category(self._category)
        if not sprites:
            return
        lv = self.query_one("#palette-list", ListView)
        cur = lv.index if lv.index is not None else 0
        lv.index = (cur - 1) % len(sprites)

    @property
    def category(self) -> SpriteCategory:
        return self._category


__all__ = ["PaletteWidget"]

"""Тесты pure-функции ``render_battlefield`` — без поднятия Textual.

Покрытие:
* пустая карта показывается одними точками;
* стены / труднопроходимая / cover / pit / door рисуются своими символами;
* существа разных фракций — своими буквами;
* приоритет стека: PC > NEUTRAL > MONSTERS;
* курсор на пустой клетке рисуется ``X``, на занятой — `reverse`-стиль;
* координаты идут построчно (`\n` между строками, не в конце).
"""

from __future__ import annotations

import pytest

from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.domain.values.terrain import (
    CLOSED_DOOR,
    DIFFICULT,
    HIGH_COVER,
    LOW_COVER,
    PIT,
    WALL,
)
from dnd.interfaces.tui.widgets.map_widget import render_battlefield

# WALL и CLOSED_DOOR — равны по value (frozen dataclass), на small-zoom
# их различить нельзя; рендер для обоих даёт '#'. То же про DIFFICULT и
# PIT: оба `difficult=True, passable=True` → ','. Это не баг, а
# естественное следствие модели Terrain как чистого value-type.


def _empty_factions() -> dict[CreatureId, Faction]:
    return {}


def test_empty_battlefield_renders_dots() -> None:
    bf = Battlefield(3, 2)
    text = render_battlefield(bf, _empty_factions())
    assert text.plain == "...\n..."


def test_terrain_glyphs_by_property() -> None:
    """Терайн рендерится по свойствам, не по identity константы.

    `WALL` ≡ `CLOSED_DOOR` (оба непроходимы и блокируют LoS) → '#'.
    `DIFFICULT` ≡ `PIT` (оба difficult+passable) → ','. На small-zoom
    эти пары неразличимы — это сознательное упрощение.
    """
    bf = Battlefield(7, 1)
    bf.set_terrain(Square(0, 0), WALL)
    bf.set_terrain(Square(1, 0), DIFFICULT)
    bf.set_terrain(Square(2, 0), CLOSED_DOOR)
    bf.set_terrain(Square(3, 0), LOW_COVER)
    bf.set_terrain(Square(4, 0), HIGH_COVER)
    bf.set_terrain(Square(5, 0), PIT)
    # Square(6, 0) — пол, остаётся `.`
    text = render_battlefield(bf, _empty_factions())
    assert text.plain == "#,#=H,."


def test_pc_and_enemy_glyphs() -> None:
    bf = Battlefield(3, 1)
    pc = CreatureId("hero")
    enemy = CreatureId("goblin")
    bf.place_creature(pc, Square(0, 0))
    bf.place_creature(enemy, Square(2, 0))
    factions = {pc: Faction.PARTY, enemy: Faction.MONSTERS}
    text = render_battlefield(bf, factions)
    assert text.plain == "@.g"


def test_stack_priority_pc_wins_over_neutral_and_enemy() -> None:
    """На одной клетке PC + союзный neutral + враг — побеждает PC (`@`)."""
    bf = Battlefield(1, 1)
    pc = CreatureId("hero")
    ally = CreatureId("dog")
    enemy = CreatureId("goblin")
    # Кладём в обратном порядке приоритета, чтобы убедиться: побеждает
    # тот, чья фракция выше — а не тот, кто пришёл последним.
    bf.place_creature(enemy, Square(0, 0))
    bf.place_creature(ally, Square(0, 0))
    bf.place_creature(pc, Square(0, 0))
    factions = {
        pc: Faction.PARTY,
        ally: Faction.NEUTRAL,
        enemy: Faction.MONSTERS,
    }
    text = render_battlefield(bf, factions)
    assert text.plain == "@"


def test_cursor_on_empty_cell_is_X() -> None:
    bf = Battlefield(3, 1)
    text = render_battlefield(bf, _empty_factions(), cursor=Square(1, 0))
    assert text.plain == ".X."


def test_cursor_on_creature_uses_reverse_style() -> None:
    bf = Battlefield(3, 1)
    pc = CreatureId("hero")
    bf.place_creature(pc, Square(1, 0))
    factions = {pc: Faction.PARTY}
    text = render_battlefield(bf, factions, cursor=Square(1, 0))
    # символ остаётся @, но к стилю добавляется reverse
    assert text.plain == ".@."
    middle_style = str(text.get_style_at_offset(_dummy_console(), 1))
    assert "reverse" in middle_style


def test_no_trailing_newline_at_end() -> None:
    """Последняя строка не должна заканчиваться `\\n` — это упрощает
    вставку в Static."""
    bf = Battlefield(2, 3)
    text = render_battlefield(bf, _empty_factions())
    assert not text.plain.endswith("\n")
    assert text.plain.count("\n") == 2  # height-1 переводов строки


@pytest.fixture
def _dummy_console_fixture() -> object:
    """rich.Text.get_style_at_offset требует Console для разрешения тем."""
    from rich.console import Console

    return Console()


def _dummy_console() -> object:
    from rich.console import Console

    return Console()


def test_render_medium_uses_tile_when_set() -> None:
    """Medium-zoom: 5×3 ячеек на клетку через Tile."""
    from dnd.domain.values.tile_aliases import WALL_TILE

    bf = Battlefield(3, 1)
    bf.set_tile(Square(1, 0), WALL_TILE)
    text = render_battlefield(bf, {}, zoom="medium")
    # 3 строки по 15 ячеек (3 клетки × 5).
    assert text.plain.count("\n") == 2  # 3 строки → 2 \n
    lines = text.plain.split("\n")
    assert all(len(line) == 15 for line in lines), [(len(ln), ln) for ln in lines]
    # Стена в средней клетке — заполнена █████.
    assert "█" in lines[0]


def test_render_medium_default_floor_empty() -> None:
    """Default tile (FLOOR_TILE) — 5 пробелов на клетку."""
    bf = Battlefield(2, 1)
    text = render_battlefield(bf, {}, zoom="medium")
    lines = text.plain.split("\n")
    assert lines == ["          ", "          ", "          "]  # 10 spaces each


def test_render_medium_creature_in_center() -> None:
    """Creature на клетке: символ фракции в центре 5×3 (row=1, col=2)."""
    bf = Battlefield(1, 1)
    pc = CreatureId("hero")
    bf.place_creature(pc, Square(0, 0))
    factions = {pc: Faction.PARTY}
    text = render_battlefield(bf, factions, zoom="medium")
    lines = text.plain.split("\n")
    # Row 1, col 2 = '@'
    assert lines[1][2] == "@"


def test_render_medium_cursor_on_empty_cell() -> None:
    """Cursor на пустой клетке — 'X' в центре."""
    bf = Battlefield(1, 1)
    text = render_battlefield(bf, {}, cursor=Square(0, 0), zoom="medium")
    lines = text.plain.split("\n")
    assert lines[1][2] == "X"


def test_dead_creature_renders_as_corpse_glyph() -> None:
    """Если is_alive(cid) == False — клетка рисуется как `%`,
    а не как глиф фракции. Через cell всё ещё видно занятость
    (на случай если игрок хочет понять, кто там лежал)."""
    from dnd.domain.entities.battlefield import Battlefield
    from dnd.domain.values.faction import Faction
    from dnd.domain.values.ids import CreatureId
    from dnd.domain.values.square import Square

    bf = Battlefield(3, 1)
    bf.place_creature(CreatureId("corpse"), Square(1, 0))
    factions = {CreatureId("corpse"): Faction.MONSTERS}
    text = render_battlefield(
        bf,
        factions,
        with_color=False,
        is_alive=lambda cid: False,
    )
    plain = text.plain
    # 3-cell ряд, центральная клетка должна быть %.
    assert plain[1] == "%"


def test_living_overrides_dead_on_same_square() -> None:
    """Если на клетке и живой, и труп — рисуется живой."""
    from dnd.domain.entities.battlefield import Battlefield
    from dnd.domain.values.faction import Faction
    from dnd.domain.values.ids import CreatureId
    from dnd.domain.values.square import Square

    bf = Battlefield(3, 1)
    bf.place_creature(CreatureId("corpse"), Square(1, 0))
    bf.place_creature(CreatureId("alive"), Square(1, 0))
    factions = {
        CreatureId("corpse"): Faction.MONSTERS,
        CreatureId("alive"): Faction.PARTY,
    }
    text = render_battlefield(
        bf,
        factions,
        with_color=False,
        is_alive=lambda cid: cid == CreatureId("alive"),
    )
    # Должны увидеть PC-глиф `@`, не `%`.
    assert "@" in text.plain
    assert "%" not in text.plain

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

from dnd.application.dto.ids import CreatureId
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.faction import Faction
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

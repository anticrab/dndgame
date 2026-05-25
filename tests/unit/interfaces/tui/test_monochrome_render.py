"""Тест: render_battlefield с with_color=False реально опускает цвета.

Это закрывает аудит-17 TUI-T001: monochrome-тема не должна красить
клетки карты (это нарушало бы инвариант «семантика — яркостью, не
цветом»).
"""

from __future__ import annotations

from rich.console import Console

from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.interfaces.tui.widgets.map_widget import render_battlefield


def _has_color(text, console: Console, offset: int) -> bool:
    style = str(text.get_style_at_offset(console, offset))
    return any(c in style for c in ("yellow", "red", "cyan", "magenta"))


def test_color_mode_uses_color_styles() -> None:
    bf = Battlefield(3, 1)
    pc = CreatureId("hero")
    enemy = CreatureId("goblin")
    bf.place_creature(pc, Square(0, 0))
    bf.place_creature(enemy, Square(2, 0))
    factions = {pc: Faction.PARTY, enemy: Faction.MONSTERS}
    text = render_battlefield(bf, factions, with_color=True)
    c = Console()
    # Под цветной темой PC/враг получают цветовые стили.
    assert _has_color(text, c, 0)  # PC @
    assert _has_color(text, c, 2)  # враг g


def test_mono_mode_drops_color_styles() -> None:
    bf = Battlefield(3, 1)
    pc = CreatureId("hero")
    enemy = CreatureId("goblin")
    bf.place_creature(pc, Square(0, 0))
    bf.place_creature(enemy, Square(2, 0))
    factions = {pc: Faction.PARTY, enemy: Faction.MONSTERS}
    text = render_battlefield(bf, factions, with_color=False)
    c = Console()
    # Под monochrome — ни одна клетка не должна нести цветовой стиль.
    assert not _has_color(text, c, 0), "PC должна быть без цвета"
    assert not _has_color(text, c, 2), "Враг должен быть без цвета"


def test_mono_pc_is_bold() -> None:
    bf = Battlefield(1, 1)
    pc = CreatureId("hero")
    bf.place_creature(pc, Square(0, 0))
    text = render_battlefield(bf, {pc: Faction.PARTY}, with_color=False)
    c = Console()
    style = str(text.get_style_at_offset(c, 0))
    assert "bold" in style


def test_mono_enemy_is_reverse() -> None:
    bf = Battlefield(1, 1)
    enemy = CreatureId("goblin")
    bf.place_creature(enemy, Square(0, 0))
    text = render_battlefield(bf, {enemy: Faction.MONSTERS}, with_color=False)
    c = Console()
    style = str(text.get_style_at_offset(c, 0))
    assert "reverse" in style

"""render_battlefield: клипует к visible_rect + рисует path_preview + highlights."""

from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.interfaces.tui.widgets.map_widget import render_battlefield


def test_render_clips_to_visible_rect() -> None:
    bf = Battlefield(20, 20)
    rendered = render_battlefield(
        bf,
        factions={},
        with_color=False,
        zoom="small",
        visible_rect=(10, 10, 20, 20),  # 10×10 окно
    )
    lines = str(rendered).split("\n")
    assert len(lines) == 10, f"expected 10 rows in viewport, got {len(lines)}"
    assert len(lines[0]) == 10, f"expected 10 cols, got {len(lines[0])}"


def test_render_full_when_rect_none() -> None:
    bf = Battlefield(7, 5)
    rendered = render_battlefield(bf, factions={}, with_color=False, zoom="small")
    lines = str(rendered).split("\n")
    assert len(lines) == 5
    assert len(lines[0]) == 7


def test_render_path_preview_draws_middle_dot() -> None:
    bf = Battlefield(10, 10)
    rendered = render_battlefield(
        bf,
        factions={},
        with_color=False,
        zoom="small",
        path_preview=(Square(2, 2), Square(3, 2)),
    )
    lines = str(rendered).split("\n")
    # на (2,2) и (3,2) должны быть точки '·' пути
    assert lines[2][2] == "·", f"expected '·' at (2,2), got {lines[2][2]!r}"
    assert lines[2][3] == "·", f"expected '·' at (3,2), got {lines[2][3]!r}"


def test_path_preview_does_not_override_creature() -> None:
    """Если на клетке стоит существо — рисуем существо, не точку пути."""
    bf = Battlefield(10, 10)
    cid = CreatureId("c1")
    bf.place_creature(cid, Square(2, 2))
    rendered = render_battlefield(
        bf,
        factions={cid: Faction.PARTY},
        with_color=False,
        zoom="small",
        path_preview=(Square(2, 2),),
    )
    lines = str(rendered).split("\n")
    # на (2,2) должно быть '@' (PC), а не '·'
    assert lines[2][2] == "@", f"expected '@' at (2,2), got {lines[2][2]!r}"


def test_highlights_applied() -> None:
    """highlights={sq: style} применяется поверх terrain glyph (не меняет символ)."""
    bf = Battlefield(10, 10)
    # отрисуй с highlights — проверим, что symbol на месте, через repr Text
    rendered = render_battlefield(
        bf,
        factions={},
        with_color=False,
        zoom="small",
        highlights={Square(3, 3): "bold"},
    )
    # просто smoke: рендер прошёл, и нужный символ floor '.' на месте
    lines = str(rendered).split("\n")
    assert lines[3][3] == "."

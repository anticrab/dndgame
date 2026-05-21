"""Тесты Battlefield — поле боя на квадратной сетке.

Покрытие:

* размеры и границы (in_bounds);
* террейн (set_terrain, terrain_at, вне границ → WALL-подобный);
* размещение существ: place, move, remove, multiple per cell (Q1);
* LoS: прямая, через стену блок, через open door open, диагональ,
  цель = источник;
* cover: возвращает наибольший на линии (книга стр. 25);
* threatens_squares: 5 фут и 10 фут (reach), границы карты;
* property-based: LoS симметричен; cover симметричен; threatens
  не выходит за карту.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dnd.application.dto.ids import CreatureId
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.square import Square
from dnd.domain.values.terrain import (
    CLOSED_DOOR,
    DIFFICULT,
    FLOOR,
    HIGH_COVER,
    LOW_COVER,
    WALL,
    CoverLevel,
)

# -- размеры и границы ---------------------------------------------------


def test_constructor_rejects_zero_or_negative_size() -> None:
    with pytest.raises(ValueError, match=">= 1"):
        Battlefield(0, 10)
    with pytest.raises(ValueError, match=">= 1"):
        Battlefield(10, -1)


def test_in_bounds() -> None:
    bf = Battlefield(width=10, height=8)
    assert bf.in_bounds(Square(0, 0)) is True
    assert bf.in_bounds(Square(9, 7)) is True
    assert bf.in_bounds(Square(10, 0)) is False
    assert bf.in_bounds(Square(0, 8)) is False
    assert bf.in_bounds(Square(-1, 0)) is False


def test_width_height_properties() -> None:
    bf = Battlefield(width=12, height=8)
    assert bf.width == 12
    assert bf.height == 8


# -- террейн -------------------------------------------------------------


def test_default_terrain_is_floor() -> None:
    bf = Battlefield(10, 10)
    assert bf.terrain_at(Square(5, 5)) is FLOOR


def test_set_and_get_terrain() -> None:
    bf = Battlefield(10, 10)
    bf.set_terrain(Square(3, 4), WALL)
    assert bf.terrain_at(Square(3, 4)) is WALL


def test_setting_floor_clears_dict() -> None:
    """FLOOR — это «по умолчанию»; явная установка FLOOR обнуляет
    клетку (внутренний dict не растёт)."""
    bf = Battlefield(10, 10)
    bf.set_terrain(Square(3, 4), WALL)
    bf.set_terrain(Square(3, 4), FLOOR)
    assert bf.terrain_at(Square(3, 4)) is FLOOR


def test_set_terrain_out_of_bounds_raises() -> None:
    bf = Battlefield(5, 5)
    with pytest.raises(ValueError, match="out of bounds"):
        bf.set_terrain(Square(10, 10), WALL)


def test_terrain_out_of_bounds_is_wall_like() -> None:
    """За границей карты — стена (для упрощения LoS-алгоритма)."""
    bf = Battlefield(5, 5)
    out_terrain = bf.terrain_at(Square(-1, 0))
    assert out_terrain.passable is False
    assert out_terrain.blocks_los is True


# -- размещение существ -------------------------------------------------


def test_place_and_query_position() -> None:
    bf = Battlefield(10, 10)
    aelar = CreatureId("aelar")
    bf.place_creature(aelar, Square(3, 4))
    assert bf.position_of(aelar) == Square(3, 4)
    assert bf.has_creature(aelar) is True
    assert bf.creatures_at(Square(3, 4)) == (aelar,)


def test_multiple_creatures_in_same_square() -> None:
    """Q1: несколько существ на одной клетке допустимо."""
    bf = Battlefield(10, 10)
    a = CreatureId("a")
    b = CreatureId("b")
    bf.place_creature(a, Square(2, 2))
    bf.place_creature(b, Square(2, 2))
    assert set(bf.creatures_at(Square(2, 2))) == {a, b}


def test_placing_on_wall_raises() -> None:
    bf = Battlefield(10, 10)
    bf.set_terrain(Square(5, 5), WALL)
    with pytest.raises(ValueError, match="impassable"):
        bf.place_creature(CreatureId("x"), Square(5, 5))


def test_placing_out_of_bounds_raises() -> None:
    bf = Battlefield(5, 5)
    with pytest.raises(ValueError, match="out of bounds"):
        bf.place_creature(CreatureId("x"), Square(10, 10))


def test_replace_creature_moves_it() -> None:
    """place_creature повторно для того же ID = переместить."""
    bf = Battlefield(10, 10)
    a = CreatureId("a")
    bf.place_creature(a, Square(1, 1))
    bf.place_creature(a, Square(5, 5))
    assert bf.position_of(a) == Square(5, 5)
    assert bf.creatures_at(Square(1, 1)) == ()
    assert bf.creatures_at(Square(5, 5)) == (a,)


def test_move_creature() -> None:
    bf = Battlefield(10, 10)
    a = CreatureId("a")
    bf.place_creature(a, Square(1, 1))
    bf.move_creature(a, Square(2, 2))
    assert bf.position_of(a) == Square(2, 2)


def test_move_creature_not_on_battlefield_raises() -> None:
    bf = Battlefield(10, 10)
    with pytest.raises(KeyError, match="not on the battlefield"):
        bf.move_creature(CreatureId("ghost"), Square(2, 2))


def test_remove_creature() -> None:
    bf = Battlefield(10, 10)
    a = CreatureId("a")
    bf.place_creature(a, Square(3, 3))
    bf.remove_creature(a)
    assert bf.has_creature(a) is False
    assert bf.creatures_at(Square(3, 3)) == ()


def test_remove_unknown_raises() -> None:
    bf = Battlefield(10, 10)
    with pytest.raises(KeyError):
        bf.remove_creature(CreatureId("ghost"))


def test_position_of_unknown_raises() -> None:
    bf = Battlefield(10, 10)
    with pytest.raises(KeyError):
        bf.position_of(CreatureId("ghost"))


def test_creatures_at_returns_immutable_snapshot() -> None:
    """Вызывающий не должен мочь повредить внутренний список."""
    bf = Battlefield(10, 10)
    bf.place_creature(CreatureId("a"), Square(1, 1))
    snap = bf.creatures_at(Square(1, 1))
    assert isinstance(snap, tuple)
    # tuple — иммутабельна по природе; повторный запрос даёт ту же
    # последовательность.
    assert bf.creatures_at(Square(1, 1)) == snap


def test_occupied_squares() -> None:
    bf = Battlefield(10, 10)
    bf.place_creature(CreatureId("a"), Square(1, 1))
    bf.place_creature(CreatureId("b"), Square(5, 5))
    assert bf.occupied_squares == frozenset({Square(1, 1), Square(5, 5)})


# -- LoS ----------------------------------------------------------------


def test_los_same_square_is_true() -> None:
    bf = Battlefield(10, 10)
    assert bf.line_of_sight(Square(5, 5), Square(5, 5)) is True


def test_los_open_field() -> None:
    bf = Battlefield(10, 10)
    assert bf.line_of_sight(Square(0, 0), Square(9, 9)) is True


@pytest.mark.rules
def test_los_blocked_by_wall_between() -> None:
    """Стена между источником и целью блокирует LoS."""
    bf = Battlefield(10, 10)
    bf.set_terrain(Square(5, 0), WALL)
    assert bf.line_of_sight(Square(0, 0), Square(9, 0)) is False


def test_los_not_blocked_by_endpoint_terrain() -> None:
    """Стена на самой цели — LoS есть (книга: «вы видите то, на что
    навели»)."""
    bf = Battlefield(10, 10)
    bf.set_terrain(Square(9, 0), WALL)
    assert bf.line_of_sight(Square(0, 0), Square(9, 0)) is True


def test_los_blocked_by_closed_door() -> None:
    bf = Battlefield(10, 10)
    bf.set_terrain(Square(5, 5), CLOSED_DOOR)
    assert bf.line_of_sight(Square(3, 5), Square(7, 5)) is False


def test_los_through_high_cover_not_blocked() -> None:
    """HighCover не блокирует LoS (стрелять между можно), но даёт cover."""
    bf = Battlefield(10, 10)
    bf.set_terrain(Square(5, 5), HIGH_COVER)
    assert bf.line_of_sight(Square(3, 5), Square(7, 5)) is True


def test_los_diagonal_open() -> None:
    bf = Battlefield(10, 10)
    assert bf.line_of_sight(Square(0, 0), Square(5, 5)) is True


# -- cover --------------------------------------------------------------


@pytest.mark.rules
def test_cover_against_low_cover_is_half() -> None:
    """Книга стр. 25: half cover за LowCover-объектом."""
    bf = Battlefield(10, 10)
    bf.set_terrain(Square(5, 5), LOW_COVER)
    assert bf.cover_against(Square(3, 5), Square(7, 5)) is CoverLevel.HALF


@pytest.mark.rules
def test_cover_against_high_cover_is_three_quarters() -> None:
    bf = Battlefield(10, 10)
    bf.set_terrain(Square(5, 5), HIGH_COVER)
    assert bf.cover_against(Square(3, 5), Square(7, 5)) is CoverLevel.THREE_QUARTERS


@pytest.mark.rules
def test_cover_picks_strongest_along_line() -> None:
    """Книга стр. 25: «если несколько источников укрытия — берётся
    самое сильное»."""
    bf = Battlefield(10, 10)
    bf.set_terrain(Square(4, 5), LOW_COVER)  # half
    bf.set_terrain(Square(5, 5), HIGH_COVER)  # three_quarters
    assert bf.cover_against(Square(2, 5), Square(7, 5)) is CoverLevel.THREE_QUARTERS


def test_cover_no_obstacles_is_none() -> None:
    bf = Battlefield(10, 10)
    assert bf.cover_against(Square(0, 0), Square(9, 9)) is CoverLevel.NONE


def test_cover_same_square_is_none() -> None:
    bf = Battlefield(10, 10)
    assert bf.cover_against(Square(3, 3), Square(3, 3)) is CoverLevel.NONE


def test_cover_endpoint_terrain_does_not_count() -> None:
    """Cover на самой цели не считается (как и для LoS)."""
    bf = Battlefield(10, 10)
    bf.set_terrain(Square(7, 5), HIGH_COVER)
    assert bf.cover_against(Square(3, 5), Square(7, 5)) is CoverLevel.NONE


# -- threatens_squares --------------------------------------------------


@pytest.mark.rules
def test_threatens_reach_5ft_is_8_neighbours() -> None:
    """5 фут reach = 1 клетка = 8 соседних клеток (книга стр. 25)."""
    bf = Battlefield(10, 10)
    a = CreatureId("a")
    bf.place_creature(a, Square(5, 5))
    threatened = bf.threatens_squares(a)
    assert len(threatened) == 8
    assert Square(5, 5) not in threatened
    assert Square(4, 5) in threatened
    assert Square(6, 6) in threatened


@pytest.mark.rules
def test_threatens_reach_10ft_is_24_squares() -> None:
    """10 фут reach (глефа, копьё, большие существа) = 2 клетки =
    5×5 квадрат минус центральная = 24 клетки."""
    bf = Battlefield(10, 10)
    a = CreatureId("a")
    bf.place_creature(a, Square(5, 5))
    threatened = bf.threatens_squares(a, reach_ft=10)
    assert len(threatened) == 24


def test_threatens_clamped_to_battlefield_borders() -> None:
    """В углу карты threatens_squares содержит только валидные клетки."""
    bf = Battlefield(10, 10)
    a = CreatureId("a")
    bf.place_creature(a, Square(0, 0))
    threatened = bf.threatens_squares(a)
    # В углу — только 3 соседа в карте: (1,0), (0,1), (1,1).
    assert threatened == frozenset({Square(1, 0), Square(0, 1), Square(1, 1)})


def test_threatens_rejects_non_multiple_of_5_reach() -> None:
    bf = Battlefield(10, 10)
    bf.place_creature(CreatureId("a"), Square(5, 5))
    with pytest.raises(ValueError):
        bf.threatens_squares(CreatureId("a"), reach_ft=7)


def test_threatens_unknown_creature_raises() -> None:
    bf = Battlefield(10, 10)
    with pytest.raises(KeyError):
        bf.threatens_squares(CreatureId("ghost"))


# -- property-based -----------------------------------------------------

_within_bf = st.integers(min_value=0, max_value=19)
_squares = st.builds(Square, x=_within_bf, y=_within_bf)


@pytest.mark.property
@given(a=_squares, b=_squares)
def test_property_los_symmetric_on_empty_map(a: Square, b: Square) -> None:
    """LoS симметричен на пустой карте без препятствий: A видит B ⇔ B видит A."""
    bf = Battlefield(20, 20)
    assert bf.line_of_sight(a, b) == bf.line_of_sight(b, a)


@pytest.mark.property
@given(a=_squares, b=_squares)
def test_property_cover_no_obstacles_is_none(a: Square, b: Square) -> None:
    """На пустой карте cover всегда NONE."""
    bf = Battlefield(20, 20)
    assert bf.cover_against(a, b) is CoverLevel.NONE


@pytest.mark.property
@given(centre=_squares)
def test_property_threatens_stays_in_bounds(centre: Square) -> None:
    """threatens_squares всегда возвращает только клетки в пределах
    карты."""
    bf = Battlefield(20, 20)
    bf.place_creature(CreatureId("a"), centre)
    threatened = bf.threatens_squares(CreatureId("a"))
    for sq in threatened:
        assert bf.in_bounds(sq)


@pytest.mark.property
@given(centre=_squares)
def test_property_threatens_excludes_self(centre: Square) -> None:
    bf = Battlefield(20, 20)
    bf.place_creature(CreatureId("a"), centre)
    assert centre not in bf.threatens_squares(CreatureId("a"))


# -- интеграция: реалистичный сценарий ----------------------------------


@pytest.mark.rules
def test_book_scenario_archer_behind_wall_blocked() -> None:
    """Сценарий: лучник за стеной, цель с другой стороны.

    Карта 10×3:
      A . . W . . . . . T

    где W — стена, A — лучник, T — цель. Стена блокирует LoS.
    """
    bf = Battlefield(10, 3)
    bf.set_terrain(Square(3, 1), WALL)
    assert bf.line_of_sight(Square(0, 1), Square(9, 1)) is False


def test_book_scenario_archer_behind_high_cover_can_shoot_with_cover() -> None:
    """Лучник стреляет через high cover (парапет): LoS есть, но цель
    под three-quarters cover."""
    bf = Battlefield(10, 3)
    bf.set_terrain(Square(5, 1), HIGH_COVER)
    assert bf.line_of_sight(Square(0, 1), Square(9, 1)) is True
    assert bf.cover_against(Square(0, 1), Square(9, 1)) is CoverLevel.THREE_QUARTERS


def test_difficult_terrain_does_not_affect_los_or_cover() -> None:
    """Труднопроходимая местность не блокирует LoS и не даёт cover —
    только замедляет движение."""
    bf = Battlefield(10, 3)
    bf.set_terrain(Square(5, 1), DIFFICULT)
    assert bf.line_of_sight(Square(0, 1), Square(9, 1)) is True
    assert bf.cover_against(Square(0, 1), Square(9, 1)) is CoverLevel.NONE

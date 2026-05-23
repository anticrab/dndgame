"""Тесты Terrain и CoverLevel — value-объекты для клеток поля боя."""

from __future__ import annotations

import pytest

from dnd.domain.values.terrain import (
    CLOSED_DOOR,
    DIFFICULT,
    FLOOR,
    HIGH_COVER,
    LOW_COVER,
    PIT,
    WALL,
    CoverLevel,
    Terrain,
)

# -- CoverLevel.ac_bonus --------------------------------------------------


@pytest.mark.rules
@pytest.mark.parametrize(
    "cover,expected_bonus",
    [
        (CoverLevel.NONE, 0),
        (CoverLevel.HALF, 2),
        (CoverLevel.THREE_QUARTERS, 5),
        (CoverLevel.TOTAL, 0),  # цель нельзя выбрать
    ],
)
def test_cover_ac_bonus_per_book(cover: CoverLevel, expected_bonus: int) -> None:
    """Книга стр. 25: +0/+2/+5/нельзя_выбрать."""
    assert cover.ac_bonus == expected_bonus


def test_cover_level_rank_order() -> None:
    """CoverLevel.rank монотонен: NONE < HALF < THREE_QUARTERS < TOTAL.
    Используется для max-выбора в Tile.aggregate_cover (PHB-2024 стр. 25)."""
    assert CoverLevel.NONE.rank < CoverLevel.HALF.rank
    assert CoverLevel.HALF.rank < CoverLevel.THREE_QUARTERS.rank
    assert CoverLevel.THREE_QUARTERS.rank < CoverLevel.TOTAL.rank


@pytest.mark.rules
def test_total_cover_means_not_targetable() -> None:
    """Книга стр. 25: «нельзя выбрать целью напрямую»."""
    assert CoverLevel.TOTAL.can_be_targeted is False
    assert CoverLevel.NONE.can_be_targeted is True
    assert CoverLevel.HALF.can_be_targeted is True
    assert CoverLevel.THREE_QUARTERS.can_be_targeted is True


# -- Каноничные террейны --------------------------------------------------


def test_floor_is_default() -> None:
    """FLOOR — обычная клетка: проходима, не труднопроходима, не блокирует LoS."""
    assert FLOOR.passable is True
    assert FLOOR.difficult is False
    assert FLOOR.blocks_los is False
    assert FLOOR.cover is CoverLevel.NONE


def test_wall_blocks_movement_and_los() -> None:
    """WALL — непроходима, блокирует LoS, total cover для всего за ней."""
    assert WALL.passable is False
    assert WALL.blocks_los is True
    assert WALL.cover is CoverLevel.TOTAL


@pytest.mark.rules
def test_difficult_terrain_marker() -> None:
    """Книга стр. 23: труднопроходимая местность — фут×2 на каждый фут."""
    assert DIFFICULT.passable is True
    assert DIFFICULT.difficult is True
    assert DIFFICULT.blocks_los is False


def test_closed_door_is_wall_like() -> None:
    """Закрытая дверь блокирует и движение, и LoS — как стена.

    Открытая дверь — это просто FLOOR (другой Terrain-объект; здесь
    мы их не различаем строго, но контент обновит set_terrain
    при открытии)."""
    assert CLOSED_DOOR.passable is False
    assert CLOSED_DOOR.blocks_los is True


def test_low_cover_passable_but_gives_half_cover() -> None:
    """LowCover: проходимо, но цели за ним — half cover."""
    assert LOW_COVER.passable is True
    assert LOW_COVER.cover is CoverLevel.HALF


def test_high_cover_blocks_movement_but_not_los_three_quarters() -> None:
    """HighCover: непроходимо, но НЕ блокирует LoS полностью —
    стрелять между можно. Three-quarters cover."""
    assert HIGH_COVER.passable is False
    assert HIGH_COVER.blocks_los is False
    assert HIGH_COVER.cover is CoverLevel.THREE_QUARTERS


def test_pit_is_passable_but_difficult() -> None:
    assert PIT.passable is True
    assert PIT.difficult is True


# -- Frozen / hashable ---------------------------------------------------


def test_terrain_is_frozen() -> None:
    """Terrain — frozen dataclass, мутация запрещена."""
    from dataclasses import FrozenInstanceError

    t = Terrain()
    with pytest.raises(FrozenInstanceError):
        t.passable = False  # type: ignore[misc]


def test_terrain_is_hashable() -> None:
    """Terrain должен быть hashable — он живёт в dict[Square, Terrain]
    и одни и те же Terrain могут шериться между клетками."""
    s = {FLOOR, WALL, DIFFICULT}
    assert len(s) == 3
    # Одинаковые значения = один и тот же hash
    assert Terrain() == FLOOR
    assert {FLOOR, Terrain()} == {FLOOR}

"""find_walkable_path — Dijkstra с учётом стен и difficult terrain."""
from __future__ import annotations

from dnd.application.engine.actions.move_path import (
    find_walkable_path,
    path_cost_ft,
)
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.domain.values.terrain import FLOOR, WALL, Terrain


def _open(w: int, h: int) -> Battlefield:
    bf = Battlefield(w, h)
    for y in range(h):
        for x in range(w):
            bf.set_terrain(Square(x, y), FLOOR)
    return bf


def test_same_square_returns_empty() -> None:
    assert find_walkable_path(_open(5, 5), Square(2, 2), Square(2, 2)) == ()


def test_open_field_direct_chebyshev() -> None:
    """На пустом поле кратчайший путь = chebyshev."""
    bf = _open(10, 10)
    path = find_walkable_path(bf, Square(2, 2), Square(5, 2))
    assert path is not None
    assert path[-1] == Square(5, 2)
    assert len(path) == 3


def test_avoids_wall() -> None:
    bf = _open(10, 10)
    # Вертикальная стена x=3, y=0..3 (y=4..9 проход).
    for y in range(4):
        bf.set_terrain(Square(3, y), WALL)
    path = find_walkable_path(bf, Square(2, 0), Square(5, 0))
    assert path is not None
    assert Square(3, 0) not in path
    # обходим вниз и обратно
    assert any(sq.y > 0 for sq in path)


def test_returns_none_if_target_walled() -> None:
    bf = _open(5, 5)
    bf.set_terrain(Square(3, 3), WALL)
    assert find_walkable_path(bf, Square(0, 0), Square(3, 3)) is None


def test_returns_none_if_fully_isolated() -> None:
    bf = _open(5, 5)
    # Окружим (4, 4) стенами
    for sq in (Square(3, 4), Square(4, 3), Square(3, 3)):
        bf.set_terrain(sq, WALL)
    # И угол наружу
    bf.set_terrain(Square(4, 4), FLOOR)
    # До (4,4) можно дойти диагонально через (3,3)... нет, (3,3)
    # тоже стена. Значит изолировано.
    assert find_walkable_path(bf, Square(0, 0), Square(4, 4)) is None


def test_difficult_terrain_costs_double() -> None:
    """difficult клетки стоят 10 ft вместо 5 — суммарная стоимость растёт."""
    bf = _open(10, 1)
    # Сделаем (5, 0) difficult (mud).
    mud = Terrain(passable=True, difficult=True)
    bf.set_terrain(Square(5, 0), mud)
    path = find_walkable_path(bf, Square(0, 0), Square(7, 0))
    assert path is not None
    cost = path_cost_ft(bf, path)
    # 7 шагов: один по mud (10) + шесть по floor (30) = 40 ft.
    # Альтернатив (для 1×10 поля) нет — есть единственный путь.
    assert cost == 40


def test_creature_blocks_path() -> None:
    """Чужое существо на клетке делает её непроходимой для маршрута."""
    bf = _open(7, 1)
    # Существо в (3, 0).
    bf.place_creature(CreatureId("blocker"), Square(3, 0))
    # 1×7 поле — обойти невозможно.
    assert find_walkable_path(bf, Square(0, 0), Square(6, 0)) is None


def test_walks_around_creature_when_room() -> None:
    """Если есть боковой проход — Dijkstra его найдёт."""
    bf = _open(7, 3)
    bf.place_creature(CreatureId("blocker"), Square(3, 1))
    path = find_walkable_path(bf, Square(0, 1), Square(6, 1))
    assert path is not None
    assert Square(3, 1) not in path


def test_open_field_path_is_chebyshev_straight() -> None:
    """На пустом поле возвращается прямой chebyshev — не «зигзаг» с
    отступом по y, который раньше иногда выбирала Dijkstra при
    равной стоимости (UX-репорт «персонаж пытается сходить через
    верхнюю клетку»)."""
    bf = _open(10, 10)
    path = find_walkable_path(bf, Square(1, 5), Square(4, 5))
    assert path == (Square(2, 5), Square(3, 5), Square(4, 5))


def test_diagonal_open_field_is_straight_chebyshev() -> None:
    """Прямая diagonal — три шага без боковых отклонений."""
    bf = _open(10, 10)
    path = find_walkable_path(bf, Square(0, 0), Square(3, 3))
    assert path == (Square(1, 1), Square(2, 2), Square(3, 3))


def test_dead_creature_does_not_block_path() -> None:
    """Труп на пути не блокирует маршрут (is_alive=False)."""
    bf = _open(7, 1)
    bf.place_creature(CreatureId("corpse"), Square(3, 0))
    path = find_walkable_path(
        bf, Square(0, 0), Square(6, 0),
        is_alive=lambda cid: cid != CreatureId("corpse"),
    )
    assert path is not None
    # Должен пройти ПРЯМО через клетку с трупом (chebyshev fast-path).
    assert Square(3, 0) in path


def test_living_creature_still_blocks_with_filter() -> None:
    bf = _open(7, 1)
    bf.place_creature(CreatureId("g"), Square(3, 0))
    path = find_walkable_path(
        bf, Square(0, 0), Square(6, 0),
        is_alive=lambda cid: True,  # все живые → блокируют как раньше
    )
    assert path is None


def test_dead_creature_does_not_block_path_when_walls_force_detour() -> None:
    """C-1 regression: трупы должны быть проходимы и в A*-обходе,
    не только в chebyshev fast-path. Сценарий: стена прямо, труп в
    единственно возможной обходной клетке. Раньше fast-path
    fail'ил (стена), а Dijkstra игнорировал is_alive и считал труп
    блокировкой → path = None."""
    bf = _open(5, 3)
    # стена прямо от (0,1) к (4,1): cells (2,1) wall
    bf.set_terrain(Square(2, 1), WALL)
    # обходной путь сверху и снизу. Сверху труп в (2,0).
    # Снизу всё свободно (2,2).
    bf.place_creature(CreatureId("corpse_up"), Square(2, 0))
    path = find_walkable_path(
        bf, Square(0, 1), Square(4, 1),
        is_alive=lambda cid: cid != CreatureId("corpse_up"),
    )
    # Должен найти путь — либо через (2,0) (труп проходим), либо (2,2).
    assert path is not None
    # А вот если is_alive говорит «все живые» — оба узких прохода
    # заблокированы (живой блокер сверху, стена прямо), снизу свободно.
    bf2 = _open(3, 3)
    bf2.set_terrain(Square(1, 1), WALL)
    bf2.place_creature(CreatureId("alive_up"), Square(1, 0))
    path2 = find_walkable_path(
        bf2, Square(0, 1), Square(2, 1),
        is_alive=lambda cid: True,
    )
    # Должен пройти снизу через (1, 2) — никаких блокировок там нет.
    assert path2 is not None
    assert Square(1, 0) not in path2
    assert Square(1, 1) not in path2

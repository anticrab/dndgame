"""Battlefield — поле боя на квадратной сетке.

Спецификация — ``docs/ENGINE.md`` §2 (квадратная сетка, 1 клетка = 5 фут,
8 соседей, Chebyshev). ADR-0002.

Это **mutable entity** (решение Q24): операции ``place_creature``,
``move_creature``, ``set_terrain`` меняют состояние на месте. Для
сериализации в сейв и для replay есть метод ``snapshot()`` —
возвращает иммутабельный pydantic-DTO :class:`BattlefieldSnapshot`.

Карта прямоугольная, размеры (``width``, ``height``) заданы при
создании. Клетки нумеруются от (0, 0) до (width-1, height-1).
Клетки за пределами карты — невалидны (``in_bounds() == False``).

Несколько существ на одной клетке допускаются (Q1, согласовано):
``occupancy[Square]`` — это список ``CreatureId``. Сквозь враждебного
проход запрещён правилами книги (стр. 24) — это проверяется на уровне
движения, не на уровне Battlefield.

Линия видимости (LoS) — алгоритм Брезенхэма по клеткам (см.
``docs/VISIBILITY.md`` §7.1). Блокирующая клетка — любая с
``Terrain.blocks_los=True`` **между** источником и целью. Сами клетки
источника и цели не блокируют.

Что **не** делает Battlefield:

* не вычисляет освещение и видимость (это ``VisibilitySystem``);
* не знает про размеры существ больше Medium (MVP);
* не вычисляет дальность движения с учётом скорости (это правило
  движения);
* не публикует события — это делает ``Encounter``.
"""

from __future__ import annotations

from collections import defaultdict

from dnd.application.dto.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.domain.values.terrain import FLOOR, CoverLevel, Terrain


class Battlefield:
    """Поле боя. Mutable entity.

    Не подписывается на события, не зависит от EventBus. Все изменения
    делаются явно через методы; вызывающий слой (``Encounter``)
    публикует события самостоятельно.
    """

    def __init__(self, width: int, height: int) -> None:
        if width < 1 or height < 1:
            raise ValueError(
                f"battlefield size must be >= 1 in each dimension, "
                f"got width={width}, height={height}"
            )
        self._width = width
        self._height = height

        # Терраин: hash-таблица только для **не-FLOOR** клеток.
        # Все остальные считаются FLOOR. Это экономит память на больших
        # картах и упрощает «карта 10×8 с одной стеной — добавь только
        # её в dict».
        self._terrain: dict[Square, Terrain] = {}

        # Занятость: для каждой клетки — список ID существ. Несколько
        # существ на одной клетке допустимо (Q1).
        self._occupancy: dict[Square, list[CreatureId]] = defaultdict(list)

        # Обратный индекс: где находится каждое существо. Нужно для
        # быстрого move_creature без линейного поиска. Если существо
        # на нескольких клетках (Large+, post-MVP), это станет
        # `dict[CreatureId, set[Square]]`; пока — одиночная клетка.
        self._creature_position: dict[CreatureId, Square] = {}

    # --- размеры и границы --------------------------------------------

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    def in_bounds(self, square: Square) -> bool:
        """Лежит ли клетка в пределах карты."""
        return 0 <= square.x < self._width and 0 <= square.y < self._height

    # --- террейн ------------------------------------------------------

    def terrain_at(self, square: Square) -> Terrain:
        """Террейн клетки. Для незаданных явно — ``FLOOR`` по умолчанию.

        Вне границ — ``WALL``-подобный (непроходимый, блокирует LoS):
        это упрощает алгоритм LoS на краю карты, ему не нужны спец-проверки.
        """
        if not self.in_bounds(square):
            # Особый случай: за границей карты — фактически стена.
            # Это нужно, чтобы LoS-алгоритм безопасно «видел» границы.
            return _OUT_OF_BOUNDS

        return self._terrain.get(square, FLOOR)

    def set_terrain(self, square: Square, terrain: Terrain) -> None:
        """Установить террейн клетки. Вне границ — ValueError."""
        if not self.in_bounds(square):
            raise ValueError(f"square {square} is out of bounds")
        if terrain == FLOOR:
            # Каноническое представление FLOOR — отсутствие в dict.
            self._terrain.pop(square, None)
        else:
            self._terrain[square] = terrain

    # --- занятость существ --------------------------------------------

    def place_creature(self, creature_id: CreatureId, square: Square) -> None:
        """Поставить существо на клетку.

        Поведение:

        * Если существо уже было на карте — оно перемещается
          (эквивалент move_creature). Это удобно для сценариев и
          мастер-вмешательств.
        * Если клетка непроходима (стена) — ValueError. (Движение
          сквозь стену через portal/teleport — отдельный API, который
          обходит эту проверку.)
        * Если клетка вне границ — ValueError.
        """
        if not self.in_bounds(square):
            raise ValueError(f"square {square} is out of bounds")
        if not self.terrain_at(square).passable:
            raise ValueError(f"cannot place creature on impassable terrain at {square}")

        # Если уже был на карте — снимаем со старой клетки.
        if creature_id in self._creature_position:
            old = self._creature_position[creature_id]
            self._occupancy[old].remove(creature_id)
            if not self._occupancy[old]:
                del self._occupancy[old]

        self._occupancy[square].append(creature_id)
        self._creature_position[creature_id] = square

    def remove_creature(self, creature_id: CreatureId) -> None:
        """Снять существо с карты. Если его не было — KeyError."""
        if creature_id not in self._creature_position:
            raise KeyError(f"creature {creature_id!r} is not on the battlefield")
        square = self._creature_position[creature_id]
        self._occupancy[square].remove(creature_id)
        if not self._occupancy[square]:
            del self._occupancy[square]
        del self._creature_position[creature_id]

    def move_creature(self, creature_id: CreatureId, to_square: Square) -> None:
        """Переместить существо в указанную клетку.

        Не проверяет пройденный путь — это забота уровня действий
        (book движение по 5 фут, провоцированные атаки и т.п.).
        Battlefield только обновляет позицию.
        """
        if creature_id not in self._creature_position:
            raise KeyError(f"creature {creature_id!r} is not on the battlefield")
        self.place_creature(creature_id, to_square)  # внутри обработает

    def position_of(self, creature_id: CreatureId) -> Square:
        try:
            return self._creature_position[creature_id]
        except KeyError as exc:
            raise KeyError(f"creature {creature_id!r} is not on the battlefield") from exc

    def creatures_at(self, square: Square) -> tuple[CreatureId, ...]:
        """Кто стоит на клетке. Порядок — по времени постановки.

        Возвращает кортеж (иммутабельный snapshot), чтобы вызывающий
        не мог случайно мутировать внутренний список.
        """
        return tuple(self._occupancy.get(square, ()))

    def has_creature(self, creature_id: CreatureId) -> bool:
        return creature_id in self._creature_position

    @property
    def occupied_squares(self) -> frozenset[Square]:
        return frozenset(self._occupancy.keys())

    # --- LoS и cover --------------------------------------------------

    def line_of_sight(self, frm: Square, to: Square) -> bool:
        """Есть ли прямая линия видимости от ``frm`` к ``to``.

        Алгоритм Брезенхэма по клеткам сетки (см. VISIBILITY.md §7.1):
        промежуточные клетки на отрезке проверяются на ``blocks_los``;
        первая блокирующая прерывает.

        Сами клетки ``frm`` и ``to`` **не** проверяются: если цель
        стоит в WALL-клетке (невозможно, но логически) — мы её видим,
        потому что мы и так выбрали её как цель. Это согласуется с
        book-правилом «вы видите то, на что навели».

        Обе точки обязаны быть в пределах карты — иначе ValueError.
        Идентичные точки — всегда видны.

        Симметрия: ``los(a,b) == los(b,a)`` гарантируется через
        канонизацию endpoint'ов (``_canonical_segment``) — стандартный
        Брезенхэм направленно-зависим, и без канонизации одна и та же
        стена могла бы блокировать только в одну сторону.
        """
        self._require_in_bounds(frm, "frm")
        self._require_in_bounds(to, "to")
        if frm == to:
            return True
        a, b = _canonical_segment(frm, to)
        for cell in _bresenham_line(a, b):
            if cell in (a, b):
                continue
            if self.terrain_at(cell).blocks_los:
                return False
        return True

    def cover_against(self, attacker_pos: Square, target_pos: Square) -> CoverLevel:
        """Какое укрытие у цели против атаки.

        Алгоритм:

        * Если ``target_pos`` стоит на клетке с ``CoverLevel.TOTAL``
          (стена, закрытая дверь) — возвращаем ``TOTAL``: книга стр. 25,
          «цель за полной защитой нельзя выбрать целью атаки». Это
          важное отличие от семантики LoS — LoS позволяет «видеть, на
          что навели», но cover остаётся полным.
        * Иначе берём cover **наибольшей** клетки **между** позициями
          (книга стр. 25: «если несколько источников укрытия — берётся
          самое сильное»). Промежуточные клетки = клетки между, не
          включая endpoint'ы — cover на endpoint означал бы «цель
          ВНУТРИ парапета», а это уже не cover, а условие выбора цели.

        Обе точки обязаны быть в пределах карты — иначе ValueError.
        Идентичные точки — NONE.
        """
        self._require_in_bounds(attacker_pos, "attacker_pos")
        self._require_in_bounds(target_pos, "target_pos")
        if attacker_pos == target_pos:
            return CoverLevel.NONE

        # Книжный crash-stop: цель в total-cover клетке — нельзя выбрать.
        target_terrain_cover = self.terrain_at(target_pos).cover
        if target_terrain_cover is CoverLevel.TOTAL:
            return CoverLevel.TOTAL

        # Канонизируем порядок endpoint'ов для симметрии cover_against:
        # стандартный Брезенхэм направленно-зависим.
        a, b = _canonical_segment(attacker_pos, target_pos)
        worst = CoverLevel.NONE
        for cell in _bresenham_line(a, b):
            if cell in (a, b):
                continue
            cover = self.terrain_at(cell).cover
            if _cover_strength(cover) > _cover_strength(worst):
                worst = cover
        return worst

    def _require_in_bounds(self, square: Square, name: str) -> None:
        if not self.in_bounds(square):
            raise ValueError(f"{name}={square} is out of bounds")

    def threatens_squares(self, creature_id: CreatureId, *, reach_ft: int = 5) -> frozenset[Square]:
        """Какие клетки находятся под угрозой существа.

        Reach в 5 фут (1 клетка) — стандарт medium-существа без
        оружия с reach. Reach=10 фут (2 клетки) — глефа, копьё,
        большие существа.

        Возвращает множество **соседних в пределах reach** клеток,
        исключая саму клетку существа. Невалидные (вне границ) клетки
        тоже исключаются.
        """
        if creature_id not in self._creature_position:
            raise KeyError(f"creature {creature_id!r} is not on the battlefield")
        if reach_ft < 5 or reach_ft % 5 != 0:
            raise ValueError(f"reach_ft must be a positive multiple of 5, got {reach_ft}")

        my_pos = self._creature_position[creature_id]
        reach_squares = reach_ft // 5
        threatened: set[Square] = set()
        for dy in range(-reach_squares, reach_squares + 1):
            for dx in range(-reach_squares, reach_squares + 1):
                if dx == 0 and dy == 0:
                    continue
                cand = my_pos.step(dx, dy)
                if not self.in_bounds(cand):
                    continue
                threatened.add(cand)
        return frozenset(threatened)


# ---- Внутренние утилиты --------------------------------------------------

# Sentinel Terrain «вне карты»: непроходим, блокирует LoS, total cover.
# Создан как обычный Terrain, не нужно отдельного класса.
_OUT_OF_BOUNDS = Terrain(passable=False, blocks_los=True, cover=CoverLevel.TOTAL)


def _canonical_segment(p1: Square, p2: Square) -> tuple[Square, Square]:
    """Канонический порядок endpoint'ов для LoS/cover.

    Стандартный Брезенхэм направленно-зависим: при ``start→end`` и
    ``end→start`` он может выбирать разные промежуточные клетки на
    диагоналях. Это нарушает книжную симметрию «A видит B ⇔ B видит A».

    Сортируем пару лексикографически ``(x, y)`` — детерминированно и
    без потери информации.
    """
    return (p1, p2) if (p1.x, p1.y) <= (p2.x, p2.y) else (p2, p1)


def _cover_strength(cover: CoverLevel) -> int:
    """Порядок «силы» укрытия для выбора наибольшего."""
    return {
        CoverLevel.NONE: 0,
        CoverLevel.HALF: 1,
        CoverLevel.THREE_QUARTERS: 2,
        CoverLevel.TOTAL: 3,
    }[cover]


def _bresenham_line(start: Square, end: Square) -> list[Square]:
    """Целочисленный алгоритм Брезенхэма для линии на квадратной сетке.

    Возвращает список клеток вдоль линии **включая** обе конечные точки.
    Точки идут в порядке от start к end.

    Используется для LoS и для расчёта cover. Конкретные правила
    «угла стены» (когда диагональ упирается в угол между двумя
    блокирующими ортогональными клетками) — в этом MVP не моделируем;
    стандартный Брезенхэм даёт «диагональ проходит» — это согласуется
    с упрощённой trying-mode из DM-руководства.
    """
    x0, y0 = start.x, start.y
    x1, y1 = end.x, end.y
    points: list[Square] = []

    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    cx, cy = x0, y0
    while True:
        points.append(Square(cx, cy))
        if cx == x1 and cy == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            cx += sx
        if e2 < dx:
            err += dx
            cy += sy
    return points


__all__ = ["Battlefield"]

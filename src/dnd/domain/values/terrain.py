"""Террейн клетки и укрытия.

Книга 2024:

* «Труднопроходимая местность» (стр. 23, «Перемещение»):
  каждый фут перемещения стоит 1 дополнительный фут (×2).
* «Укрытие» (стр. 25, «Укрытие»): полное (нельзя выбрать целью),
  три четверти (+5 КД и спасброскам ЛОВ), половина (+2 КД и
  спасброскам ЛОВ).

Дополнительно — стены и двери (физическая блокировка движения и LoS).

Этот модуль определяет **value-объект** ``Terrain`` (иммутабельный
dataclass). Конкретные клетки хранятся в
:class:`~dnd.domain.entities.battlefield.Battlefield` как
``dict[Square, Terrain]``. Один и тот же объект ``Terrain`` может
ссылаться из многих клеток (флайвейт-стиль), поэтому он frozen и
hashable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CoverLevel(StrEnum):
    """Степень укрытия, которое террейн или объект даёт защищаемому."""

    NONE = "none"
    HALF = "half"  # +2 КД и спасброскам Ловкости (книга стр. 25)
    THREE_QUARTERS = "three_quarters"  # +5 КД и спасброскам Ловкости
    TOTAL = "total"  # нельзя выбрать целью

    @property
    def ac_bonus(self) -> int:
        """Бонус к КД и спасброскам Ловкости защищаемого."""
        return {
            CoverLevel.NONE: 0,
            CoverLevel.HALF: 2,
            CoverLevel.THREE_QUARTERS: 5,
            CoverLevel.TOTAL: 0,  # цель нельзя выбрать вообще
        }[self]

    @property
    def can_be_targeted(self) -> bool:
        return self is not CoverLevel.TOTAL


@dataclass(frozen=True, slots=True)
class Terrain:
    """Свойства одной клетки.

    Поля:

    * ``passable`` — можно ли войти в клетку (стены — False).
    * ``difficult`` — труднопроходимая (стоимость движения ×2).
    * ``blocks_los`` — блокирует ли линию видимости (стена, закрытая
      дверь, дым).
    * ``cover`` — какое укрытие даёт цели за этой клеткой (а не на ней).
      Высокий бортик: ``HALF``; колонна: ``THREE_QUARTERS``; стена:
      ``TOTAL`` (но обычно стену не атакуют как цель).

    Не валидируем «passable=False но cover=NONE» — стены могут давать
    укрытие или нет (например, стеклянная стена не блокирует LoS, но
    блокирует движение). Контент описывает явно.
    """

    passable: bool = True
    difficult: bool = False
    blocks_los: bool = False
    cover: CoverLevel = CoverLevel.NONE


# Готовые «канонические» типы террейна. Используются и в YAML через
# простой ID-маппинг ('.' → FLOOR, '#' → WALL и т.п.), и из кода тестов.

FLOOR = Terrain()
"""Обычный пол: проходимо, не труднопроходимо, не блокирует LoS."""

DIFFICULT = Terrain(difficult=True)
"""Труднопроходимая местность (низкая мебель, осыпь, мелкие болота,
снег). Книга стр. 23: каждый фут стоит 2 фута перемещения."""

WALL = Terrain(passable=False, blocks_los=True, cover=CoverLevel.TOTAL)
"""Стена: непроходима, блокирует LoS, total cover для всего за ней."""

CLOSED_DOOR = Terrain(passable=False, blocks_los=True, cover=CoverLevel.TOTAL)
"""Закрытая дверь — то же, что стена. Открытая — обычный пол."""

LOW_COVER = Terrain(passable=True, cover=CoverLevel.HALF)
"""Низкий бортик / стол / большой обломок: проходимо (можно перелезть
действием Interact или ползком), но даёт цели за ним half cover."""

HIGH_COVER = Terrain(passable=False, blocks_los=False, cover=CoverLevel.THREE_QUARTERS)
"""Высокий выступ / колонна / парапет: непроходимо, не блокирует LoS
полностью (можно стрелять между), даёт три-четверти cover."""

PIT = Terrain(passable=True, difficult=True)
"""Яма: проходимо (с риском падения, что — отдельная механика), но
труднопроходимо."""


__all__ = [
    "CLOSED_DOOR",
    "DIFFICULT",
    "FLOOR",
    "HIGH_COVER",
    "LOW_COVER",
    "PIT",
    "WALL",
    "CoverLevel",
    "Terrain",
]

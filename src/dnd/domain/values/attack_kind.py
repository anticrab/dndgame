"""AttackKind — категория атаки (MELEE / RANGED).

Чистое value-перечисление; живёт в domain, потому что используется и
``WeaponProfile`` (свойство оружия), и application-action'ами (на чём
строится поведение AttackAction / OpportunityAttack). Раздельно от
``attack.py``, чтобы domain не зависел от application.
"""

from __future__ import annotations

from enum import StrEnum


class AttackKind(StrEnum):
    """Категория атаки.

    * ``MELEE`` — ближний бой. Для атаки нужно быть в reach оружия.
    * ``RANGED`` — дальний бой. Имеет ``range_ft`` (нормальная) и
      опциональный ``long_range_ft`` (на helf-disadvantage).
    """

    MELEE = "melee"
    RANGED = "ranged"


__all__ = ["AttackKind"]

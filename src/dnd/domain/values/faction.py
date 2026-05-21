"""Фракция существа в бою.

Per-encounter роль (не свойство самой ``Creature``: одно и то же
существо в разных сценариях может быть на разных сторонах). Хранится
в ``Encounter.factions: dict[CreatureId, Faction]``.

См. ``docs/ENCOUNTER.md`` §5.
"""

from __future__ import annotations

from enum import StrEnum


class Faction(StrEnum):
    """Сторона в бою.

    * ``PARTY`` — игроки и их союзники;
    * ``MONSTERS`` — противники;
    * ``NEUTRAL`` — наблюдатели, бесчувственные существа, кто-то третий.
      Не участвует в проверке «бой закончен» (см. ENCOUNTER.md §5).
    """

    PARTY = "party"
    MONSTERS = "monsters"
    NEUTRAL = "neutral"

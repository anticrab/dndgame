"""XpAwardService — начисление XP и сигнал о готовности к level-up (этап R1).

Подписан на CreatureDied: смерть монстра (фракция ≠ PARTY) даёт XP всем живым
PC (PARTY) по формуле CR*100 (PROGRESSION.md §2). Если XP пересёк порог кривой —
публикует LevelUpReady. Применяет повышение НЕ здесь, а LevelUpService (по выбору
игрока: сейчас/после боя).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.application.dto.engine_event import CreatureDied, LevelUpReady
from dnd.domain.values.faction import Faction

if TYPE_CHECKING:
    from dnd.application.engine.progression.xp_curve import XpCurve
    from dnd.application.ports.class_repository import ClassRepository
    from dnd.application.ports.event_bus import EventBus
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ids import CreatureId


class XpAwardService:
    def __init__(
        self,
        *,
        event_bus: EventBus,
        curve: XpCurve,
        participants: dict[CreatureId, Creature],
        factions: dict[CreatureId, Faction],
        class_repository: ClassRepository | None = None,
    ) -> None:
        self._bus = event_bus
        self._curve = curve
        self._participants = participants
        self._factions = factions
        # REV-6: ограничиваем целевой уровень максимумом таблицы класса —
        # иначе при XP выше недостижимого уровня (кривая отдаёт 4/20, а
        # classes.yaml только L1–3) LevelUpReady спамился бы на каждое
        # убийство (LevelUpService при этом — no-op). None → без ограничения
        # (backward-compat для тестов/каркаса).
        self._classes = class_repository

    def subscribe(self) -> None:
        self._bus.subscribe(CreatureDied, self._on_died)

    def _on_died(self, event: CreatureDied) -> None:
        dead_faction = self._factions.get(event.actor_id)
        if dead_faction is not Faction.MONSTERS:
            return  # XP дают только за врагов (не PARTY и не NEUTRAL)
        dead = self._participants.get(event.actor_id)
        if dead is None:
            return
        gained = int(dead.challenge_rating * 100)
        if gained <= 0:
            return
        for cid, cr in self._participants.items():
            if self._factions.get(cid) is not Faction.PARTY or not cr.is_alive:
                continue
            cr.xp += gained
            target_level = self._curve.level_for_xp(cr.xp)
            max_level = self._max_class_level(cr)
            if max_level is not None:
                target_level = min(target_level, max_level)
            if target_level > cr.level:
                self._bus.publish(
                    LevelUpReady(
                        actor_id=cid,
                        from_level=cr.level,
                        to_level=target_level,
                    )
                )

    def _max_class_level(self, cr: Creature) -> int | None:
        """Максимальный уровень в таблице класса существа (None — нет данных)."""
        if self._classes is None or cr.character_class is None:
            return None
        if not self._classes.contains(cr.character_class):
            return None
        levels = self._classes.load(cr.character_class).levels
        return max(levels) if levels else None


__all__ = ["XpAwardService"]

"""LevelUpService — применение повышения уровня (этап R1).

Двигает creature.level вперёд по таблице класса, начисляя за каждый уровень:
HP (фикс. среднее кости хитов + mod ТЕЛ), proficiency_bonus, spell_slots, и
обретение фич через FeatureRegistry. Идемпотентно: повторный apply к тому же
to_level — no-op (level уже там). HP — детерминированно (без броска), удобно
для тестов и драмы level-up в бою.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from dnd.application.dto.engine_event import LeveledUp
from dnd.domain.values.ability import Ability

if TYPE_CHECKING:
    from dnd.application.engine.features.registry import FeatureRegistry
    from dnd.application.engine.turn_context import TurnContext
    from dnd.application.ports.class_repository import ClassRepository
    from dnd.application.ports.event_bus import EventBus
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ids import FeatureId


@dataclass(frozen=True, slots=True)
class LevelUpResult:
    new_level: int
    hp_gained: int
    features_gained: tuple[FeatureId, ...]
    new_proficiency_bonus: int


class LevelUpService:
    def __init__(
        self,
        *,
        class_repository: ClassRepository,
        feature_registry: FeatureRegistry,
        event_bus: EventBus,
    ) -> None:
        self._classes = class_repository
        self._features = feature_registry
        self._bus = event_bus

    def apply(self, creature: Creature, *, to_level: int, ctx: TurnContext | None) -> LevelUpResult:
        assert creature.character_class is not None, "level-up requires a class"
        progression = self._classes.load(creature.character_class)
        # T1: держим профициентные спасброски в синхроне с таблицей класса.
        creature.saving_throw_proficiencies = progression.saving_throw_proficiencies
        con_mod = creature.abilities.modifier(Ability.CON)
        hp_per_level = max(1, progression.hit_die_average() + con_mod)

        total_hp = 0
        gained: list[FeatureId] = []
        while creature.level < to_level:
            next_level = creature.level + 1
            lvl = progression.levels.get(next_level)
            if lvl is None:
                break
            creature.level = next_level
            creature.proficiency_bonus = lvl.proficiency_bonus
            if lvl.spell_slots is not None:
                creature.spell_slots = dict(lvl.spell_slots)
            total_hp += hp_per_level
            for fid in lvl.features:
                creature.features = (*creature.features, fid)
                gained.append(fid)
                self._features.get(fid).on_gain(creature, ctx)

        if total_hp:
            creature.hit_points = creature.hit_points.gain_max(total_hp)

        result = LevelUpResult(
            new_level=creature.level,
            hp_gained=total_hp,
            features_gained=tuple(gained),
            new_proficiency_bonus=creature.proficiency_bonus,
        )
        if total_hp or gained:
            self._bus.publish(
                LeveledUp(
                    actor_id=creature.id,
                    new_level=creature.level,
                    hp_gained=total_hp,
                    features_gained=tuple(str(f) for f in gained),
                )
            )
        return result


__all__ = ["LevelUpResult", "LevelUpService"]

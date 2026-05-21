"""Сборка ``Battlefield`` и ``Encounter`` из ``ScenarioTemplate``.

См. ``docs/ENGINE.md`` §2.6 (формат карты) и ``docs/ENCOUNTER.md``.
"""

from __future__ import annotations

from dnd.application.dto.ids import CreatureId
from dnd.application.dto.templates import MapTemplate, ScenarioTemplate
from dnd.application.engine.builder import build_creature_from_template
from dnd.application.engine.encounter import Encounter, EncounterDependencies
from dnd.application.ports.content_repository import ContentRepository
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
from dnd.domain.values.terrain import (
    CLOSED_DOOR,
    DIFFICULT,
    FLOOR,
    HIGH_COVER,
    LOW_COVER,
    PIT,
    WALL,
    Terrain,
)

# Имя в YAML legend → канонический Terrain. Расширяется по мере роста
# контента.
_TERRAIN_BY_ID: dict[str, Terrain] = {
    "floor": FLOOR,
    "wall": WALL,
    "difficult": DIFFICULT,
    "closed_door": CLOSED_DOOR,
    "low_cover": LOW_COVER,
    "high_cover": HIGH_COVER,
    "pit": PIT,
}


def build_battlefield_from_map(template: MapTemplate) -> Battlefield:
    """``MapTemplate`` → ``Battlefield`` с расставленным террейном.

    Sanity:

    * ``len(grid) == height``;
    * каждая строка имеет длину ``width``;
    * все символы из ``grid`` присутствуют в ``legend``;
    * все ``legend.values()`` — известные ID террейна.
    """
    if len(template.grid) != template.height:
        raise ValueError(
            f"grid has {len(template.grid)} rows, expected {template.height}"
        )

    bf = Battlefield(template.width, template.height)
    for y, row in enumerate(template.grid):
        if len(row) != template.width:
            raise ValueError(
                f"row {y} has length {len(row)}, expected {template.width}"
            )
        for x, ch in enumerate(row):
            terrain_id = template.legend.get(ch)
            if terrain_id is None:
                raise ValueError(
                    f"unknown legend symbol {ch!r} at ({x},{y})"
                )
            terrain = _TERRAIN_BY_ID.get(terrain_id)
            if terrain is None:
                raise ValueError(
                    f"unknown terrain id {terrain_id!r} in legend"
                )
            if terrain is not FLOOR:
                bf.set_terrain(Square(x, y), terrain)
    return bf


def build_encounter_from_scenario(
    scenario: ScenarioTemplate,
    *,
    content: ContentRepository,
    deps: EncounterDependencies,
) -> Encounter:
    """Из сценария — готовый Encounter (не запущенный).

    Битфилд из ``deps`` игнорируется и заменяется на новый из карты —
    composition root обычно строит deps под этот сценарий.

    Возвращает Encounter; вызывающий делает ``encounter.start()``.
    """
    bf = build_battlefield_from_map(scenario.map)
    deps_with_map = EncounterDependencies(
        battlefield=bf,
        dice_roller=deps.dice_roller,
        modifier_applier=deps.modifier_applier,
        condition_service=deps.condition_service,
        event_bus=deps.event_bus,
        rng=deps.rng,
    )

    participants: dict[CreatureId, Creature] = {}
    factions: dict[CreatureId, Faction] = {}
    for spawn in scenario.spawns:
        instance_id = CreatureId(spawn.instance_id)
        template = content.monster_by_id(spawn.template_id)
        creature = build_creature_from_template(
            template, instance_id=instance_id, content=content
        )
        participants[instance_id] = creature
        factions[instance_id] = spawn.faction
        bf.place_creature(instance_id, Square(*spawn.at))

    return Encounter(
        participants=participants,
        factions=factions,
        deps=deps_with_map,
    )


__all__ = [
    "build_battlefield_from_map",
    "build_encounter_from_scenario",
]

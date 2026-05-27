"""Сборка ``Battlefield`` и ``Encounter`` из ``ScenarioTemplate``.

См. ``docs/ENGINE.md`` §2.6 (формат карты) и ``docs/ENCOUNTER.md``.

K9 S1-1: добавлен путь «scenario с ``map_id``» — карта берётся из
:class:`MapRepository` (формат :class:`MapDocument` с Tile API +
objects), а не из inline ``MapTemplate``. Старый путь сохранён для
backwards-compatibility (mvp_skirmish / mvp_room).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.application.dto.map_dto import MapDocument
from dnd.application.dto.templates import MapTemplate, ScenarioTemplate
from dnd.application.engine.builder import build_creature_from_template
from dnd.application.engine.encounter import Encounter, EncounterDependencies
from dnd.application.ports.content_repository import ContentRepository
from dnd.application.ports.map_repository import MapRepository
from dnd.application.ports.sprite_registry import SpriteRegistry
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.entities.interactable import InteractableObject
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId, ObjectId
from dnd.domain.values.object_kind import ObjectKind
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
from dnd.domain.values.tile import Tile

if TYPE_CHECKING:
    from dnd.application.ports.class_repository import ClassRepository
    from dnd.composition import EncounterRuntimeServices

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
        raise ValueError(f"grid has {len(template.grid)} rows, expected {template.height}")

    bf = Battlefield(template.width, template.height)
    for y, row in enumerate(template.grid):
        if len(row) != template.width:
            raise ValueError(f"row {y} has length {len(row)}, expected {template.width}")
        for x, ch in enumerate(row):
            terrain_id = template.legend.get(ch)
            if terrain_id is None:
                raise ValueError(f"unknown legend symbol {ch!r} at ({x},{y})")
            terrain = _TERRAIN_BY_ID.get(terrain_id)
            if terrain is None:
                raise ValueError(f"unknown terrain id {terrain_id!r} in legend")
            if terrain is not FLOOR:
                bf.set_terrain(Square(x, y), terrain)
    return bf


def build_battlefield_from_document(doc: MapDocument, *, sprites: SpriteRegistry) -> Battlefield:
    """``MapDocument`` → ``Battlefield`` через Tile API + объекты.

    Tile-слой (новый, K1-T6) используется для каждой клетки с не-пустыми
    features. Параллельно проставляется legacy ``Terrain`` для
    непроходимых клеток (стены / непроходимые features), чтобы старые
    проверки ``passable`` (через ``terrain_at``) тоже работали — пока
    движение/LoS не полностью переехали на Tile.

    Объекты карты (``MapObjectDoc``) превращаются в
    :class:`InteractableObject` и кладутся через ``place_object``.
    """
    bf = Battlefield(doc.width, doc.height)
    for tile_doc in doc.tiles:
        base = sprites.get_terrain(tile_doc.base)
        features = tuple(sprites.get_feature(fid) for fid in tile_doc.features)
        tile = Tile(base=base, features=features)
        sq = Square(tile_doc.x, tile_doc.y)
        # Tile API — новый слой.
        if features or not base.passable:
            bf.set_tile(sq, tile)
        # Legacy Terrain — нужен для place_creature и старых API, которые
        # пока проверяют passability через ``terrain_at``. Маппим
        # «непроходимое или непрозрачное» в ``WALL``, иначе оставляем
        # FLOOR (default).
        if not tile.base.passable or any(f.passable_cost_ft == 0 for f in features):
            bf.set_terrain(sq, WALL)

    for obj_doc in doc.objects:
        try:
            kind = ObjectKind(obj_doc.kind)
        except ValueError as exc:
            raise ValueError(f"unknown object kind {obj_doc.kind!r} for {obj_doc.id}") from exc
        bf.place_object(
            InteractableObject(
                id=ObjectId(obj_doc.id),
                kind=kind,
                pos=Square(obj_doc.x, obj_doc.y),
                state=dict(obj_doc.state),
            )
        )
    return bf


def build_encounter_from_scenario(
    scenario: ScenarioTemplate,
    *,
    content: ContentRepository,
    services: EncounterRuntimeServices | None = None,
    deps: EncounterDependencies | None = None,
    map_repository: MapRepository | None = None,
    sprite_registry: SpriteRegistry | None = None,
    class_repository: ClassRepository | None = None,
) -> Encounter:
    """Из сценария — готовый Encounter (не запущенный).

    Принимает **одно** из двух (XOR):

    * ``services: EncounterRuntimeServices`` — рекомендуемый путь
      (CL-A001). Битфилд строится из карты сценария, services
      привязываются через ``with_battlefield``.
    * ``deps: EncounterDependencies`` — legacy: ``deps.battlefield``
      игнорируется и заменяется новым битфилдом. Сохранено для
      обратной совместимости тестов.

    Карта берётся из:

    * inline ``scenario.map`` (legacy MVP); либо
    * ``scenario.map_id`` через ``map_repository`` + ``sprite_registry``
      (K9: новый формат с Tile API + objects). Оба обязательны если
      используется map_id.

    Возвращает Encounter; вызывающий делает ``encounter.start()``.
    """
    if (services is None) == (deps is None):
        raise ValueError(
            "build_encounter_from_scenario requires exactly one of `services` or `deps`"
        )

    if scenario.map_id is not None:
        if map_repository is None or sprite_registry is None:
            raise ValueError(
                "scenario uses map_id; map_repository and sprite_registry are required"
            )
        doc = map_repository.load(scenario.map_id)
        bf = build_battlefield_from_document(doc, sprites=sprite_registry)
    else:
        assert scenario.map is not None  # гарантировано XOR-валидатором
        bf = build_battlefield_from_map(scenario.map)

    if services is not None:
        deps_with_map = services.with_battlefield(bf)
    else:
        # legacy путь: переиспользуем все сервисы из deps, заменяем
        # только battlefield на свежий из карты.
        assert deps is not None
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
            template,
            instance_id=instance_id,
            content=content,
            class_repository=class_repository,
        )
        # Q-11: существа фракции PARTY используют спасброски от смерти
        # (PHB-2024 стр. 27) — при 0 HP уходят в dying, а не умирают сразу.
        # NPC/MONSTERS — мгновенная смерть (CORPSE).
        if spawn.faction is Faction.PARTY:
            creature.uses_death_saves = True
        participants[instance_id] = creature
        factions[instance_id] = spawn.faction
        bf.place_creature(instance_id, Square(*spawn.at))

    return Encounter(
        participants=participants,
        factions=factions,
        deps=deps_with_map,
    )


__all__ = [
    "build_battlefield_from_document",
    "build_battlefield_from_map",
    "build_encounter_from_scenario",
]

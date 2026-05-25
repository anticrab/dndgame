"""R1-7: LevelUpService — применение уровней (HP/prof/slots/features)."""
from __future__ import annotations

from pathlib import Path

from dnd.application.dto.engine_event import LeveledUp
from dnd.application.engine.features.registry import FeatureRegistry
from dnd.application.engine.progression.level_up import LevelUpService
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ids import FeatureId
from dnd.infrastructure.content.yaml_class_repository import YamlClassRepository
from dnd.infrastructure.events.in_memory_event_bus import InMemoryEventBus

_CLASSES = Path(__file__).resolve().parents[3] / "data" / "content" / "classes.yaml"


class _RecordingHandler:
    def __init__(self) -> None:
        self.calls = 0

    def on_gain(self, creature: Creature, ctx: object) -> None:
        self.calls += 1


def _pc() -> Creature:
    c = Creature.create(
        id_="hero", name="Hero",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=12, armor_class=16, speed_ft=30,
    )
    c.character_class = "fighter"
    return c


def _svc(bus: InMemoryEventBus, registry: FeatureRegistry) -> LevelUpService:
    return LevelUpService(
        class_repository=YamlClassRepository(_CLASSES),
        feature_registry=registry, event_bus=bus,
    )


def test_level_up_grants_hp_prof_and_feature() -> None:
    bus = InMemoryEventBus()
    leveled: list[LeveledUp] = []
    bus.subscribe(LeveledUp, leveled.append)
    reg = FeatureRegistry()
    surge = _RecordingHandler()
    reg.register(FeatureId("action_surge"), surge)   # фича L2 воина
    pc = _pc()
    res = _svc(bus, reg).apply(pc, to_level=2, ctx=None)
    assert pc.level == 2
    # HP: d10 avg(6) + CON mod(+2) = 8 за уровень L2
    assert res.hp_gained == 8
    assert pc.hit_points.maximum == 12 + 8 and pc.hit_points.current == 12 + 8
    assert FeatureId("action_surge") in pc.features
    assert surge.calls == 1
    assert leveled and leveled[0].new_level == 2


def test_level_up_idempotent() -> None:
    bus = InMemoryEventBus()
    reg = FeatureRegistry()
    reg.register(FeatureId("action_surge"), _RecordingHandler())
    pc = _pc()
    svc = _svc(bus, reg)
    svc.apply(pc, to_level=2, ctx=None)
    hp_after_first = pc.hit_points.maximum
    svc.apply(pc, to_level=2, ctx=None)   # повтор — no-op
    assert pc.hit_points.maximum == hp_after_first and pc.level == 2

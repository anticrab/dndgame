"""E2E T4: воин L1→L3 получает боевой стиль (Defense +1 AC) и подкласс
(Чемпион → крит 19), плут получает Cunning Action на L2."""
from __future__ import annotations

from pathlib import Path

import pytest

from dnd.application.engine.features.defaults import default_feature_registry
from dnd.application.engine.progression.level_up import LevelUpService
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ability_id import AbilityId
from dnd.domain.values.ids import CreatureId, FeatureId
from dnd.infrastructure.content.yaml_class_repository import YamlClassRepository
from dnd.infrastructure.events.in_memory_event_bus import InMemoryEventBus

_CLASSES = Path("data/content/classes.yaml")


def _svc() -> LevelUpService:
    return LevelUpService(
        class_repository=YamlClassRepository(_CLASSES),
        feature_registry=default_feature_registry(),
        event_bus=InMemoryEventBus(),
    )


@pytest.mark.e2e
def test_fighter_l1_to_l3_gains_style_and_champion() -> None:
    fighter = Creature.create(
        id_=CreatureId("f"), name="f",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=12, armor_class=16, speed_ft=30,
    )
    fighter.character_class = "fighter"
    fighter.level = 0  # рамп с нуля, чтобы применился и L1 (Fighting Style)
    fighter.fighting_style = FeatureId("style_defense")
    _svc().apply(fighter, to_level=3, ctx=None)
    assert fighter.armor_class == 17  # Defense +1
    assert "action_surge" in fighter.resource_uses  # L2
    assert fighter.crit_range_min == 19  # L3 Champion → Improved Critical
    assert fighter.subclass == FeatureId("subclass_champion")


@pytest.mark.e2e
def test_rogue_l2_gains_cunning_action() -> None:
    rogue = Creature.create(
        id_=CreatureId("r"), name="r",
        abilities=AbilityScores.of(str_=10, dex=16, con=12, int_=12, wis=10, cha=10),
        max_hp=10, armor_class=14, speed_ft=30,
    )
    rogue.character_class = "rogue"
    rogue.level = 0
    _svc().apply(rogue, to_level=3, ctx=None)
    assert AbilityId("cunning_dash") in rogue.ability_ids  # L2
    assert rogue.subclass == FeatureId("subclass_thief")  # L3

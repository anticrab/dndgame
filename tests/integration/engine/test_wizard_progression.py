"""T1: класс wizard — слоты растут по уровням через LevelUpService."""

from __future__ import annotations

from pathlib import Path

from dnd.application.engine.features.defaults import default_feature_registry
from dnd.application.engine.progression.level_up import LevelUpService
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.ids import CreatureId
from dnd.infrastructure.content.yaml_class_repository import YamlClassRepository
from dnd.infrastructure.events.in_memory_event_bus import InMemoryEventBus


def _wiz() -> Creature:
    c = Creature.create(
        id_=CreatureId("w"),
        name="w",
        abilities=AbilityScores.of(str_=8, dex=12, con=12, int_=16, wis=10, cha=10),
        max_hp=6,
        armor_class=12,
        speed_ft=30,
    )
    c.character_class = "wizard"
    c.level = 1
    c.spellcasting_ability = Ability.INT
    return c


def _svc() -> LevelUpService:
    return LevelUpService(
        class_repository=YamlClassRepository(Path("data/content/classes.yaml")),
        feature_registry=default_feature_registry(),
        event_bus=InMemoryEventBus(),
    )


def test_wizard_class_exists_with_d6_and_save_profs() -> None:
    repo = YamlClassRepository(Path("data/content/classes.yaml"))
    prog = repo.load("wizard")
    assert prog.hit_die == "1d6"
    assert prog.saving_throw_proficiencies == frozenset({Ability.INT, Ability.WIS})


def test_wizard_slots_grow_by_level() -> None:
    w = _wiz()
    svc = _svc()
    svc.apply(w, to_level=2, ctx=None)
    assert w.spell_slots == {1: 3}
    svc.apply(w, to_level=3, ctx=None)
    assert w.spell_slots == {1: 4, 2: 2}

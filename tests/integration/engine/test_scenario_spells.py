"""P1-12: сценарий выдаёт PC-кастеру заклинания, ячейки и характеристику."""

from __future__ import annotations

from pathlib import Path

from dnd.application.engine.scenario_builder import build_encounter_from_scenario
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.ability import Ability
from dnd.domain.values.ids import CreatureId, SpellId
from dnd.infrastructure.content.yaml_repository import YamlContentRepository

_CONTENT = Path(__file__).resolve().parents[3] / "data" / "content"


def test_mage_skirmish_pc_is_spellcaster() -> None:
    repo = YamlContentRepository(_CONTENT)
    scenario = repo.scenario_by_id("mage_skirmish")
    deps, _, _ = build_scripted_dependencies(battlefield=Battlefield(1, 1), rolls=[])
    enc = build_encounter_from_scenario(scenario, content=repo, deps=deps)
    mage = enc.participants[CreatureId("aelar")]
    assert mage.spellcasting_ability is Ability.INT
    assert SpellId("fire_bolt") in mage.known_spells
    assert SpellId("magic_missile") in mage.known_spells
    assert mage.spell_slots == {1: 2}  # T1: волшебник L1 — две ячейки 1 круга
    # Деривации работают (INT 16 → +3, prof +2).
    assert mage.spell_attack_bonus() == 5
    assert mage.spell_save_dc() == 13


def test_goblin_is_not_spellcaster() -> None:
    repo = YamlContentRepository(_CONTENT)
    scenario = repo.scenario_by_id("mage_skirmish")
    deps, _, _ = build_scripted_dependencies(battlefield=Battlefield(1, 1), rolls=[])
    enc = build_encounter_from_scenario(scenario, content=repo, deps=deps)
    gob = enc.participants[CreatureId("goblin1")]
    assert gob.spellcasting_ability is None
    assert gob.known_spells == ()

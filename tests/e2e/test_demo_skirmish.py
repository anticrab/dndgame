"""E2E демо-сцена `demo_skirmish` — основа «первичного показа».

Проверяем, что курированная боевая сцена корректно собрана из контента:
один воин-PC (fighter L1, со спасбросками от смерти) против пяти гоблинов,
и что суммарного XP за гоблинов заведомо хватает на level-up до 2.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dnd.application.dto.engine_event import CreatureDied, LevelUpReady
from dnd.application.dto.templates import ScenarioTemplate
from dnd.application.engine.encounter import Encounter
from dnd.application.engine.features.defaults import default_feature_registry
from dnd.application.engine.progression.level_up import LevelUpService
from dnd.application.engine.progression.xp_award import XpAwardService
from dnd.application.engine.progression.xp_curve import FastXpCurve
from dnd.application.engine.scenario_builder import build_encounter_from_scenario
from dnd.composition import build_default_runtime_services
from dnd.domain.values.faction import Faction
from dnd.infrastructure.content.yaml_class_repository import YamlClassRepository
from dnd.infrastructure.content.yaml_repository import YamlContentRepository

_CONTENT = Path("data/content")


def _build_demo() -> tuple[ScenarioTemplate, Encounter]:
    repo = YamlContentRepository(_CONTENT)
    scenario = repo.scenario_by_id("demo_skirmish")
    services = build_default_runtime_services()
    return scenario, build_encounter_from_scenario(
        scenario, content=repo, services=services
    )


@pytest.mark.e2e
def test_demo_skirmish_loads_with_warrior_vs_five_goblins() -> None:
    _scenario, enc = _build_demo()

    party = [cid for cid, f in enc.factions.items() if f is Faction.PARTY]
    monsters = [cid for cid, f in enc.factions.items() if f is Faction.MONSTERS]
    assert len(party) == 1, "в демо ровно один PC-воин"
    assert len(monsters) == 5, "в демо пять гоблинов"

    warrior = enc.participants[party[0]]
    assert warrior.character_class == "fighter"
    assert warrior.level == 1
    assert warrior.uses_death_saves is True  # PARTY → death saves (страховка драмы)


@pytest.mark.e2e
def test_demo_skirmish_xp_budget_reaches_level_two() -> None:
    """Суммарный XP за всех гоблинов ≥ порога 2 уровня (100 по FastXpCurve)."""
    _scenario, enc = _build_demo()
    total_xp = sum(
        int(enc.participants[cid].challenge_rating * 100)
        for cid, f in enc.factions.items()
        if f is Faction.MONSTERS
    )
    assert total_xp >= FastXpCurve().threshold(2), (
        f"XP-бюджет демо ({total_xp}) меньше порога 2 уровня"
    )


@pytest.mark.e2e
def test_demo_skirmish_fourth_kill_triggers_levelup_to_two() -> None:
    """Смерти 4 гоблинов → 100 XP → LevelUpReady → авто level-up до 2.

    Воспроизводит ровно тот wiring, что в interfaces/cli/app.py (non-TUI):
    XpAwardService.subscribe() + авто-применение LevelUpService на LevelUpReady.
    """
    _scenario, enc = _build_demo()
    warrior_id = next(cid for cid, f in enc.factions.items() if f is Faction.PARTY)
    goblin_ids = [cid for cid, f in enc.factions.items() if f is Faction.MONSTERS]
    warrior = enc.participants[warrior_id]

    XpAwardService(
        event_bus=enc.event_bus, curve=FastXpCurve(),
        participants=enc.participants, factions=enc.factions,
    ).subscribe()
    level_up = LevelUpService(
        class_repository=YamlClassRepository(_CONTENT / "classes.yaml"),
        feature_registry=default_feature_registry(),
        event_bus=enc.event_bus,
    )
    ready: list[LevelUpReady] = []

    def _auto(ev: LevelUpReady) -> None:
        ready.append(ev)
        level_up.apply(enc.participants[ev.actor_id], to_level=ev.to_level, ctx=None)

    enc.event_bus.subscribe(LevelUpReady, _auto)

    # «Убиваем» первых четырёх гоблинов — публикуем их смерть в шину.
    for gid in goblin_ids[:4]:
        enc.event_bus.publish(CreatureDied(actor_id=gid))

    assert warrior.xp == 100, "4 гоблина × CR0.25×100 = 100 XP"
    assert ready and ready[-1].to_level == 2, "LevelUpReady на 2 уровень"
    assert warrior.level == 2, "авто level-up поднял воина до 2"

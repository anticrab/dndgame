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
def test_demo_skirmish_loads_with_veteran_vs_two_goblins() -> None:
    _scenario, enc = _build_demo()

    party = [cid for cid, f in enc.factions.items() if f is Faction.PARTY]
    monsters = [cid for cid, f in enc.factions.items() if f is Faction.MONSTERS]
    assert len(party) == 1, "в демо ровно один PC-воин"
    assert len(monsters) == 2, "в демо два гоблина (соло-воину 4–5 непроходимо)"

    warrior = enc.participants[party[0]]
    assert warrior.character_class == "fighter"
    assert warrior.level == 1
    assert warrior.xp == 90, "бывалый воин стартует у порога 2 уровня (90<100)"
    assert warrior.uses_death_saves is True  # PARTY → death saves (страховка драмы)


@pytest.mark.e2e
def test_demo_skirmish_first_kill_crosses_level_threshold() -> None:
    """Старт 90 XP + одно добивание (CR0.25×100=25) = 115 ≥ порога 2 уровня."""
    _scenario, enc = _build_demo()
    warrior = next(
        enc.participants[cid] for cid, f in enc.factions.items() if f is Faction.PARTY
    )
    assert warrior.xp + 25 >= FastXpCurve().threshold(2), (
        "первого добивания должно хватать на level-up в бою"
    )


@pytest.mark.e2e
def test_demo_skirmish_first_kill_triggers_levelup_to_two() -> None:
    """Смерть 1 гоблина → 115 XP → LevelUpReady → авто level-up до 2.

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

    # «Убиваем» первого гоблина — публикуем его смерть в шину.
    enc.event_bus.publish(CreatureDied(actor_id=goblin_ids[0]))

    assert warrior.xp == 115, "90 (старт) + 25 (CR0.25×100) = 115 XP"
    assert ready and ready[-1].to_level == 2, "LevelUpReady на 2 уровень"
    assert warrior.level == 2, "авто level-up поднял воина до 2"

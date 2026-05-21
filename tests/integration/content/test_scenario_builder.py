"""Тесты ``scenario_builder`` — карта + spawns из шаблона.

Грузит реальные ``data/content/scenarios.yaml`` и проверяет, что:

* битфилд имеет правильные размеры и террейн;
* участники созданы с правильными faction;
* Encounter.start() работает.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dnd.application.dto.engine_event import EncounterEnded, EngineEvent
from dnd.application.engine.actions.attack import AttackAction
from dnd.application.engine.actions.weapon_attack import weapon_attack_params
from dnd.application.engine.ai.simple_monster import take_monster_turn
from dnd.application.engine.scenario_builder import (
    build_battlefield_from_map,
    build_encounter_from_scenario,
)
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
from dnd.domain.values.terrain import CLOSED_DOOR, FLOOR, WALL
from dnd.infrastructure.content.yaml_repository import YamlContentRepository

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CONTENT = _REPO_ROOT / "data" / "content"

_MAX_TURNS = 30


@pytest.fixture
def repo() -> YamlContentRepository:
    return YamlContentRepository(_DEFAULT_CONTENT)


def test_mvp_skirmish_battlefield_is_floor(repo: YamlContentRepository) -> None:
    scenario = repo.scenario_by_id("mvp_skirmish")
    bf = build_battlefield_from_map(scenario.map)
    assert isinstance(bf, Battlefield)
    assert bf.width == 5
    assert bf.height == 5
    # Все клетки — FLOOR (легенда содержит только "." → floor).
    for x in range(5):
        for y in range(5):
            assert bf.terrain_at(Square(x, y)) is FLOOR


def test_mvp_room_terrain(repo: YamlContentRepository) -> None:
    scenario = repo.scenario_by_id("mvp_room")
    bf = build_battlefield_from_map(scenario.map)
    # Углы и периметр — WALL.
    assert bf.terrain_at(Square(0, 0)) is WALL
    assert bf.terrain_at(Square(6, 0)) is WALL
    assert bf.terrain_at(Square(0, 4)) is WALL
    assert bf.terrain_at(Square(6, 4)) is WALL
    # Дверь по центру.
    assert bf.terrain_at(Square(3, 2)) is CLOSED_DOOR
    # Внутренние клетки — FLOOR.
    assert bf.terrain_at(Square(1, 1)) is FLOOR


def test_build_encounter_from_mvp_skirmish(repo: YamlContentRepository) -> None:
    """Полный круг: YAML → Encounter с расставленными существами."""
    scenario = repo.scenario_by_id("mvp_skirmish")
    deps, _bus, _rng = build_scripted_dependencies(
        battlefield=Battlefield(1, 1),  # будет заменён в build_encounter
        rolls=[],
    )
    enc = build_encounter_from_scenario(
        scenario, content=repo, deps=deps
    )
    # Участники расставлены и имеют правильные factions.
    assert len(enc.participants) == 2
    assert any(f is Faction.PARTY for f in enc.factions.values())
    assert any(f is Faction.MONSTERS for f in enc.factions.values())
    # Битфилд имеет правильные размеры (заменён builder'ом).
    assert enc.battlefield.width == 5
    assert enc.battlefield.height == 5


def test_e2e_scenario_run_via_yaml(repo: YamlContentRepository) -> None:
    """E2E: бой целиком из YAML-сценария до EncounterEnded."""
    scenario = repo.scenario_by_id("mvp_skirmish")
    rolls = [
        18,  # warrior init: 18+1=19
        8,   # goblin init: 8+2=10 → warrior первый
        18,  # warrior atk: 18+5=23 vs 13 → попал
        7,   # warrior damage 1d8=7; +3 STR = 10 → goblin 7-10 = 0
    ]
    deps, bus, _rng = build_scripted_dependencies(
        battlefield=Battlefield(1, 1), rolls=rolls
    )
    enc = build_encounter_from_scenario(
        scenario, content=repo, deps=deps
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    enc.start()
    turns = 0
    while not enc.is_concluded and turns < _MAX_TURNS:
        turns += 1
        actor_id = enc.current_actor_id
        ctx = enc.start_turn()
        actor = enc.participants[actor_id]
        if not actor.is_alive or actor.is_at_zero_hp:
            enc.end_turn()
            continue
        if enc.factions[actor_id] is Faction.PARTY:
            from dnd.application.dto.action import Allowed

            target_id = next(
                cid for cid, f in enc.factions.items() if f is Faction.MONSTERS
            )
            params = weapon_attack_params(actor, target_id)
            attack = AttackAction()
            if isinstance(attack.can_perform_against(actor, params, ctx), Allowed):
                attack.execute(actor, params, ctx)
        else:
            take_monster_turn(
                actor, ctx, hostile_factions=frozenset({"party"})
            )
        enc.end_turn()

    assert enc.is_concluded is True
    ended = next(e for e in captured if isinstance(e, EncounterEnded))
    assert ended.winners is Faction.PARTY


# -- sanity edges -----------------------------------------------------


def test_build_battlefield_validates_grid_height() -> None:
    from dnd.application.dto.templates import MapTemplate

    bad = MapTemplate(
        width=3, height=3, legend={".": "floor"}, grid=("...", "...")
    )
    with pytest.raises(ValueError, match="rows"):
        build_battlefield_from_map(bad)


def test_build_battlefield_validates_row_width() -> None:
    from dnd.application.dto.templates import MapTemplate

    bad = MapTemplate(
        width=3, height=2, legend={".": "floor"}, grid=("...", "....")
    )
    with pytest.raises(ValueError, match="length"):
        build_battlefield_from_map(bad)


def test_build_battlefield_rejects_unknown_symbol() -> None:
    from dnd.application.dto.templates import MapTemplate

    bad = MapTemplate(
        width=3, height=1, legend={".": "floor"}, grid=("X..",)
    )
    with pytest.raises(ValueError, match="unknown legend symbol"):
        build_battlefield_from_map(bad)

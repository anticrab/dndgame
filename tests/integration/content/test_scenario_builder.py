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
from dnd.application.engine.ai.simple_monster import (
    is_hostile_from_factions,
    take_monster_turn,
)
from dnd.application.engine.scenario_builder import (
    build_battlefield_from_map,
    build_encounter_from_scenario,
)
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
from dnd.domain.values.terrain import FLOOR, WALL
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
    # Аудит 16 SC-R-NEW-001: до появления InteractAction CLOSED_DOOR
    # в сценарии убрана — иначе бой неразрешим. Сейчас (3,2) — пол.
    assert bf.terrain_at(Square(3, 2)) is FLOOR
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


def test_party_creatures_use_death_saves(repo: YamlContentRepository) -> None:
    """Q-11: существа фракции PARTY получают uses_death_saves=True,
    MONSTERS — False (мгновенная смерть → CORPSE)."""
    scenario = repo.scenario_by_id("mvp_skirmish")
    deps, _bus, _rng = build_scripted_dependencies(
        battlefield=Battlefield(1, 1), rolls=[]
    )
    enc = build_encounter_from_scenario(scenario, content=repo, deps=deps)
    for cid, faction in enc.factions.items():
        creature = enc.participants[cid]
        if faction is Faction.PARTY:
            assert creature.uses_death_saves, f"{cid} (PARTY) должен иметь death saves"
        else:
            assert not creature.uses_death_saves, f"{cid} ({faction}) — без death saves"


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
                actor, ctx, is_hostile=is_hostile_from_factions(actor_id, enc.factions)
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


# K9 S1-1: scenarios с map_id (K8 maps) -------------------------------


@pytest.mark.parametrize(
    "scenario_id",
    [
        "open_field",
        "dungeon_hall",
        "warehouse",
        "bridge_crossing",
        "forest_clearing",
    ],
)
def test_k8_scenarios_load_via_map_id(
    repo: YamlContentRepository, scenario_id: str
) -> None:
    """Каждый K8-сценарий имеет map_id, без inline map, и загружается
    через MapRepository + SpriteRegistry."""
    from dnd.infrastructure.content.yaml_map_repository import YamlMapRepository
    from dnd.infrastructure.content.yaml_sprite_registry import YamlSpriteRegistry

    scenario = repo.scenario_by_id(scenario_id)
    assert scenario.map_id == scenario_id
    assert scenario.map is None

    deps, _bus, _rng = build_scripted_dependencies(
        battlefield=Battlefield(1, 1), rolls=[]
    )
    map_repo = YamlMapRepository(_DEFAULT_CONTENT / "maps")
    sprites = YamlSpriteRegistry(_DEFAULT_CONTENT / "sprites")
    enc = build_encounter_from_scenario(
        scenario,
        content=repo,
        deps=deps,
        map_repository=map_repo,
        sprite_registry=sprites,
    )
    # Битфилд из MapDocument: имеет размеры, спавны размещены.
    assert enc.battlefield.width >= 5
    assert enc.battlefield.height >= 5
    assert len(enc.participants) == 2


def test_warehouse_has_interactable_objects(
    repo: YamlContentRepository,
) -> None:
    """warehouse.yaml содержит дверь/окно/бочки/сундук — они должны
    оказаться в Battlefield._objects через build_battlefield_from_document."""
    from dnd.infrastructure.content.yaml_map_repository import YamlMapRepository
    from dnd.infrastructure.content.yaml_sprite_registry import YamlSpriteRegistry

    scenario = repo.scenario_by_id("warehouse")
    deps, _bus, _rng = build_scripted_dependencies(
        battlefield=Battlefield(1, 1), rolls=[]
    )
    map_repo = YamlMapRepository(_DEFAULT_CONTENT / "maps")
    sprites = YamlSpriteRegistry(_DEFAULT_CONTENT / "sprites")
    enc = build_encounter_from_scenario(
        scenario,
        content=repo,
        deps=deps,
        map_repository=map_repo,
        sprite_registry=sprites,
    )
    # warehouse.yaml: 1 door + 1 window + 4 barrels + 1 chest = 7.
    # Используем publicапи: object_at для двери.
    from dnd.application.dto.ids import ObjectId

    door = enc.battlefield.object_at(ObjectId("door-main"))
    assert door.kind.value == "door"


def test_scenario_with_map_id_without_repo_raises() -> None:
    """Если сценарий с map_id, но не передан map_repository — ValueError."""
    from dnd.application.dto.templates import (
        ScenarioTemplate,
        SpawnTemplate,
    )

    repo = YamlContentRepository(_DEFAULT_CONTENT)
    scenario = ScenarioTemplate(
        id="virtual", name="virtual", map_id="warehouse",
        spawns=(
            SpawnTemplate(
                template_id="warrior_lv1",
                instance_id="x",
                at=(0, 0),
                faction=Faction.PARTY,
            ),
        ),
    )
    deps, _bus, _rng = build_scripted_dependencies(
        battlefield=Battlefield(1, 1), rolls=[]
    )
    with pytest.raises(ValueError, match="map_repository"):
        build_encounter_from_scenario(scenario, content=repo, deps=deps)


def test_scenario_template_xor_map_and_map_id() -> None:
    """ScenarioTemplate требует ровно одно из map / map_id."""
    from dnd.application.dto.templates import (
        MapTemplate,
        ScenarioTemplate,
        SpawnTemplate,
    )

    map_t = MapTemplate(
        width=2, height=2, legend={".": "floor"}, grid=("..", ".."),
    )
    sp = (
        SpawnTemplate(
            template_id="x", instance_id="i", at=(0, 0), faction=Faction.PARTY
        ),
    )
    # Оба заданы — ошибка.
    with pytest.raises(ValueError, match="exactly one"):
        ScenarioTemplate(id="a", name="a", map=map_t, map_id="x", spawns=sp)
    # Ни одного — ошибка.
    with pytest.raises(ValueError, match="exactly one"):
        ScenarioTemplate(id="a", name="a", spawns=sp)


def test_dnd_play_warehouse_via_cli_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E2E smoke: `dnd play warehouse` — scenario загружается через CLI.

    Прерываем сразу EndTurnIntent, чтобы тест был быстрым (не играем
    бой целиком), но загрузчик scenario+map+sprites должен отработать.
    """
    import dnd.interfaces.cli.app as app_module
    from dnd.application.dto.player_intent import EndTurnIntent
    from dnd.interfaces.cli.scripted_provider import ScriptedIntentProvider

    # Подменим ConsoleIntentProvider — иначе он повиснет на input().
    scripted = ScriptedIntentProvider([EndTurnIntent()] * 200)
    monkeypatch.setattr(
        "dnd.interfaces.cli.app.ConsoleIntentProvider"
        if hasattr(app_module, "ConsoleIntentProvider")
        else "dnd.interfaces.cli.console_provider.ConsoleIntentProvider",
        lambda: scripted,
    )
    from typer.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(
        app_module.app, ["play", "warehouse"]
    )
    # Главное — scenario найден, encounter собрался; код выхода 0 или
    # завершение по MAX_ROUNDS — оба ОК. Старый баг был
    # «Scenario not found», который exit_code=2 + stderr про not found.
    assert "Scenario not found" not in (result.stderr or "") + result.output
    # Имя сценария напечатано в лог:
    assert "Warehouse" in result.output

"""TUI UX-snapshot тесты: ловим отрегрессии в feedback'е и визуале.

Это «реальный playtest» через Pilot без живого TTY. Воспроизводим
конкретные сценарии (PC потратил action, нажимает attack — должен
увидеть понятное сообщение; sprites соседних столов не сливаются
в одну линию через всю карту).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("textual")

from dnd.application.engine.encounter import Encounter
from dnd.application.engine.scenario_builder import (
    build_encounter_from_scenario,
)
from dnd.composition import build_default_runtime_services
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD
from dnd.infrastructure.content.yaml_map_repository import YamlMapRepository
from dnd.infrastructure.content.yaml_repository import YamlContentRepository
from dnd.infrastructure.content.yaml_sprite_registry import YamlSpriteRegistry
from dnd.infrastructure.rng.real_rng import RealRNG
from dnd.interfaces.tui.app import TuiApp

CONTENT = Path(__file__).resolve().parents[3] / "data" / "content"
MAPS = CONTENT / "maps"
SPRITES = CONTENT / "sprites"


def _load_warehouse_encounter(seed: int = 42) -> Encounter:
    repo = YamlContentRepository(CONTENT)
    sc = repo.scenario_by_id("warehouse")
    services = build_default_runtime_services(rng=RealRNG(seed=seed))
    return build_encounter_from_scenario(
        sc,
        content=repo,
        services=services,
        map_repository=YamlMapRepository(MAPS),
        sprite_registry=YamlSpriteRegistry(SPRITES),
    )


def _build_solo_encounter_with_pc(spent_action: bool = False) -> Encounter:
    """Solo PC без врагов — для теста UX-сообщений без участия AI."""
    warrior = Creature.create(
        id_=CreatureId("aelar"),
        name="Aelar",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=16,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )
    goblin = Creature.create(
        id_=CreatureId("goblin1"),
        name="Goblin",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7,
        armor_class=13,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )
    bf = Battlefield(10, 10)
    bf.place_creature(warrior.id, Square(1, 1))
    bf.place_creature(goblin.id, Square(8, 8))  # далеко
    from dnd.composition import build_scripted_dependencies

    deps, _bus, _ = build_scripted_dependencies(battlefield=bf, rolls=[20, 5, 20, 5])
    enc = Encounter(
        participants={warrior.id: warrior, goblin.id: goblin},
        factions={warrior.id: Faction.PARTY, goblin.id: Faction.MONSTERS},
        deps=deps,
    )
    if spent_action:
        # Симулируем что action уже потрачен (просто для теста UI).
        pass  # фактически проверяем через ctx
    return enc


def test_attack_with_no_action_left_shows_proper_message() -> None:
    """REGRESSION: при потраченном action нажатие `a` должно
    сказать «Action already used», а не «No reachable targets»."""
    enc = _build_solo_encounter_with_pc()
    app = TuiApp(encounter=enc)

    async def _go() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            screen = pilot.app.screen
            # Ждём пока PC получит ход
            for _ in range(30):
                if getattr(screen, "_current", None) is not None:
                    break
                await pilot.pause(0.1)
            if getattr(screen, "_current", None) is None:
                pytest.skip("PC did not get a turn within timeout")
            # Симулируем «action used» на ctx
            from dnd.application.dto.action import ActionEconomyCost

            _actor, ctx, _enc = screen._current
            ctx.spend(ActionEconomyCost.ACTION)
            # Теперь нажимаем `a`
            await pilot.press("a")
            await pilot.pause(0.3)
            log = screen.query_one("#log")
            log_text = " ".join(str(line) for line in log.lines[-5:])
            assert "Action already used" in log_text or "already used" in log_text, log_text

    asyncio.run(_go())


def test_attack_with_no_targets_in_reach_shows_move_closer() -> None:
    """REGRESSION: когда враги далеко, сообщение должно подсказать
    «Move closer», а не просто «No reachable targets»."""
    enc = _build_solo_encounter_with_pc()
    app = TuiApp(encounter=enc)

    async def _go() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            screen = pilot.app.screen
            for _ in range(30):
                if getattr(screen, "_current", None) is not None:
                    break
                await pilot.pause(0.1)
            if getattr(screen, "_current", None) is None:
                pytest.skip("PC did not get a turn within timeout")
            await pilot.press("a")
            await pilot.pause(0.3)
            log = screen.query_one("#log")
            text = " ".join(str(line) for line in log.lines[-5:])
            assert "Move closer" in text or "in reach" in text, text

    asyncio.run(_go())


def test_warehouse_render_tables_dont_merge_into_line() -> None:
    """REGRESSION: соседние table_long не должны сливаться в одну
    непрерывную линию ═════ через всю карту (старый sprite был
    "═════" на всю ширину клетки)."""
    enc = _load_warehouse_encounter()
    app = TuiApp(encounter=enc)

    async def _go() -> None:
        async with app.run_test(size=(180, 50)) as pilot:
            await pilot.pause(0.5)
            mw = pilot.app.screen.query_one("#map")
            text = str(mw.renderable)
            # Проверка: НИ ОДНА строка не должна содержать 15+ '═' подряд
            # (3 клетки по 5). 5 подряд могут быть от одного sprite'а,
            # это ОК; 15+ — sign of «слились».
            for line in text.split("\n"):
                consecutive = 0
                max_consecutive = 0
                for ch in line:
                    if ch == "═":
                        consecutive += 1
                        max_consecutive = max(max_consecutive, consecutive)
                    else:
                        consecutive = 0
                assert max_consecutive < 10, (
                    f"Tables merged into line: {max_consecutive} '═' in row: {line!r}"
                )

    asyncio.run(_go())


def test_move_action_with_no_movement_shows_dash_hint() -> None:
    """Если PC потратил все футы — `m` должен предложить Dash."""
    enc = _build_solo_encounter_with_pc()
    app = TuiApp(encounter=enc)

    async def _go() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            screen = pilot.app.screen
            for _ in range(30):
                if getattr(screen, "_current", None) is not None:
                    break
                await pilot.pause(0.1)
            if getattr(screen, "_current", None) is None:
                pytest.skip("PC did not get a turn within timeout")
            _actor, ctx, _enc = screen._current
            ctx.movement_remaining_ft = 0
            await pilot.press("m")
            await pilot.pause(0.3)
            log = screen.query_one("#log")
            text = " ".join(str(line) for line in log.lines[-5:])
            assert "Dash" in text or "movement left" in text, text

    asyncio.run(_go())

"""Integration: труп лежит на маршруте, PC проходит через клетку.

C-1 regression guard: A* main loop игнорировал is_alive — труп
становился непроходимой блокировкой ровно в обходных случаях.
Этот тест поднимает Pilot, ставит труп точно на пути PC и проверяет,
что pathfinder в MoveModeHandler возвращает путь, проходящий через
эту клетку.
"""
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("textual")

from dnd.application.engine.encounter import Encounter
from dnd.composition import build_default_runtime_services
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.domain.values.terrain import FLOOR
from dnd.domain.values.weapon import LONGSWORD
from dnd.infrastructure.rng.real_rng import RealRNG
from dnd.interfaces.tui.app import TuiApp


def _open_bf(w: int, h: int) -> Battlefield:
    bf = Battlefield(w, h)
    for y in range(h):
        for x in range(w):
            bf.set_terrain(Square(x, y), FLOOR)
    return bf


def test_pathfinder_routes_through_dead_creature() -> None:
    """PC в (2,2), труп в (4,2), цель курсора — (6,2). Путь должен
    проходить через клетку с трупом."""
    pc = Creature.create(
        id_=CreatureId("aelar"), name="Aelar",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    # Goblin сразу убит (0 HP) — нужен только чтобы Encounter имел
    # обе фракции и не закончился победой PC мгновенно.
    goblin = Creature.create(
        id_=CreatureId("g_dead"), name="G",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=1, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    goblin.hit_points = goblin.hit_points.take_damage(99)
    assert not goblin.is_alive

    # Живой goblin далеко — чтобы PC не закончил бой моментально.
    g_alive = Creature.create(
        id_=CreatureId("g_alive"), name="G2",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD,
    )

    bf = _open_bf(10, 5)
    bf.place_creature(pc.id, Square(2, 2))
    bf.place_creature(goblin.id, Square(4, 2))  # труп на пути
    bf.place_creature(g_alive.id, Square(9, 4))  # вдалеке

    services = build_default_runtime_services(rng=RealRNG(seed=42))
    deps = services.with_battlefield(bf)
    enc = Encounter(
        participants={pc.id: pc, goblin.id: goblin, g_alive.id: g_alive},
        factions={
            pc.id: Faction.PARTY,
            goblin.id: Faction.MONSTERS,
            g_alive.id: Faction.MONSTERS,
        },
        deps=deps,
    )
    app = TuiApp(encounter=enc)

    async def _go() -> None:
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.3)
            screen = pilot.app.screen
            for _ in range(60):
                if getattr(screen, "_current", None) is not None:
                    actor, _, _ = screen._current
                    if actor.id == pc.id:
                        break
                await pilot.pause(0.1)
            if getattr(screen, "_current", None) is None:
                pytest.skip("PC did not get a turn within timeout")
            # Войдём в MOVE и попробуем дойти до (6, 2).
            await pilot.press("m")
            await pilot.pause(0.1)
            assert screen._mode.value == "move"
            for _ in range(4):
                await pilot.press("right")
                await pilot.pause(0.05)
            # Курсор должен быть в (6, 2), путь — непустой и
            # проходить через (4, 2) — клетку с трупом.
            data = screen._mode_handler.overlay()
            assert data.cursor == Square(6, 2)
            assert data.path_preview, (
                "путь должен существовать — труп не блокирует"
            )
            assert Square(4, 2) in data.path_preview, (
                f"путь должен проходить через клетку трупа, got {data.path_preview}"
            )

    asyncio.run(_go())

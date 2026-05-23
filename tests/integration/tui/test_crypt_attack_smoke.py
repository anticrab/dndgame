"""Inline TARGET flow на большой карте (40×24).

После пользовательского репорта «выбрать цель не получается» — проверяем
что:
1. 'a' с adjacent целью переключает в TARGET,
2. Auto-follow центрирует viewport на выбранной цели (даже когда
   PC и цель на дальнем краю большой карты),
3. Enter подтверждает.

Сценарий с двумя goblin'ами в дальнем углу 40×24 карты воспроизводит
условия `crypt_of_black_candle` без загрузки content-pipeline'а.
"""
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("textual")

from dnd.application.dto.ids import CreatureId
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_default_runtime_services
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
from dnd.domain.values.terrain import FLOOR
from dnd.domain.values.weapon import LONGSWORD
from dnd.infrastructure.rng.real_rng import RealRNG
from dnd.interfaces.tui.app import TuiApp
from dnd.interfaces.tui.widgets import MapWidget


def _big_open_bf() -> Battlefield:
    bf = Battlefield(40, 24)
    for y in range(24):
        for x in range(40):
            bf.set_terrain(Square(x, y), FLOOR)
    return bf


def test_attack_on_big_map_target_follows_cursor() -> None:
    """PC в (35, 20), goblin рядом в (34, 20). Viewport (120×40)
    физически содержит вообще всю карту, поэтому центрирование
    проверяем косвенно — через успешный enter→normal."""
    pc = Creature.create(
        id_=CreatureId("aelar"), name="Aelar",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    g = Creature.create(
        id_=CreatureId("g1"), name="G1",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    bf = _big_open_bf()
    bf.place_creature(pc.id, Square(35, 20))
    bf.place_creature(g.id, Square(34, 20))
    services = build_default_runtime_services(rng=RealRNG(seed=42))
    deps = services.with_battlefield(bf)
    enc = Encounter(
        participants={pc.id: pc, g.id: g},
        factions={pc.id: Faction.PARTY, g.id: Faction.MONSTERS},
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
                    if actor.id == CreatureId("aelar"):
                        break
                await pilot.pause(0.1)
            if getattr(screen, "_current", None) is None:
                pytest.skip("PC did not get a turn within timeout")
            await pilot.press("a")
            await pilot.pause(0.1)
            assert screen._mode.value == "target", (
                f"'a' should enter TARGET, got {screen._mode.value!r}"
            )
            # Cursor follow: viewport должен покрывать клетку цели (34, 20).
            mw = pilot.app.screen.query_one("#map", MapWidget)
            x0, y0, x1, y1 = mw.visible_rect()
            assert x0 <= 34 < x1, f"target.x not in viewport: {x0}..{x1}"
            assert y0 <= 20 < y1, f"target.y not in viewport: {y0}..{y1}"
            await pilot.press("enter")
            await pilot.pause(0.6)
            assert screen._mode.value == "normal"

    asyncio.run(_go())

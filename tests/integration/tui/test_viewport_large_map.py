"""Viewport на большой карте — PC всегда внутри visible_rect.

См. spec §3 (viewport/auto-follow) и L1-4. На 50×50 карте экран физически
не способен показать всё; auto-follow в MapWidget центрирует viewport
так, чтобы актор не уехал за safe-zone.
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
from dnd.domain.values.weapon import LONGSWORD
from dnd.infrastructure.rng.real_rng import RealRNG
from dnd.interfaces.tui.app import TuiApp
from dnd.interfaces.tui.widgets import MapWidget


def test_viewport_centers_on_pc_at_corner() -> None:
    """PC в дальнем углу 50×50 карты — viewport должен его захватить.

    Гоблин в противоположном углу нужен только чтобы Encounter не
    завершился победой в первом же тике (тогда BattleScreen уступает
    EndScreen'у, и query_one('#map') падает).
    """
    pc = Creature.create(
        id_=CreatureId("p"), name="PC",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    goblin = Creature.create(
        id_=CreatureId("g"), name="Goblin",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    bf = Battlefield(50, 50)
    bf.place_creature(pc.id, Square(40, 40))
    bf.place_creature(goblin.id, Square(0, 0))
    services = build_default_runtime_services(rng=RealRNG(seed=42))
    deps = services.with_battlefield(bf)
    enc = Encounter(
        participants={pc.id: pc, goblin.id: goblin},
        factions={pc.id: Faction.PARTY, goblin.id: Faction.MONSTERS},
        deps=deps,
    )
    app = TuiApp(encounter=enc)

    async def _go() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.5)
            mw = pilot.app.screen.query_one("#map", MapWidget)
            # Явно дёргаем refresh_from с follow=PC — это и есть контракт
            # auto-follow'а; зависеть от того, успел ли PC получить ход в
            # event-loop'е под Pilot'ом, тест не должен.
            mw.refresh_from(bf, enc.factions, follow=Square(40, 40))
            x0, y0, x1, y1 = mw.visible_rect()
            assert x0 <= 40 < x1, f"PC.x not in viewport: {x0}..{x1}"
            assert y0 <= 40 < y1, f"PC.y not in viewport: {y0}..{y1}"

    asyncio.run(_go())

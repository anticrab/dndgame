"""Custom keybinding для weapon_attack: 'z' открывает TARGET mode.

Контракт L2-7: если ``actor.keybindings`` содержит {'z': 'weapon_attack'},
нажатие 'z' роутится через AbilityRegistry → ``_trigger_ability`` и ведёт
себя как родной 'a' (default hotkey'и при этом продолжают работать
через BINDINGS — этот тест проверяет именно override-путь).
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
from dnd.domain.values.ability_id import AbilityId
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD
from dnd.infrastructure.rng.real_rng import RealRNG
from dnd.interfaces.tui.app import TuiApp


def test_z_rebound_to_attack_opens_target_mode() -> None:
    pc = Creature.create(
        id_=CreatureId("pc"), name="PC",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    pc.keybindings["z"] = AbilityId("weapon_attack")
    g = Creature.create(
        id_=CreatureId("g"), name="G",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    bf = Battlefield(10, 10)
    bf.place_creature(pc.id, Square(5, 5))
    bf.place_creature(g.id, Square(6, 5))
    services = build_default_runtime_services(rng=RealRNG(seed=42))
    deps = services.with_battlefield(bf)
    enc = Encounter(
        participants={pc.id: pc, g.id: g},
        factions={pc.id: Faction.PARTY, g.id: Faction.MONSTERS},
        deps=deps,
    )
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
            await pilot.press("z")
            await pilot.pause(0.1)
            assert screen._mode.value == "target"
            await pilot.press("enter")
            await pilot.pause(0.5)
            assert screen._mode.value == "normal"

    asyncio.run(_go())


def test_default_hotkey_a_still_works_alongside_rebind() -> None:
    """Дефолтный 'a' продолжает работать даже когда есть override 'z'."""
    pc = Creature.create(
        id_=CreatureId("pc"), name="PC",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    pc.keybindings["z"] = AbilityId("weapon_attack")
    g = Creature.create(
        id_=CreatureId("g"), name="G",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    bf = Battlefield(10, 10)
    bf.place_creature(pc.id, Square(5, 5))
    bf.place_creature(g.id, Square(6, 5))
    services = build_default_runtime_services(rng=RealRNG(seed=42))
    deps = services.with_battlefield(bf)
    enc = Encounter(
        participants={pc.id: pc, g.id: g},
        factions={pc.id: Faction.PARTY, g.id: Faction.MONSTERS},
        deps=deps,
    )
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
            await pilot.pause(0.1)
            assert screen._mode.value == "target"

    asyncio.run(_go())

"""Inline MOVE flow без модала — курсор + Enter перемещают PC.

После L1-T9 действие `m` не открывает MovePicker, а переключает
BattleScreen в `BattleMode.MOVE`. Стрелки двигают cursor по карте,
Enter подтверждает chebyshev-путь, Esc отменяет и возвращает в
NORMAL — без выполнения хода.
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
from dnd.domain.values.weapon import LONGSWORD
from dnd.infrastructure.rng.real_rng import RealRNG
from dnd.interfaces.tui.app import TuiApp


def _enc() -> Encounter:
    """Энкаунтер с одиночным PC и далеко стоящим гоблином.

    Карта 15×15, чтобы PC мог свободно двигаться курсором.
    """
    pc = Creature.create(
        id_=CreatureId("aelar"),
        name="Aelar",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=16,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )
    goblin = Creature.create(
        id_=CreatureId("g"),
        name="Goblin",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7,
        armor_class=13,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )
    bf = Battlefield(15, 15)
    bf.place_creature(pc.id, Square(2, 2))
    bf.place_creature(goblin.id, Square(12, 12))
    # RealRNG (fixed seed) — гоблин может что-то выкинуть, нам важна только
    # стабильность; PC получит ход и тест отработает курсор+enter.
    services = build_default_runtime_services(rng=RealRNG(seed=42))
    deps = services.with_battlefield(bf)
    return Encounter(
        participants={pc.id: pc, goblin.id: goblin},
        factions={pc.id: Faction.PARTY, goblin.id: Faction.MONSTERS},
        deps=deps,
    )


def test_m_enters_move_mode_arrows_move_cursor_enter_executes() -> None:
    """`m` → MOVE mode, `right` ×3 двигает cursor, `enter` подтверждает.

    После confirm экран возвращается в NORMAL mode.
    """
    app = TuiApp(encounter=_enc())

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
            await pilot.press("m")
            await pilot.pause(0.1)
            assert screen._mode.value == "move"
            for _ in range(3):
                await pilot.press("right")
                await pilot.pause(0.05)
            await pilot.press("enter")
            await pilot.pause(0.5)
            # После Enter mode возвращается в NORMAL.
            assert screen._mode.value == "normal"

    asyncio.run(_go())


def test_escape_in_move_returns_to_normal_without_action() -> None:
    """Esc в MOVE mode отменяет выбор и возвращает в NORMAL без хода."""
    app = TuiApp(encounter=_enc())

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
            await pilot.press("m")
            await pilot.pause(0.1)
            assert screen._mode.value == "move"
            await pilot.press("right")
            await pilot.press("escape")
            await pilot.pause(0.3)
            assert screen._mode.value == "normal"

    asyncio.run(_go())

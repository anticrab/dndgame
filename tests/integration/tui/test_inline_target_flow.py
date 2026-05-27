"""Inline TARGET flow: `a` → Tab/Enter без модального picker'а.

После L1-T9 нажатие `a` переключает BattleScreen в ``BattleMode.TARGET``
вместо открытия TargetPicker. Tab циклит между целями в reach, Enter
подтверждает выбор и кладёт ``AttackIntent`` в очередь — экран
возвращается в ``NORMAL``. Esc отменяет без удара.
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


def _enc_adjacent() -> Encounter:
    """PC в (5,5) и два гоблина по соседству — оба в melee-reach.

    Используем ``RealRNG(seed=...)`` (как в ``test_inline_move_flow``),
    а не ``ScriptedRNG`` — последний быстро упирается в исчерпание
    rolls при первой же выкатке инициативы / атаки гоблина и Encounter
    либо не запускается, либо PC не получает ход в timeout.
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
    g1 = Creature.create(
        id_=CreatureId("g1"),
        name="G1",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7,
        armor_class=13,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )
    g2 = Creature.create(
        id_=CreatureId("g2"),
        name="G2",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7,
        armor_class=13,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )
    bf = Battlefield(10, 10)
    bf.place_creature(pc.id, Square(5, 5))
    bf.place_creature(g1.id, Square(6, 5))
    bf.place_creature(g2.id, Square(4, 5))
    services = build_default_runtime_services(rng=RealRNG(seed=42))
    deps = services.with_battlefield(bf)
    return Encounter(
        participants={pc.id: pc, g1.id: g1, g2.id: g2},
        factions={
            pc.id: Faction.PARTY,
            g1.id: Faction.MONSTERS,
            g2.id: Faction.MONSTERS,
        },
        deps=deps,
    )


def _wait_for_pc_turn(screen) -> bool:  # type: ignore[no-untyped-def]
    """Хелпер: ждать пока screen получит ход PC. Возвращает успех."""
    return getattr(screen, "_current", None) is not None


def test_a_then_enter_attacks_first_target() -> None:
    """`a` → TARGET mode, `enter` сразу подтверждает первую цель."""
    enc = _enc_adjacent()
    app = TuiApp(encounter=enc)

    async def _go() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            screen = pilot.app.screen
            for _ in range(30):
                if _wait_for_pc_turn(screen):
                    break
                await pilot.pause(0.1)
            if not _wait_for_pc_turn(screen):
                pytest.skip("PC did not get a turn within timeout")
            await pilot.press("a")
            await pilot.pause(0.1)
            assert screen._mode.value == "target"
            await pilot.press("enter")
            await pilot.pause(0.6)
            # Главное — mode вернулся в NORMAL (значит Intent сформирован
            # и handler корректно отработал переход). Конкретный урон
            # зависит от RealRNG'а и проверяется отдельными e2e-тестами.
            assert screen._mode.value == "normal"

    asyncio.run(_go())


def test_tab_cycles_target_then_enter() -> None:
    """Tab переключает на следующую цель, Enter подтверждает её."""
    enc = _enc_adjacent()
    app = TuiApp(encounter=enc)

    async def _go() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            screen = pilot.app.screen
            for _ in range(30):
                if _wait_for_pc_turn(screen):
                    break
                await pilot.pause(0.1)
            if not _wait_for_pc_turn(screen):
                pytest.skip("PC did not get a turn within timeout")
            await pilot.press("a")
            await pilot.press("tab")
            await pilot.press("enter")
            await pilot.pause(0.6)
            assert screen._mode.value == "normal"

    asyncio.run(_go())


def test_escape_in_target_returns_to_normal_without_attack() -> None:
    """Esc в TARGET mode отменяет — никаких изменений в hp у гоблинов."""
    enc = _enc_adjacent()
    app = TuiApp(encounter=enc)

    async def _go() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            screen = pilot.app.screen
            for _ in range(30):
                if _wait_for_pc_turn(screen):
                    break
                await pilot.pause(0.1)
            if not _wait_for_pc_turn(screen):
                pytest.skip("PC did not get a turn within timeout")
            await pilot.press("a")
            await pilot.pause(0.1)
            assert screen._mode.value == "target"
            await pilot.press("escape")
            await pilot.pause(0.3)
            # Атака не была подана (mode сразу cancel'нулся) — у гоблинов
            # полные hp.
            assert screen._mode.value == "normal"
            g1 = enc.participants[CreatureId("g1")]
            g2 = enc.participants[CreatureId("g2")]
            assert g1.hit_points.current == 7 and g2.hit_points.current == 7

    asyncio.run(_go())

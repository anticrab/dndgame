"""AbilityMenuScreen — навигация, применение, перебинд (этап S).

Pilot-харнесс через ``asyncio.run`` (как в test_app_smoke — без pytest-asyncio).
"""
from __future__ import annotations

import asyncio

import pytest

try:
    import textual  # noqa: F401
except ImportError:  # pragma: no cover
    pytest.skip("textual not installed", allow_module_level=True)

from textual.app import App

from dnd.application.abilities.ability import Ability
from dnd.application.dto.action import ActionEconomyCost
from dnd.application.dto.player_intent import EndTurnIntent
from dnd.domain.values.ability_id import AbilityId
from dnd.interfaces.tui.screens.ability_menu_screen import AbilityMenuScreen, AbilityRow


def _ab(aid: str) -> Ability:
    return Ability(
        id=AbilityId(aid),
        name=aid,
        icon="*",
        default_hotkey="",
        economy_cost=ActionEconomyCost.ACTION,
        requires_target=False,
        requires_path=False,
        intent_factory=lambda: EndTurnIntent(),
    )


class _Host(App[None]):
    """Минимальный хост, который сразу выталкивает тестируемую модалку."""

    def __init__(self, screen: AbilityMenuScreen) -> None:
        super().__init__()
        self._screen = screen

    def on_mount(self) -> None:
        self.push_screen(self._screen)


def test_navigation_and_apply_selects_row() -> None:
    applied: list[Ability] = []
    rows = [AbilityRow(_ab("a"), "a", True), AbilityRow(_ab("b"), "b", True)]
    scr = AbilityMenuScreen(rows, on_apply=applied.append, on_rebind=lambda *_: None)

    async def _go() -> None:
        async with _Host(scr).run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("down")  # курсор → строка 1
            await pilot.press("enter")  # применить
            await pilot.pause()

    asyncio.run(_go())
    assert len(applied) == 1
    assert applied[0] is rows[1].ability


def test_unavailable_row_not_applied() -> None:
    applied: list[Ability] = []
    rows = [AbilityRow(_ab("a"), "a", False)]  # недоступна
    scr = AbilityMenuScreen(rows, on_apply=applied.append, on_rebind=lambda *_: None)

    async def _go() -> None:
        async with _Host(scr).run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("enter")
            await pilot.pause()

    asyncio.run(_go())
    assert applied == []


def test_rebind_captures_next_key() -> None:
    bound: list[tuple[str, str]] = []
    rows = [AbilityRow(_ab("atk"), "a", True)]
    scr = AbilityMenuScreen(
        rows, on_apply=lambda *_: None, on_rebind=lambda ab, k: bound.append((ab.id, k))
    )

    async def _go() -> None:
        async with _Host(scr).run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("b")  # режим «нажмите клавишу»
            await pilot.press("z")  # назначить z
            await pilot.pause()

    asyncio.run(_go())
    assert bound == [("atk", "z")]


def test_tab_opens_ability_menu_in_battle() -> None:
    """Интеграция: Tab на ходу PC выталкивает AbilityMenuScreen со способностями."""
    from dnd.application.abilities.defaults import register_default_abilities
    from dnd.application.abilities.registry import AbilityRegistry
    from dnd.application.engine.encounter import Encounter
    from dnd.composition import build_scripted_dependencies
    from dnd.domain.entities.battlefield import Battlefield
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ability import AbilityScores
    from dnd.domain.values.faction import Faction
    from dnd.domain.values.ids import CreatureId
    from dnd.domain.values.square import Square
    from dnd.domain.values.weapon import LONGSWORD, SCIMITAR
    from dnd.interfaces.tui.screens.battle import BattleScreen

    reg = AbilityRegistry()
    register_default_abilities(reg)
    bf = Battlefield(5, 5)
    warrior = Creature.create(
        id_=CreatureId("hero"), name="hero",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    gob = Creature.create(
        id_=CreatureId("g"), name="g",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30, equipped_weapon=SCIMITAR,
    )
    bf.place_creature(warrior.id, Square(1, 2))
    bf.place_creature(gob.id, Square(3, 2))
    deps, _bus, _ = build_scripted_dependencies(battlefield=bf, rolls=[20, 1])
    enc = Encounter(
        participants={warrior.id: warrior, gob.id: gob},
        factions={warrior.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    actor = enc.participants[enc.current_actor_id]
    ctx = enc.start_turn()

    class _BattleHost(App[None]):
        def on_mount(self) -> None:
            self._scr = BattleScreen(ability_registry=reg)
            self.push_screen(self._scr)

    async def _go() -> None:
        host = _BattleHost()
        async with host.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.1)
            host._scr.set_active_turn(actor, ctx, enc)
            await pilot.pause(0.05)
            await pilot.press("tab")
            await pilot.pause(0.05)
            assert isinstance(host.screen, AbilityMenuScreen)

    asyncio.run(_go())


def test_esc_from_target_mode_clears_pending_ability() -> None:
    """REV-4: Esc из TARGET (вход через ability) обнуляет _pending_ability —
    иначе следующая атака улетела бы как старая способность."""
    from dnd.application.abilities.defaults import register_default_abilities
    from dnd.application.abilities.registry import AbilityRegistry
    from dnd.application.engine.encounter import Encounter
    from dnd.composition import build_scripted_dependencies
    from dnd.domain.entities.battlefield import Battlefield
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ability import AbilityScores
    from dnd.domain.values.ability_id import AbilityId
    from dnd.domain.values.faction import Faction
    from dnd.domain.values.ids import CreatureId
    from dnd.domain.values.square import Square
    from dnd.domain.values.weapon import LONGSWORD, SCIMITAR
    from dnd.interfaces.tui.screens.battle import BattleScreen

    reg = AbilityRegistry()
    register_default_abilities(reg)
    bf = Battlefield(5, 5)
    warrior = Creature.create(
        id_=CreatureId("hero"), name="hero",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    gob = Creature.create(
        id_=CreatureId("g"), name="g",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30, equipped_weapon=SCIMITAR,
    )
    bf.place_creature(warrior.id, Square(1, 2))
    bf.place_creature(gob.id, Square(2, 2))  # смежно — reach есть
    deps, _bus, _ = build_scripted_dependencies(battlefield=bf, rolls=[20, 1])
    enc = Encounter(
        participants={warrior.id: warrior, gob.id: gob},
        factions={warrior.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    actor = enc.participants[enc.current_actor_id]
    ctx = enc.start_turn()

    class _Host(App[None]):
        def on_mount(self) -> None:
            self._scr = BattleScreen(ability_registry=reg)
            self.push_screen(self._scr)

    async def _go() -> None:
        host = _Host()
        async with host.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.1)
            host._scr.set_active_turn(actor, ctx, enc)
            await pilot.pause(0.05)
            # Войти в TARGET через ability (weapon_attack requires_target).
            host._scr._trigger_ability(reg.get(AbilityId("weapon_attack")))
            await pilot.pause(0.05)
            assert host._scr._pending_ability is not None
            await pilot.press("escape")
            await pilot.pause(0.05)
            assert host._scr._pending_ability is None

    asyncio.run(_go())

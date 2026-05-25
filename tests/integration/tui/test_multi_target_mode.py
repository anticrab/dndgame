"""P2b-7: MultiTargetModeHandler — выбор мультимножества целей с клавиатуры."""
from __future__ import annotations

from dnd.domain.values.ids import CreatureId, SpellId
from dnd.domain.values.square import Square
from dnd.interfaces.tui.screens.battle_modes.multi_target_mode import (
    MultiTargetModeHandler,
)


class _Screen:
    """Минимальный мок ModeScreenContext для MULTI_TARGET."""

    def __init__(self, max_targets: int, allow_repeat: bool) -> None:
        self._current_actor_position = Square(2, 2)
        self._reachable_targets = [
            (CreatureId("A"), Square(3, 2)),
            (CreatureId("B"), Square(4, 2)),
        ]
        self._participants: dict[CreatureId, object] = {}
        self._multi_max_targets = max_targets
        self._multi_allow_repeat = allow_repeat


def test_pick_three_distinct_no_repeat() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=2, allow_repeat=False)
    h.on_enter(screen)
    h.on_key(screen, "space")          # add A (cursor at idx0)
    h.on_key(screen, "tab")            # cursor → B
    h.on_key(screen, "space")          # add B
    h.on_key(screen, "enter")          # confirm
    assert h.confirmed_picks == (CreatureId("A"), CreatureId("B"))


def test_no_repeat_ignores_duplicate() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=3, allow_repeat=False)
    h.on_enter(screen)
    h.on_key(screen, "space")          # add A
    h.on_key(screen, "space")          # повтор A игнорируется (no-repeat)
    h.on_key(screen, "enter")
    assert h.confirmed_picks == (CreatureId("A"),)


def test_repeat_allows_same_target_twice() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=3, allow_repeat=True)
    h.on_enter(screen)
    h.on_key(screen, "space")          # A
    h.on_key(screen, "space")          # A снова (repeat ok)
    h.on_key(screen, "tab")
    h.on_key(screen, "space")          # B
    h.on_key(screen, "enter")
    assert h.confirmed_picks == (CreatureId("A"), CreatureId("A"), CreatureId("B"))


def test_max_targets_caps_picks() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=2, allow_repeat=True)
    h.on_enter(screen)
    h.on_key(screen, "space")          # A
    h.on_key(screen, "space")          # A
    h.on_key(screen, "space")          # сверх лимита → игнор
    h.on_key(screen, "enter")
    assert h.confirmed_picks == (CreatureId("A"), CreatureId("A"))


def test_backspace_removes_last_pick() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=3, allow_repeat=True)
    h.on_enter(screen)
    h.on_key(screen, "space")          # A
    h.on_key(screen, "space")          # A
    h.on_key(screen, "backspace")      # снять последнее A
    h.on_key(screen, "enter")
    assert h.confirmed_picks == (CreatureId("A"),)


def test_enter_with_no_picks_does_not_confirm() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=3, allow_repeat=False)
    h.on_enter(screen)
    h.on_key(screen, "enter")
    assert h.confirmed_picks is None


def test_escape_cancels() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=3, allow_repeat=False)
    h.on_enter(screen)
    h.on_key(screen, "escape")
    assert h.cancelled is True


def test_overlay_shows_counts() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=3, allow_repeat=True)
    h.on_enter(screen)
    h.on_key(screen, "space")          # A
    h.on_key(screen, "space")          # A
    data = h.overlay()
    assert "осталось" in data.hint.lower() or "выбери" in data.hint.lower()
    # выбранная клетка A подсвечена
    assert screen._reachable_targets[0][1] in data.highlights


def test_pilot_magic_missile_multi_target_flow() -> None:
    """Pilot: PC давит '1' (Magic Missile MULTI) → MULTI_TARGET mode →
    выбор двух целей → Enter → CastSpellIntent с target_ids длиной 2."""
    import asyncio
    from pathlib import Path

    import pytest
    pytest.importorskip("textual")

    from dnd.application.dto.player_intent import CastSpellIntent
    from dnd.application.engine.encounter import Encounter
    from dnd.composition import build_default_runtime_services
    from dnd.domain.entities.battlefield import Battlefield
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ability import Ability, AbilityScores
    from dnd.domain.values.faction import Faction
    from dnd.domain.values.terrain import FLOOR
    from dnd.domain.values.weapon import LONGSWORD
    from dnd.infrastructure.content.yaml_spell_repository import YamlSpellRepository
    from dnd.infrastructure.rng.real_rng import RealRNG
    from dnd.interfaces.tui.app import TuiApp
    from dnd.interfaces.tui.screens.battle_modes.protocol import BattleMode

    spells = YamlSpellRepository(
        Path(__file__).resolve().parents[3] / "data" / "content" / "spells.yaml"
    )
    mage = Creature.create(
        id_="aelar", name="Aelar",
        abilities=AbilityScores.of(str_=8, dex=12, con=12, int_=16, wis=10, cha=10),
        max_hp=20, armor_class=12, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    mage.spellcasting_ability = Ability.INT
    mage.known_spells = (SpellId("magic_missile"),)
    mage.spell_slots = {1: 3}
    g1 = Creature.create(
        id_="g1", name="G1",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=12, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    g2 = Creature.create(
        id_="g2", name="G2",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=12, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    bf = Battlefield(10, 10)
    for y in range(10):
        for x in range(10):
            bf.set_terrain(Square(x, y), FLOOR)
    bf.place_creature(mage.id, Square(2, 2))
    bf.place_creature(g1.id, Square(4, 2))
    bf.place_creature(g2.id, Square(5, 2))
    deps = build_default_runtime_services(rng=RealRNG(seed=1)).with_battlefield(bf)
    enc = Encounter(
        participants={mage.id: mage, g1.id: g1, g2.id: g2},
        factions={
            mage.id: Faction.PARTY, g1.id: Faction.MONSTERS, g2.id: Faction.MONSTERS,
        },
        deps=deps,
    )
    app = TuiApp(encounter=enc, spell_repository=spells)
    captured: list[CastSpellIntent] = []

    async def _go() -> None:
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.3)
            screen = pilot.app.screen
            for _ in range(60):
                if getattr(screen, "_current", None) is not None:
                    actor, _, _ = screen._current
                    if actor.id == mage.id:
                        break
                await pilot.pause(0.1)
            if getattr(screen, "_current", None) is None:
                pytest.skip("маг не получил ход")
            orig_put = screen._put_intent

            def _capture(intent: object) -> None:
                if isinstance(intent, CastSpellIntent):
                    captured.append(intent)
                orig_put(intent)

            screen._put_intent = _capture  # type: ignore[method-assign]
            await pilot.press("1")          # Magic Missile → MULTI_TARGET
            await pilot.pause(0.2)
            assert screen._mode is BattleMode.MULTI_TARGET
            await pilot.press("space")      # выбрать g1
            await pilot.press("tab")        # курсор → g2
            await pilot.press("space")      # выбрать g2
            await pilot.press("enter")      # подтвердить
            await pilot.pause(0.3)
            assert screen._mode is BattleMode.NORMAL

    asyncio.run(_go())
    assert captured, "CastSpellIntent не был положен"
    assert captured[0].spell_id == SpellId("magic_missile")
    assert len(captured[0].target_ids) == 2

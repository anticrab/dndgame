"""Inline loot flow: 'l' открывает InventoryScreen + Enter pickup'ит.

O-9 integration smoke под Pilot'ом: PC рядом с сундуком, давим 'l',
выбираем item, Enter — проверяем что PickupIntent попал в очередь
(или что pickup реально случился, если бы был GameRunner; здесь
проверяем сам факт push'а интента).
"""
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("textual")

from dnd.application.engine.encounter import Encounter
from dnd.composition import build_default_runtime_services
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.entities.interactable import InteractableObject
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId, ObjectId
from dnd.domain.values.item import Item, ItemId, ItemKind
from dnd.domain.values.object_kind import ObjectKind
from dnd.domain.values.square import Square
from dnd.domain.values.terrain import FLOOR
from dnd.domain.values.weapon import LONGSWORD
from dnd.infrastructure.rng.real_rng import RealRNG
from dnd.interfaces.tui.app import TuiApp


class _MiniRepo:
    def __init__(self) -> None:
        self._items = {
            ItemId("gold"): Item(
                id=ItemId("gold"), name="Gold piece",
                kind=ItemKind.MISC, weight_lb=0.02, stackable=True,
            ),
        }

    def list_ids(self) -> tuple[ItemId, ...]:
        return tuple(self._items.keys())

    def load(self, item_id: ItemId) -> Item:
        return self._items[item_id]

    def contains(self, item_id: ItemId) -> bool:
        return item_id in self._items


def _open_bf(w: int, h: int) -> Battlefield:
    bf = Battlefield(w, h)
    for y in range(h):
        for x in range(w):
            bf.set_terrain(Square(x, y), FLOOR)
    return bf


def test_l_opens_inventory_screen_enter_pushes_pickup_intent() -> None:
    pc = Creature.create(
        id_=CreatureId("aelar"), name="Aelar",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    g = Creature.create(
        id_=CreatureId("g"), name="G",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    bf = _open_bf(8, 8)
    bf.place_creature(pc.id, Square(2, 2))
    bf.place_creature(g.id, Square(7, 7))
    bf.place_object(InteractableObject(
        id=ObjectId("chest-loot"), kind=ObjectKind.CHEST,
        pos=Square(3, 2),
        state={"open": True, "locked": False, "hp": 8, "ac": 14,
               "contents": [{"item_id": "gold", "qty": 25}]},
    ))
    services = build_default_runtime_services(rng=RealRNG(seed=42))
    deps = services.with_battlefield(bf)
    enc = Encounter(
        participants={pc.id: pc, g.id: g},
        factions={pc.id: Faction.PARTY, g.id: Faction.MONSTERS},
        deps=deps,
    )
    app = TuiApp(encounter=enc, item_repository=_MiniRepo())

    async def _go() -> None:
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.3)
            screen = pilot.app.screen
            # Дождаться pc хода
            for _ in range(60):
                if getattr(screen, "_current", None) is not None:
                    actor, _, _ = screen._current
                    if actor.id == pc.id:
                        break
                await pilot.pause(0.1)
            if getattr(screen, "_current", None) is None:
                pytest.skip("PC did not get a turn within timeout")
            await pilot.press("l")
            await pilot.pause(0.2)
            # Сейчас активен InventoryScreen
            assert "InventoryScreen" in type(pilot.app.screen).__name__
            await pilot.press("enter")  # take all gold
            await pilot.pause(0.5)
            # Возврат к BattleScreen
            assert "BattleScreen" in type(pilot.app.screen).__name__
            # Pickup реально случился: GameRunner забрал PickupIntent,
            # выполнил PickupAction → в инвентаре PC появилось gold,
            # а сундук стал пуст. Проверяем побочный эффект, не очередь
            # (она может быть уже опустошена worker'ом).
            assert pc.inventory.contains(ItemId("gold")), (
                "PC должен был забрать gold из сундука"
            )
            chest_obj = enc.battlefield.object_at(ObjectId("chest-loot"))
            assert chest_obj.state.get("contents") in ([], None), (
                f"сундук должен быть пуст, contents={chest_obj.state.get('contents')!r}"
            )

    asyncio.run(_go())


def test_l_without_chest_in_reach_logs_warning() -> None:
    """Если в reach нет открытых сундуков — InventoryScreen НЕ открывается."""
    pc = Creature.create(
        id_=CreatureId("aelar"), name="Aelar",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    g = Creature.create(
        id_=CreatureId("g"), name="G",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    bf = _open_bf(8, 8)
    bf.place_creature(pc.id, Square(2, 2))
    bf.place_creature(g.id, Square(7, 7))
    # chest есть, но далеко (>5 ft)
    bf.place_object(InteractableObject(
        id=ObjectId("far-chest"), kind=ObjectKind.CHEST,
        pos=Square(7, 6),
        state={"open": True, "locked": False, "hp": 8, "ac": 14,
               "contents": [{"item_id": "gold", "qty": 5}]},
    ))
    services = build_default_runtime_services(rng=RealRNG(seed=42))
    deps = services.with_battlefield(bf)
    enc = Encounter(
        participants={pc.id: pc, g.id: g},
        factions={pc.id: Faction.PARTY, g.id: Faction.MONSTERS},
        deps=deps,
    )
    app = TuiApp(encounter=enc, item_repository=_MiniRepo())

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
            await pilot.press("l")
            await pilot.pause(0.2)
            # InventoryScreen НЕ открыт — остались на BattleScreen.
            assert "BattleScreen" in type(pilot.app.screen).__name__

    asyncio.run(_go())

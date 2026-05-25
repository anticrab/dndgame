"""Q-8/Q-9: при смерти NPC спавнится CORPSE с лутом; лут через Interact+Pickup."""
from __future__ import annotations

from typing import ClassVar

from dnd.application.dto.engine_event import AttackResolved
from dnd.application.engine.actions.interact import (
    InteractAction,
    InteractKind,
    InteractParams,
)
from dnd.application.engine.actions.pickup import PickupAction, PickupParams
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.entities.inventory import Inventory
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageInstance, DamageType
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import ObjectId
from dnd.domain.values.item import Item, ItemId, ItemKind
from dnd.domain.values.object_kind import ObjectKind
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD

_GOLD = Item(id=ItemId("gold"), name="Gold", kind=ItemKind.MISC,
             weight_lb=0.02, stackable=True)


class _Repo:
    _m: ClassVar[dict[ItemId, Item]] = {ItemId("gold"): _GOLD}

    def list_ids(self) -> tuple[ItemId, ...]:
        return tuple(self._m)

    def load(self, item_id: ItemId) -> Item:
        return self._m[item_id]

    def contains(self, item_id: ItemId) -> bool:
        return item_id in self._m


def _pc() -> Creature:
    c = Creature.create(
        id_="hero", name="Hero",
        abilities=AbilityScores.of(str_=14, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=10, armor_class=12, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    c.uses_death_saves = True
    return c


def _goblin_with_gold(qty: int) -> Creature:
    inv = Inventory()
    if qty > 0:
        inv.add(_GOLD, qty)
    return Creature.create(
        id_="gob", name="Goblin",
        abilities=AbilityScores.of(str_=12, dex=14, con=10, int_=8, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD, inventory=inv,
    )


def _enc(pc: Creature, gob: Creature, *, adjacent: bool) -> Encounter:
    bf = Battlefield(8, 8)
    bf.place_creature(pc.id, Square(2, 2))
    bf.place_creature(gob.id, Square(2, 3) if adjacent else Square(6, 6))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[20, 19] + [10] * 30)
    enc = Encounter(
        participants={pc.id: pc, gob.id: gob},
        factions={pc.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    return enc


def _kill_gob(enc: Encounter, pc: Creature, gob: Creature) -> None:
    gob.take_damage(DamageInstance(amount=10, type_=DamageType.SLASHING))
    enc.event_bus.publish(AttackResolved(
        attacker_id=pc.id, target_id=gob.id,
        attack_roll_id="00000000-0000-0000-0000-000000000000",
        hit=True, is_critical=False, downed=True,
    ))


def test_npc_death_spawns_corpse_with_loot() -> None:
    pc, gob = _pc(), _goblin_with_gold(15)
    enc = _enc(pc, gob, adjacent=False)
    _kill_gob(enc, pc, gob)
    corpses = enc.battlefield.objects_at(Square(6, 6))
    assert any(o.kind == ObjectKind.CORPSE for o in corpses)
    corpse = next(o for o in corpses if o.kind == ObjectKind.CORPSE)
    assert corpse.state.get("contents") == [{"item_id": "gold", "qty": 15}]
    assert corpse.state.get("open") is False  # надо открыть Interact'ом


def test_empty_npc_spawns_empty_corpse() -> None:
    pc, gob = _pc(), _goblin_with_gold(0)  # add(0) → пустой инвентарь
    enc = _enc(pc, gob, adjacent=False)
    _kill_gob(enc, pc, gob)
    corpse = next(
        o for o in enc.battlefield.objects_at(Square(6, 6))
        if o.kind == ObjectKind.CORPSE
    )
    assert corpse.state.get("contents") == []


def test_corpse_opens_via_interact() -> None:
    """Interact.OPEN на трупе ставит open=True, contents НЕ очищаются
    (в отличие от сундука — лут идёт через Pickup, не моментально)."""
    pc, gob = _pc(), _goblin_with_gold(15)
    enc = _enc(pc, gob, adjacent=True)
    _kill_gob(enc, pc, gob)
    ctx = enc.start_turn()  # ход PC (gob мёртв, но бой ещё «решается» в end_turn)
    assert enc.current_actor_id == pc.id
    corpse_id = ObjectId("corpse-gob")
    InteractAction().execute(pc, InteractParams(
        target_object_id=corpse_id, kind=InteractKind.OPEN), ctx)
    corpse = enc.battlefield.object_at(corpse_id)
    assert corpse.state["open"] is True
    assert corpse.state["contents"] == [{"item_id": "gold", "qty": 15}]


def test_loot_open_corpse_via_pickup() -> None:
    """PickupAction забирает лут из открытого трупа тем же путём, что из сундука."""
    from dnd.application.dto.action import Allowed
    pc, gob = _pc(), _goblin_with_gold(15)
    enc = _enc(pc, gob, adjacent=True)
    _kill_gob(enc, pc, gob)
    ctx = enc.start_turn()
    assert enc.current_actor_id == pc.id
    corpse_id = ObjectId("corpse-gob")
    corpse = enc.battlefield.object_at(corpse_id)
    corpse.open()  # доменное открытие (без траты экономики хода)
    action = PickupAction(item_repository=_Repo())
    params = PickupParams(target_object_id=corpse_id, item_id=ItemId("gold"))
    # audit C-1: реальный флоу идёт через can_perform_against (GameRunner),
    # а не только execute — проверяем именно его.
    assert isinstance(action.can_perform_against(pc, params, ctx), Allowed)
    out = action.execute(pc, params, ctx)
    assert out.success
    stack = pc.inventory.find_by_id(ItemId("gold"))
    assert stack is not None and stack.qty == 15

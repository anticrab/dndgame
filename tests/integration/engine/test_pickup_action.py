"""PickupAction — забрать предмет из сундука в инвентарь."""
from __future__ import annotations

from dnd.application.dto.action import Allowed, Forbidden, ForbiddenReason
from dnd.application.dto.engine_event import ItemPickedUp
from dnd.application.engine.actions.pickup import PickupAction, PickupParams
from dnd.application.engine.encounter import Encounter
from dnd.application.engine.turn_context import TurnContext
from dnd.application.ports.item_repository import ItemRepository
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.entities.interactable import InteractableObject
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId, ObjectId
from dnd.domain.values.item import Item, ItemId, ItemKind
from dnd.domain.values.object_kind import ObjectKind
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD


class _FakeItemRepo:
    def __init__(self, items: list[Item]) -> None:
        self._by_id = {i.id: i for i in items}

    def list_ids(self) -> tuple[ItemId, ...]:
        return tuple(self._by_id.keys())

    def load(self, item_id: ItemId) -> Item:
        return self._by_id[item_id]

    def contains(self, item_id: ItemId) -> bool:
        return item_id in self._by_id


_GOLD = Item(
    id=ItemId("gold"), name="Gold", kind=ItemKind.MISC,
    weight_lb=0.02, stackable=True,
)
_SWORD = Item(id=ItemId("sword"), name="Sword", kind=ItemKind.WEAPON, weight_lb=3)


def _repo() -> ItemRepository:
    return _FakeItemRepo([_GOLD, _SWORD])


def _setup(
    *,
    chest_contents: list[dict] | list[str] | None,
    chest_locked: bool = False,
    chest_open: bool = True,
    actor_inv_weight_limit: float | None = None,
) -> tuple[Encounter, Creature, TurnContext, InteractableObject]:
    pc = Creature.create(
        id_=CreatureId("aelar"), name="Aelar",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    if actor_inv_weight_limit is not None:
        pc.inventory.weight_limit_lb = actor_inv_weight_limit
    # Фиктивный goblin в углу: иначе Encounter мгновенно завершается
    # как «PARTY won» (нет ни одного MONSTERS) и start_turn() кинет
    # RuntimeError ('encounter is concluded; no more turns').
    goblin = Creature.create(
        id_=CreatureId("g_dummy"), name="G",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    bf = Battlefield(8, 8)
    bf.place_creature(pc.id, Square(2, 2))
    bf.place_creature(goblin.id, Square(7, 7))
    chest = InteractableObject(
        id=ObjectId("chest-1"), kind=ObjectKind.CHEST,
        pos=Square(3, 2),
        state={"open": chest_open, "locked": chest_locked, "hp": 8, "ac": 14,
               "contents": chest_contents or []},
    )
    bf.place_object(chest)
    # rolls=[20]*30 — initiative и checks гарантированно выкатываются.
    # PC с DEX 12 (initiative +1) vs goblin с DEX 14 (+2): чтобы PC шёл
    # первым, нужно либо чтобы у обоих выпал максимум (и tie-breaker
    # отдал PC), либо просто перебираем turn'ы пока не дойдём до PC.
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[20] * 30)
    enc = Encounter(
        participants={pc.id: pc, goblin.id: goblin},
        factions={pc.id: Faction.PARTY, goblin.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    # Дойдём до хода PC: пропускаем чужие ходы.
    while enc.current_actor_id != pc.id:
        enc.start_turn()
        enc.end_turn()
    ctx = enc.start_turn()
    return enc, pc, ctx, chest


# --- happy path -----------------------------------------------------


def test_pickup_partial_qty_from_stackable() -> None:
    enc, pc, ctx, chest = _setup(
        chest_contents=[{"item_id": "gold", "qty": 50}]
    )
    captured: list[ItemPickedUp] = []
    enc.event_bus.subscribe(ItemPickedUp, captured.append)
    action = PickupAction(_repo())
    params = PickupParams(
        target_object_id=chest.id, item_id=ItemId("gold"), qty=20
    )
    assert isinstance(action.can_perform_against(pc, params, ctx), Allowed)
    out = action.execute(pc, params, ctx)
    assert out.success
    assert pc.inventory.find_by_id(ItemId("gold")).qty == 20  # type: ignore[union-attr]
    # В сундуке осталось 30.
    leftover = chest.state["contents"]
    assert leftover == [{"item_id": "gold", "qty": 30}]
    assert captured[0].qty == 20
    assert captured[0].source == "chest:chest-1"


def test_pickup_all_consumes_stack() -> None:
    """qty=None → весь стак; сундук становится пустым."""
    _enc, pc, ctx, chest = _setup(
        chest_contents=[{"item_id": "gold", "qty": 10}]
    )
    action = PickupAction(_repo())
    params = PickupParams(
        target_object_id=chest.id, item_id=ItemId("gold"), qty=None
    )
    out = action.execute(pc, params, ctx)
    assert out.success
    assert pc.inventory.find_by_id(ItemId("gold")).qty == 10  # type: ignore[union-attr]
    assert chest.state["contents"] == []


def test_pickup_non_stackable_removes_one_stack() -> None:
    _enc, pc, ctx, chest = _setup(
        chest_contents=[{"item_id": "sword", "qty": 1}]
    )
    action = PickupAction(_repo())
    params = PickupParams(
        target_object_id=chest.id, item_id=ItemId("sword"),
    )
    action.execute(pc, params, ctx)
    assert pc.inventory.contains(ItemId("sword"))
    assert chest.state["contents"] == []


def test_pickup_legacy_string_contents_works() -> None:
    """Старый формат list[str] тоже должен поддерживаться."""
    _enc, pc, ctx, chest = _setup(chest_contents=["gold", "gold", "gold"])
    action = PickupAction(_repo())
    out = action.execute(
        pc, PickupParams(target_object_id=chest.id, item_id=ItemId("gold")), ctx
    )
    assert out.success
    assert pc.inventory.find_by_id(ItemId("gold")).qty == 3  # type: ignore[union-attr]


# --- forbidden / edge ----------------------------------------------


def test_pickup_locked_chest_forbidden() -> None:
    _enc, pc, ctx, chest = _setup(
        chest_contents=[{"item_id": "gold", "qty": 10}],
        chest_locked=True,
    )
    action = PickupAction(_repo())
    avail = action.can_perform_against(
        pc, PickupParams(target_object_id=chest.id, item_id=ItemId("gold")),
        ctx,
    )
    assert isinstance(avail, Forbidden)
    assert "locked" in (avail.details or "").lower()


def test_pickup_missing_item_forbidden() -> None:
    _enc, pc, ctx, chest = _setup(chest_contents=[{"item_id": "gold", "qty": 5}])
    action = PickupAction(_repo())
    avail = action.can_perform_against(
        pc, PickupParams(target_object_id=chest.id, item_id=ItemId("sword")),
        ctx,
    )
    assert isinstance(avail, Forbidden)
    assert avail.reason is ForbiddenReason.NO_VALID_TARGETS


def test_pickup_out_of_reach_forbidden() -> None:
    _enc, pc, ctx, chest = _setup(chest_contents=[{"item_id": "gold", "qty": 5}])
    # Сдвинем сундук дальше 5 ft.
    chest.pos = Square(4, 4)  # type: ignore[misc]
    action = PickupAction(_repo())
    avail = action.can_perform_against(
        pc, PickupParams(target_object_id=chest.id, item_id=ItemId("gold")),
        ctx,
    )
    assert isinstance(avail, Forbidden)


def test_pickup_no_object_interaction_left() -> None:
    """Уже использовали free interaction в этом ходу → Forbidden."""
    _enc, pc, ctx, chest = _setup(chest_contents=[{"item_id": "gold", "qty": 5}])
    ctx.use_object_interaction()
    action = PickupAction(_repo())
    avail = action.can_perform_against(
        pc, PickupParams(target_object_id=chest.id, item_id=ItemId("gold")),
        ctx,
    )
    assert isinstance(avail, Forbidden)
    assert avail.reason is ForbiddenReason.NO_ECONOMY_LEFT


def test_pickup_inventory_full_returns_failure_without_consuming() -> None:
    """Если рюкзак не вмещает — outcome.success=False, free action
    НЕ должен 'съесться' (audit MAJOR-3): иначе игрок терял ход на
    безрезультатной попытке."""
    _enc, pc, ctx, chest = _setup(
        chest_contents=[{"item_id": "sword", "qty": 1}],
        actor_inv_weight_limit=1.0,  # меч весит 3 lb — не влезет
    )
    assert ctx.can_use_object_interaction(), "стартово free interaction есть"
    action = PickupAction(_repo())
    out = action.execute(
        pc, PickupParams(target_object_id=chest.id, item_id=ItemId("sword")),
        ctx,
    )
    assert not out.success
    assert pc.inventory.slot_count() == 0
    # Сундук не тронут.
    assert chest.state["contents"] == [{"item_id": "sword", "qty": 1}]
    # MAJOR-3: free interaction всё ещё доступен — можно открыть дверь
    # или Interact с другим объектом в этом же ходу.
    assert ctx.can_use_object_interaction()


def test_pickup_from_closed_chest_forbidden() -> None:
    """Audit MAJOR-1: pickup из ЗАКРЫТОГО chest'а недопустим — сначала
    нужен InteractAction.OPEN. Семантика 'open' теряется без этого."""
    _enc, pc, ctx, chest = _setup(
        chest_contents=[{"item_id": "gold", "qty": 5}],
        chest_open=False,  # ← закрытый, но не запертый
    )
    action = PickupAction(_repo())
    avail = action.can_perform_against(
        pc, PickupParams(target_object_id=chest.id, item_id=ItemId("gold")),
        ctx,
    )
    assert isinstance(avail, Forbidden)
    assert "closed" in (avail.details or "").lower()


def test_pickup_emits_item_picked_up_event() -> None:
    """Audit MAJOR-2 regression: ItemPickedUp реально публикуется."""
    enc, pc, ctx, chest = _setup(
        chest_contents=[{"item_id": "gold", "qty": 7}]
    )
    captured: list[ItemPickedUp] = []
    enc.event_bus.subscribe(ItemPickedUp, captured.append)
    action = PickupAction(_repo())
    action.execute(
        pc, PickupParams(target_object_id=chest.id, item_id=ItemId("gold")),
        ctx,
    )
    assert len(captured) == 1
    ev = captured[0]
    assert ev.item_id == ItemId("gold")
    assert ev.qty == 7
    assert ev.source == "chest:chest-1"

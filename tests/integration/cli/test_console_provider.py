"""Тесты ConsoleIntentProvider через подменённые prompt'ы.

Не используем настоящий ``questionary`` — подменяем prompt-функции
своими, чтобы тесты были детерминированными и не требовали TTY.
"""

from __future__ import annotations

from dnd.application.dto.ids import CreatureId, ObjectId
from dnd.application.dto.player_intent import (
    AttackIntent,
    BreakIntent,
    DashIntent,
    DisengageIntent,
    DodgeIntent,
    EndTurnIntent,
    InteractIntent,
    MoveIntent,
    PickupIntent,
)
from dnd.application.engine.actions.interact import InteractKind
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.entities.interactable import InteractableObject
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.item import Item as _Item
from dnd.domain.values.item import ItemId as _ItemId
from dnd.domain.values.item import ItemKind as _ItemKind
from dnd.domain.values.object_kind import ObjectKind
from dnd.domain.values.square import Square
from dnd.domain.values.terrain import WALL
from dnd.domain.values.weapon import LONGSWORD, SCIMITAR
from dnd.interfaces.cli.console_provider import ConsoleIntentProvider


def _build_encounter() -> tuple[Encounter, Creature, Creature]:
    bf = Battlefield(5, 5)
    warrior = Creature.create(
        id_=CreatureId("warrior"),
        name="Warrior",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=16,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )
    goblin = Creature.create(
        id_=CreatureId("goblin"),
        name="Goblin",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7,
        armor_class=13,
        speed_ft=30,
        equipped_weapon=SCIMITAR,
    )
    bf.place_creature(warrior.id, Square(1, 2))
    bf.place_creature(goblin.id, Square(2, 2))
    deps, _bus, _rng = build_scripted_dependencies(
        battlefield=bf, rolls=[18, 8]
    )
    enc = Encounter(
        participants={warrior.id: warrior, goblin.id: goblin},
        factions={warrior.id: Faction.PARTY, goblin.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    return enc, warrior, goblin


def test_console_provider_end_turn_choice() -> None:
    enc, warrior, _g = _build_encounter()
    ctx = enc.start_turn()
    provider = ConsoleIntentProvider(prompt_action=lambda _m, _c: "End turn")
    intent = provider.next_intent(warrior, ctx, enc)
    assert isinstance(intent, EndTurnIntent)


def test_console_provider_dodge_choice() -> None:
    enc, warrior, _g = _build_encounter()
    ctx = enc.start_turn()
    provider = ConsoleIntentProvider(prompt_action=lambda _m, _c: "Dodge")
    intent = provider.next_intent(warrior, ctx, enc)
    assert isinstance(intent, DodgeIntent)


def test_console_provider_dash_choice() -> None:
    enc, warrior, _g = _build_encounter()
    ctx = enc.start_turn()
    provider = ConsoleIntentProvider(prompt_action=lambda _m, _c: "Dash")
    intent = provider.next_intent(warrior, ctx, enc)
    assert isinstance(intent, DashIntent)


def test_console_provider_disengage_choice() -> None:
    enc, warrior, _g = _build_encounter()
    ctx = enc.start_turn()
    provider = ConsoleIntentProvider(prompt_action=lambda _m, _c: "Disengage")
    intent = provider.next_intent(warrior, ctx, enc)
    assert isinstance(intent, DisengageIntent)


def test_console_provider_attack_picks_target_from_list() -> None:
    enc, warrior, goblin = _build_encounter()
    ctx = enc.start_turn()
    captured_choices: list[list[str]] = []

    def fake_choice(_msg: str, choices: list[str]) -> str:
        captured_choices.append(choices)
        return choices[0]

    provider = ConsoleIntentProvider(
        prompt_action=lambda _m, _c: "Attack",
        prompt_choice=fake_choice,
    )
    intent = provider.next_intent(warrior, ctx, enc)
    assert isinstance(intent, AttackIntent)
    assert intent.target_id == goblin.id
    # Список целей содержит хотя бы одного goblin'а.
    assert any("goblin" in label.lower() for label in captured_choices[0])


def test_console_provider_attack_with_no_targets_becomes_end_turn() -> None:
    """Если у actor нет оружия — список целей пуст — EndTurn."""
    enc, warrior, _g = _build_encounter()
    ctx = enc.start_turn()
    # Очищаем оружие в runtime.
    warrior.equipped_weapon = None
    provider = ConsoleIntentProvider(
        prompt_action=lambda _m, _c: "Attack",
    )
    intent = provider.next_intent(warrior, ctx, enc)
    assert isinstance(intent, EndTurnIntent)


def test_console_provider_move_with_valid_coords_builds_path() -> None:
    enc, warrior, _g = _build_encounter()
    ctx = enc.start_turn()
    provider = ConsoleIntentProvider(
        prompt_action=lambda _m, _c: "Move",
        prompt_text=lambda _m: "2,3",
    )
    intent = provider.next_intent(warrior, ctx, enc)
    assert isinstance(intent, MoveIntent)
    # Путь — от (1,2) к (2,3): chebyshev = 1 шаг, диагональ.
    assert intent.path == (Square(2, 3),)


def test_console_provider_move_invalid_text_becomes_end_turn() -> None:
    enc, warrior, _g = _build_encounter()
    ctx = enc.start_turn()
    provider = ConsoleIntentProvider(
        prompt_action=lambda _m, _c: "Move",
        prompt_text=lambda _m: "garbage",
    )
    intent = provider.next_intent(warrior, ctx, enc)
    assert isinstance(intent, EndTurnIntent)


# -- CL-UX001 (audit 15): re-prompt при invalid input ------------------


def test_attack_with_no_targets_reprompts_with_warning() -> None:
    """Аудит 15 CL-UX001: «Attack без целей» → re-prompt, не EndTurn."""
    enc, warrior, _g = _build_encounter()
    ctx = enc.start_turn()
    # Снимаем оружие → нет валидных целей.
    warrior.equipped_weapon = None

    action_seq = iter(["Attack", "Dodge"])
    notifications: list[str] = []
    provider = ConsoleIntentProvider(
        prompt_action=lambda _m, _c: next(action_seq),
        notify=notifications.append,
    )
    intent = provider.next_intent(warrior, ctx, enc)
    # После «Attack без целей» → notify + re-prompt → следующий выбор «Dodge».
    assert isinstance(intent, DodgeIntent)
    assert any("targets" in n.lower() for n in notifications)


def test_move_with_invalid_text_reprompts() -> None:
    """Invalid coord → notify + re-prompt → user пробует снова."""
    enc, warrior, _g = _build_encounter()
    ctx = enc.start_turn()

    action_seq = iter(["Move", "Dodge"])
    text_seq = iter(["garbage"])
    notifications: list[str] = []
    provider = ConsoleIntentProvider(
        prompt_action=lambda _m, _c: next(action_seq),
        prompt_text=lambda _m: next(text_seq),
        notify=notifications.append,
    )
    intent = provider.next_intent(warrior, ctx, enc)
    assert isinstance(intent, DodgeIntent)
    assert any("parse" in n.lower() for n in notifications)


def test_move_out_of_bounds_target_reprompts() -> None:
    """Target за пределами карты → notify + re-prompt."""
    enc, warrior, _g = _build_encounter()
    ctx = enc.start_turn()

    action_seq = iter(["Move", "Dodge"])
    text_seq = iter(["99,99"])
    notifications: list[str] = []
    provider = ConsoleIntentProvider(
        prompt_action=lambda _m, _c: next(action_seq),
        prompt_text=lambda _m: next(text_seq),
        notify=notifications.append,
    )
    intent = provider.next_intent(warrior, ctx, enc)
    assert isinstance(intent, DodgeIntent)
    assert any("out of bounds" in n.lower() for n in notifications)


def test_reprompt_max_depth_falls_back_to_end_turn() -> None:
    """Слишком много re-prompt'ов → принудительно EndTurn (защита)."""
    enc, warrior, _g = _build_encounter()
    ctx = enc.start_turn()
    warrior.equipped_weapon = None  # все Attack бесплодны

    # Всегда выбирает «Attack» — должен сломаться на _MAX_REPROMPTS.
    notifications: list[str] = []
    provider = ConsoleIntentProvider(
        prompt_action=lambda _m, _c: "Attack",
        notify=notifications.append,
    )
    intent = provider.next_intent(warrior, ctx, enc)
    assert isinstance(intent, EndTurnIntent)
    # Финальное warning о принудительном завершении.
    assert any("ending turn" in n.lower() for n in notifications)


def _build_with_chest_and_locked_door() -> tuple[Encounter, Creature]:
    """PC + chest и locked door рядом (для Interact/Break-меню)."""
    bf = Battlefield(5, 5)
    warrior = Creature.create(
        id_=CreatureId("warrior"),
        name="Warrior",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    goblin = Creature.create(
        id_=CreatureId("goblin"),
        name="Goblin",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30, equipped_weapon=SCIMITAR,
    )
    bf.place_creature(warrior.id, Square(2, 2))
    bf.place_creature(goblin.id, Square(4, 4))
    # Сундук смежно — для Interact.
    bf.place_object(InteractableObject(
        id=ObjectId("chest-1"), kind=ObjectKind.CHEST, pos=Square(3, 2),
        state={"open": False, "locked": False, "hp": 8, "ac": 14},
    ))
    # Запертая дверь — Interact + Break (hp есть → попадёт и в break menu).
    bf.place_object(InteractableObject(
        id=ObjectId("door-1"), kind=ObjectKind.DOOR, pos=Square(2, 1),
        state={"open": False, "locked": True, "hp": 10, "ac": 13},
    ))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[20] * 10)
    enc = Encounter(
        participants={warrior.id: warrior, goblin.id: goblin},
        factions={warrior.id: Faction.PARTY, goblin.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    return enc, warrior


def test_interact_lists_objects_in_reach_and_builds_intent() -> None:
    enc, warrior = _build_with_chest_and_locked_door()
    ctx = enc.start_turn()
    action_seq = iter(["Interact"])
    # Меню целей предлагает [chest-1, door-1] — выбираем chest.
    choice_seq = iter(["chest-1 (chest) at (3,2)"])
    provider = ConsoleIntentProvider(
        prompt_action=lambda _m, _c: next(action_seq),
        prompt_choice=lambda _m, _c: next(choice_seq),
    )
    intent = provider.next_intent(warrior, ctx, enc)
    assert isinstance(intent, InteractIntent)
    assert intent.target_object_id == ObjectId("chest-1")
    assert intent.interact_kind is InteractKind.OPEN


def test_break_filters_breakable_only_and_builds_intent() -> None:
    enc, warrior = _build_with_chest_and_locked_door()
    ctx = enc.start_turn()
    action_seq = iter(["Break"])
    # И chest, и door имеют hp — оба попадают в меню Break.
    choice_seq = iter(["door-1 (door) at (2,1)"])
    provider = ConsoleIntentProvider(
        prompt_action=lambda _m, _c: next(action_seq),
        prompt_choice=lambda _m, _c: next(choice_seq),
    )
    intent = provider.next_intent(warrior, ctx, enc)
    assert isinstance(intent, BreakIntent)
    assert intent.target_object_id == ObjectId("door-1")


def test_interact_no_objects_in_reach_reprompts() -> None:
    """PC в одиночестве — Interact даёт notify + новый prompt."""
    enc, warrior, _ = _build_encounter()  # warrior в (1,2), goblin в (2,2)
    # Удалим goblin'а; объектов в reach всё равно нет.
    enc.battlefield.remove_creature(CreatureId("goblin"))
    ctx = enc.start_turn()
    notifications: list[str] = []
    action_seq = iter(["Interact", "Dodge"])
    provider = ConsoleIntentProvider(
        prompt_action=lambda _m, _c: next(action_seq),
        notify=notifications.append,
    )
    intent = provider.next_intent(warrior, ctx, enc)
    assert isinstance(intent, DodgeIntent)
    assert any("no interactable" in n.lower() for n in notifications)


def test_move_unreachable_target_reprompts() -> None:
    """Стена между PC и целью → CLI должен сказать «unreachable»
    (раньше chebyshev строил путь через стену, а MoveAction отказывал
    после хода — теряли ход незаметно)."""
    enc, warrior, _ = _build_encounter()  # warrior в (1,2)
    bf = enc.battlefield
    # Стенами огораживаем (3,3) полностью (включая 8 соседей кроме
    # тех, что заняты creature'ами — pathfinder и так их учтёт).
    for sq in (Square(2, 3), Square(3, 2), Square(2, 2), Square(4, 3),
               Square(3, 4), Square(4, 4), Square(4, 2), Square(2, 4)):
        if not bf.creatures_at(sq):
            bf.set_terrain(sq, WALL)
    ctx = enc.start_turn()
    notifications: list[str] = []
    action_seq = iter(["Move", "Dodge"])
    text_seq = iter(["3,3"])
    provider = ConsoleIntentProvider(
        prompt_action=lambda _m, _c: next(action_seq),
        prompt_text=lambda _m: next(text_seq),
        notify=notifications.append,
    )
    intent = provider.next_intent(warrior, ctx, enc)
    assert isinstance(intent, DodgeIntent)
    assert any("unreachable" in n.lower() for n in notifications)


# === O-10: CLI Pickup ================================================


class _MiniItemRepo:
    def __init__(self) -> None:
        self._items = {
            _ItemId("gold"): _Item(
                id=_ItemId("gold"), name="Gold piece",
                kind=_ItemKind.MISC, weight_lb=0.02, stackable=True,
            ),
            _ItemId("sword"): _Item(
                id=_ItemId("sword"), name="Longsword",
                kind=_ItemKind.WEAPON, weight_lb=3.0,
            ),
        }

    def list_ids(self):
        return tuple(self._items.keys())

    def load(self, item_id):
        return self._items[item_id]

    def contains(self, item_id):
        return item_id in self._items


def _build_with_chest_loot() -> tuple[Encounter, Creature]:
    """PC + сундук с лутом в reach."""
    bf = Battlefield(5, 5)
    warrior = Creature.create(
        id_=CreatureId("warrior"), name="Warrior",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    goblin = Creature.create(
        id_=CreatureId("goblin"), name="Goblin",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30, equipped_weapon=SCIMITAR,
    )
    bf.place_creature(warrior.id, Square(2, 2))
    bf.place_creature(goblin.id, Square(4, 4))
    bf.place_object(InteractableObject(
        id=ObjectId("chest-loot"), kind=ObjectKind.CHEST,
        pos=Square(3, 2),
        state={"open": False, "locked": False, "hp": 8, "ac": 14,
               "contents": [
                   {"item_id": "gold", "qty": 25},
                   {"item_id": "sword", "qty": 1},
               ]},
    ))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[20] * 10)
    enc = Encounter(
        participants={warrior.id: warrior, goblin.id: goblin},
        factions={warrior.id: Faction.PARTY, goblin.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    return enc, warrior


def test_pickup_menu_builds_intent_with_named_items() -> None:
    """С item_repository — меню показывает 'Gold piece ×25 (gold)' и
    собирает PickupIntent с указанным item_id и qty."""
    enc, warrior = _build_with_chest_loot()
    ctx = enc.start_turn()
    action_seq = iter(["Pickup"])
    # 1) выбор сундука  2) выбор item — берём gold  3) qty=10
    choice_seq = iter([
        "chest-loot at (3,2)",  # шаг 1
        "Gold piece ×25 (gold)",  # шаг 2
    ])
    text_seq = iter(["10"])  # qty
    provider = ConsoleIntentProvider(
        prompt_action=lambda _m, _c: next(action_seq),
        prompt_choice=lambda _m, _c: next(choice_seq),
        prompt_text=lambda _m: next(text_seq),
        item_repository=_MiniItemRepo(),
    )
    intent = provider.next_intent(warrior, ctx, enc)
    assert isinstance(intent, PickupIntent)
    assert intent.target_object_id == ObjectId("chest-loot")
    assert intent.item_id == _ItemId("gold")
    assert intent.qty == 10


def test_pickup_qty_all_means_none() -> None:
    enc, warrior = _build_with_chest_loot()
    ctx = enc.start_turn()
    action_seq = iter(["Pickup"])
    choice_seq = iter([
        "chest-loot at (3,2)",
        "Longsword ×1 (sword)",
    ])
    text_seq = iter(["all"])  # → None
    provider = ConsoleIntentProvider(
        prompt_action=lambda _m, _c: next(action_seq),
        prompt_choice=lambda _m, _c: next(choice_seq),
        prompt_text=lambda _m: next(text_seq),
        item_repository=_MiniItemRepo(),
    )
    intent = provider.next_intent(warrior, ctx, enc)
    assert isinstance(intent, PickupIntent)
    assert intent.qty is None


def test_pickup_without_chests_in_reach_reprompts() -> None:
    """PC далеко от любых chest'ов — Pickup даёт notify + новое меню."""
    enc, warrior, _ = _build_encounter()  # warrior в (1,2), goblin в (2,2), нет chest'ов
    ctx = enc.start_turn()
    notifications: list[str] = []
    action_seq = iter(["Pickup", "Dodge"])
    provider = ConsoleIntentProvider(
        prompt_action=lambda _m, _c: next(action_seq),
        notify=notifications.append,
        item_repository=_MiniItemRepo(),
    )
    intent = provider.next_intent(warrior, ctx, enc)
    assert isinstance(intent, DodgeIntent)
    assert any("no open chests" in n.lower() for n in notifications)


def test_pickup_works_without_item_repository_with_raw_ids() -> None:
    """Fallback: без repository меню показывает сырые id, intent
    всё равно собирается корректно."""
    enc, warrior = _build_with_chest_loot()
    ctx = enc.start_turn()
    action_seq = iter(["Pickup"])
    choice_seq = iter(["chest-loot at (3,2)", "gold ×25"])
    text_seq = iter([""])  # пустой qty = None
    provider = ConsoleIntentProvider(
        prompt_action=lambda _m, _c: next(action_seq),
        prompt_choice=lambda _m, _c: next(choice_seq),
        prompt_text=lambda _m: next(text_seq),
        # item_repository=None
    )
    intent = provider.next_intent(warrior, ctx, enc)
    assert isinstance(intent, PickupIntent)
    assert intent.item_id == _ItemId("gold")
    assert intent.qty is None

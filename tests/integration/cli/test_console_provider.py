"""Тесты ConsoleIntentProvider через подменённые prompt'ы.

Не используем настоящий ``questionary`` — подменяем prompt-функции
своими, чтобы тесты были детерминированными и не требовали TTY.
"""

from __future__ import annotations

from dnd.application.dto.ids import CreatureId
from dnd.application.dto.player_intent import (
    AttackIntent,
    DashIntent,
    DisengageIntent,
    DodgeIntent,
    EndTurnIntent,
    MoveIntent,
)
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
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

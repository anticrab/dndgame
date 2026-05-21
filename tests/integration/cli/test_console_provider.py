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

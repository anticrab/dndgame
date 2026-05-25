"""Default-регистрации базовых ability'ев.

6 умений = 6 hotkey'ев, которые уже жёстко зашиты в BINDINGS
``BattleScreen``-а на момент L2-3: Attack/Dodge/Dash/Disengage/
Interact/Break. После L2-7 hotkey'и поедут именно через registry, и
``BattleScreen.BINDINGS`` смогут собираться динамически из
``register_default_abilities`` + ``Creature.keybindings``.

Move — намеренно НЕ ability: это MOVEMENT, не ACTION, отдельный
hotkey ``m`` BattleScreen'а с собственным MoveModeHandler'ом.

Help/Search/Spell-casting и т.п. — в plan'e L3+, пока в коде нет
HelpIntent/SearchIntent — добавим вместе с самими intent'ами, чтобы
не плодить «висящие» зарегистрированные умения без рабочей фабрики.
"""
from __future__ import annotations

from dnd.application.abilities.ability import Ability, AbilityId
from dnd.application.abilities.registry import AbilityRegistry
from dnd.application.dto.action import ActionEconomyCost
from dnd.application.dto.ids import CreatureId, ObjectId
from dnd.application.dto.player_intent import (
    AttackIntent,
    BreakIntent,
    DashIntent,
    DisengageIntent,
    DodgeIntent,
    InteractIntent,
    PlayerIntent,
    StabilizeIntent,
)
from dnd.application.engine.actions.interact import InteractKind


def _attack(target_id: CreatureId) -> PlayerIntent:
    return AttackIntent(target_id=target_id)


def _dodge() -> PlayerIntent:
    return DodgeIntent()


def _dash() -> PlayerIntent:
    return DashIntent()


def _disengage() -> PlayerIntent:
    return DisengageIntent()


def _interact(target_id: CreatureId) -> PlayerIntent:
    # ``target_id`` — это CreatureId-обёртка над str (см. action_intent_interact
    # в BattleScreen). InteractIntent ждёт ObjectId; конвертация
    # явная — типы разные, str один и тот же.
    return InteractIntent(
        target_object_id=ObjectId(str(target_id)),
        interact_kind=InteractKind.OPEN,
    )


def _break(target_id: CreatureId) -> PlayerIntent:
    return BreakIntent(target_object_id=ObjectId(str(target_id)))


def _stabilize(target_id: CreatureId) -> PlayerIntent:
    return StabilizeIntent(target_id=target_id)


def register_default_abilities(registry: AbilityRegistry) -> None:
    """Регистрирует 6 базовых умений с дефолтными hotkey'ями.

    Хоткеи синхронизированы с действующими ``BattleScreen.BINDINGS``:
    a (attack), d (dodge), h (dash — «hustle»), g (disengage), i (interact),
    k (break). Совпадение нужно, чтобы L2-7 wiring через registry не сменил
    управление под игроком — ``Creature.keybindings`` всё ещё может это
    переопределить per-creature.
    """
    registry.register(Ability(
        id=AbilityId("weapon_attack"), name="Attack", icon="A",
        default_hotkey="a", economy_cost=ActionEconomyCost.ACTION,
        requires_target=True, requires_path=False,
        intent_factory=_attack,
    ))
    registry.register(Ability(
        id=AbilityId("dodge"), name="Dodge", icon="D",
        default_hotkey="d", economy_cost=ActionEconomyCost.ACTION,
        requires_target=False, requires_path=False,
        intent_factory=_dodge,
    ))
    registry.register(Ability(
        id=AbilityId("dash"), name="Dash", icon="H",
        default_hotkey="h", economy_cost=ActionEconomyCost.ACTION,
        requires_target=False, requires_path=False,
        intent_factory=_dash,
    ))
    registry.register(Ability(
        id=AbilityId("disengage"), name="Disengage", icon="G",
        default_hotkey="g", economy_cost=ActionEconomyCost.ACTION,
        requires_target=False, requires_path=False,
        intent_factory=_disengage,
    ))
    registry.register(Ability(
        id=AbilityId("interact"), name="Interact", icon="I",
        default_hotkey="i", economy_cost=ActionEconomyCost.FREE,
        requires_target=True, requires_path=False,
        intent_factory=_interact,
    ))
    registry.register(Ability(
        id=AbilityId("break_object"), name="Break", icon="K",
        default_hotkey="k", economy_cost=ActionEconomyCost.ACTION,
        requires_target=True, requires_path=False,
        intent_factory=_break,
    ))
    registry.register(Ability(
        id=AbilityId("stabilize"), name="Stabilize", icon="S",
        default_hotkey="s", economy_cost=ActionEconomyCost.ACTION,
        requires_target=True, requires_path=False,
        intent_factory=_stabilize,
    ))


__all__ = ["register_default_abilities"]

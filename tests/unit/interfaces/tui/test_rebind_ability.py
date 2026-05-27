"""rebind_ability / ability_can_afford — хелперы меню способностей (этап S)."""
from __future__ import annotations

from dnd.application.abilities.ability import Ability
from dnd.application.dto.action import ActionEconomyCost
from dnd.application.engine.turn_context import TurnContext
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ability_id import AbilityId
from dnd.domain.values.ids import CreatureId
from dnd.interfaces.tui.screens.keymap import ability_can_afford, rebind_ability


def _actor() -> Creature:
    return Creature.create(
        id_=CreatureId("hero"),
        name="hero",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10,
        armor_class=10,
        speed_ft=30,
    )


def test_rebind_sets_keybinding() -> None:
    actor = _actor()
    rebind_ability(actor, "z", AbilityId("weapon_attack"))
    assert actor.keybindings["z"] == AbilityId("weapon_attack")


def test_rebind_clears_previous_key_of_same_ability() -> None:
    """Одна способность не должна висеть на двух клавишах."""
    actor = _actor()
    actor.keybindings["z"] = AbilityId("weapon_attack")
    rebind_ability(actor, "x", AbilityId("weapon_attack"))
    assert "z" not in actor.keybindings
    assert actor.keybindings["x"] == AbilityId("weapon_attack")


def test_rebind_overwrites_other_ability_on_that_key() -> None:
    """Одна клавиша = одна способность: новый бинд вытесняет старую."""
    actor = _actor()
    actor.keybindings["z"] = AbilityId("dodge")
    rebind_ability(actor, "z", AbilityId("weapon_attack"))
    assert actor.keybindings["z"] == AbilityId("weapon_attack")


def _ctx(actor: Creature) -> TurnContext:
    bf = Battlefield(3, 3)
    deps, _bus, _rng = build_scripted_dependencies(battlefield=bf, rolls=[])
    return TurnContext(
        actor_id=actor.id,
        battlefield=deps.battlefield,
        dice_roller=deps.dice_roller,
        modifier_applier=deps.modifier_applier,
        condition_service=deps.condition_service,
        event_bus=deps.event_bus,
        rng=deps.rng,
        participants={actor.id: actor},
        movement_remaining_ft=actor.speed_ft,
    )


def _ability(cost: ActionEconomyCost) -> Ability:
    from dnd.application.dto.player_intent import EndTurnIntent

    return Ability(
        id=AbilityId("x"),
        name="X",
        icon="*",
        default_hotkey="",
        economy_cost=cost,
        requires_target=False,
        requires_path=False,
        intent_factory=lambda: EndTurnIntent(),
    )


def test_ability_can_afford_action_until_spent() -> None:
    actor = _actor()
    ctx = _ctx(actor)
    ab = _ability(ActionEconomyCost.ACTION)
    assert ability_can_afford(ab, ctx) is True
    ctx.spend(ActionEconomyCost.ACTION)
    assert ability_can_afford(ab, ctx) is False


def test_bonus_ability_still_afforded_after_action_spent() -> None:
    actor = _actor()
    ctx = _ctx(actor)
    ctx.spend(ActionEconomyCost.ACTION)
    ab = _ability(ActionEconomyCost.BONUS_ACTION)
    assert ability_can_afford(ab, ctx) is True

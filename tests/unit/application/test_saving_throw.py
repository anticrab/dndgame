"""T1: единый бросок спасброска с учётом профициентности класса."""
from __future__ import annotations

from dnd.application.engine.saving_throw import roll_saving_throw, saving_throw_bonus
from dnd.application.engine.turn_context import TurnContext
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.ids import CreatureId


def _actor(*, con_prof: bool) -> Creature:
    c = Creature.create(
        id_=CreatureId("h"), name="h",
        abilities=AbilityScores.of(str_=10, dex=10, con=14, int_=10, wis=10, cha=10),
        max_hp=10, armor_class=10, speed_ft=30,
    )
    c.proficiency_bonus = 2
    if con_prof:
        c.saving_throw_proficiencies = frozenset({Ability.CON})
    return c


def _ctx(actor: Creature, rolls: list[int]) -> TurnContext:
    bf = Battlefield(3, 3)
    deps, _bus, _rng = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    return TurnContext(
        actor_id=actor.id, battlefield=deps.battlefield,
        dice_roller=deps.dice_roller, modifier_applier=deps.modifier_applier,
        condition_service=deps.condition_service, event_bus=deps.event_bus,
        rng=deps.rng, participants={actor.id: actor},
        movement_remaining_ft=actor.speed_ft,
    )


def test_saving_throw_bonus_with_and_without_proficiency() -> None:
    assert saving_throw_bonus(_actor(con_prof=True), Ability.CON) == 4  # +2 mod +2 prof
    assert saving_throw_bonus(_actor(con_prof=False), Ability.CON) == 2  # только +2 mod


def test_proficient_save_adds_proficiency() -> None:
    actor = _actor(con_prof=True)
    # d20=10 + CON(2) + prof(2) = 14 ≥ DC 13 → успех
    assert roll_saving_throw(actor, Ability.CON, dc=13, ctx=_ctx(actor, [10])) is True


def test_nonproficient_save_no_proficiency() -> None:
    actor = _actor(con_prof=False)
    # d20=10 + CON(2) = 12 < DC 13 → провал (prof не добавился)
    assert roll_saving_throw(actor, Ability.CON, dc=13, ctx=_ctx(actor, [10])) is False


def test_roll_saving_throw_raw_uses_services() -> None:
    """raw-вариант не требует TurnContext — берёт службы напрямую."""
    from dnd.application.engine.saving_throw import roll_saving_throw_raw
    from dnd.composition import build_scripted_dependencies
    from dnd.domain.entities.battlefield import Battlefield
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ability import Ability, AbilityScores
    from dnd.domain.values.ids import CreatureId

    deps, _bus, _rng = build_scripted_dependencies(
        battlefield=Battlefield(1, 1), rolls=[10]
    )
    actor = Creature.create(
        id_=CreatureId("a"), name="a",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=14, cha=10),
        max_hp=10, armor_class=10, speed_ft=30,
    )
    # d20=10 + WIS(+2) = 12 >= 12 → успех.
    assert roll_saving_throw_raw(
        actor, Ability.WIS, dc=12,
        dice_roller=deps.dice_roller, modifier_applier=deps.modifier_applier,
    ) is True

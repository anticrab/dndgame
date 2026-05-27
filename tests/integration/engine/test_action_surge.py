"""R1-11: Action Surge — даёт дополнительное действие в текущем ходу."""

from __future__ import annotations

from dnd.application.dto.action import ActionEconomyCost, Forbidden
from dnd.application.engine.actions.action_surge import (
    ActionSurgeAction,
    ActionSurgeParams,
)
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square


def _setup() -> tuple[Creature, object]:
    f = Creature.create(
        id_="f",
        name="F",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=16,
        speed_ft=30,
    )
    f.character_class = "fighter"
    f.level = 2
    f.resource_uses = {"action_surge": 1}
    gob = Creature.create(
        id_="gob",
        name="Gob",
        abilities=AbilityScores.of(str_=8, dex=8, con=10, int_=8, wis=8, cha=8),
        max_hp=12,
        armor_class=13,
        speed_ft=30,
    )
    bf = Battlefield(8, 8)
    bf.place_creature(f.id, Square(1, 1))
    bf.place_creature(gob.id, Square(6, 6))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[20, 1])
    enc = Encounter(
        participants={f.id: f, gob.id: gob},
        factions={f.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    for _ in range(12):
        if enc.current_actor_id == f.id:
            break
        enc.start_turn()
        enc.end_turn()
    ctx = enc.start_turn()
    return f, ctx


def test_action_surge_refreshes_action() -> None:
    f, ctx = _setup()
    ctx.spend(ActionEconomyCost.ACTION)  # потратили действие
    assert ctx.action_used is True
    out = ActionSurgeAction().execute(f, ActionSurgeParams(), ctx)
    assert out.success
    assert ctx.action_used is False  # действие снова доступно
    assert f.resource_uses["action_surge"] == 0


def test_action_surge_forbidden_without_use() -> None:
    f, ctx = _setup()
    f.resource_uses["action_surge"] = 0
    avail = ActionSurgeAction().can_perform_against(f, ActionSurgeParams(), ctx)
    assert isinstance(avail, Forbidden)

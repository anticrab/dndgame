"""Тест ``format_status`` (pure-функция StatusWidget).

Покрытие:
* без TurnContext — короткая строка;
* с TurnContext — добавляется блок экономии действий.
"""

from __future__ import annotations

from dnd.application.dto.action import ActionEconomyCost
from dnd.application.dto.ids import CreatureId
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD
from dnd.interfaces.tui.widgets.status_widget import format_status

from ._fixtures import build_minimal_ctx


def _hero() -> Creature:
    return Creature.create(
        id_=CreatureId("aelar"),
        name="Aelar",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=12,
        armor_class=16,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )


def test_status_without_ctx_is_compact() -> None:
    line = format_status(_hero(), None)
    assert "Aelar" in line
    assert "HP 12/12" in line
    assert "AC 16" in line
    assert "Spd 30ft" in line
    assert "act:" not in line  # без ctx — нет экономии


def test_status_with_ctx_shows_economy_flags() -> None:
    hero = _hero()
    bf = Battlefield(3, 3)
    bf.place_creature(hero.id, Square(0, 0))
    ctx = build_minimal_ctx(actor=hero, battlefield=bf)
    line = format_status(hero, ctx)
    assert "act:Y" in line  # action ещё не потрачен
    assert "bonus:Y" in line
    assert f"move:{hero.speed_ft}ft" in line


def test_status_with_used_action_shows_N() -> None:
    hero = _hero()
    bf = Battlefield(3, 3)
    bf.place_creature(hero.id, Square(0, 0))
    ctx = build_minimal_ctx(actor=hero, battlefield=bf)
    ctx.spend(ActionEconomyCost.ACTION)
    line = format_status(hero, ctx)
    assert "act:N" in line
    assert "bonus:Y" in line

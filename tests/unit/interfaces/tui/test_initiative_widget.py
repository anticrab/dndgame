"""Тест ``format_initiative`` — pure-функция InitiativeWidget."""

from __future__ import annotations

from uuid import uuid4

from dnd.application.dto.initiative import InitiativeEntry
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageInstance, DamageType
from dnd.domain.values.ids import CreatureId, RollId
from dnd.interfaces.tui.widgets.initiative_widget import format_initiative


def _make_creature(name: str, *, alive: bool = True) -> Creature:
    c = Creature.create(
        id_=CreatureId(name.lower()),
        name=name,
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10,
        armor_class=10,
        speed_ft=30,
        equipped_weapon=None,
    )
    if not alive:
        # Снимаем все хиты — Creature становится "поверженным" (is_alive=False).
        c.take_damage(DamageInstance(amount=20, type_=DamageType.SLASHING))
    return c


def _entry(cid: str, total: int, order: int) -> InitiativeEntry:
    return InitiativeEntry(
        creature_id=CreatureId(cid),
        total=total,
        d20_raw=total,
        dex_score=10,
        insertion_order=order,
        roll_id=RollId(uuid4()),
    )


def test_active_actor_marker() -> None:
    hero = _make_creature("Hero")
    goblin = _make_creature("Goblin")
    order = [_entry("hero", 18, 0), _entry("goblin", 12, 1)]
    text = format_initiative(
        order, {hero.id: hero, goblin.id: goblin}, active_id=hero.id
    )
    lines = text.splitlines()
    assert lines[0].startswith("1 ▶ Hero")
    assert lines[1].startswith("2 - Goblin")


def test_dead_creature_gets_cross_marker_and_dead_label() -> None:
    """Мёртвый — крестик в красном + перечёркнутое имя + 'DEAD' (UX-fix:
    раньше только маленький '✗' терялся среди обычных строк, игрок не
    понимал, что цель выбита из боя)."""
    hero = _make_creature("Hero")
    goblin = _make_creature("Goblin", alive=False)
    order = [_entry("hero", 18, 0), _entry("goblin", 12, 1)]
    text = format_initiative(
        order, {hero.id: hero, goblin.id: goblin}, active_id=hero.id
    )
    assert "✗" in text
    assert "DEAD" in text
    assert "[dim strike]Goblin" in text  # markup присутствует


def test_unknown_creature_shows_question_mark() -> None:
    """Если в participants нет существа из initiative-entry —
    рендерим знак вопроса, не падаем."""
    order = [_entry("ghost", 15, 0)]
    text = format_initiative(order, {})
    assert text.startswith("1 ? ghost")

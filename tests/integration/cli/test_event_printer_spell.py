"""P1-11: EventPrinter рендерит SpellCast и HealingApplied."""

from __future__ import annotations

from dnd.application.dto.engine_event import EngineEvent, HealingApplied, ItemUsed, SpellCast
from dnd.domain.values.item import ItemId
from dnd.interfaces.cli.event_printer import EventPrinter


def _capture(event: EngineEvent) -> str:
    lines: list[str] = []
    EventPrinter(sink=lines.append).dispatch_event(event)
    return "\n".join(lines)


def test_spell_cast_with_target() -> None:
    out = _capture(
        SpellCast(
            caster_id="mage",
            spell_id="fire_bolt",
            spell_name="Fire Bolt",
            slot_level=0,
            target_id="gob",
        )
    )
    assert "mage" in out and "Fire Bolt" in out and "gob" in out


def test_spell_cast_multi_targets() -> None:
    """M2: MULTI-каст логирует все цели с числом попаданий (✦×N)."""
    out = _capture(
        SpellCast(
            caster_id="mage",
            spell_id="magic_missile",
            spell_name="Magic Missile",
            slot_level=1,
            target_ids=("gobA", "gobA", "gobB"),
        )
    )
    assert "Magic Missile" in out
    assert "gobA×2" in out and "gobB" in out


def test_spell_cast_self() -> None:
    out = _capture(
        SpellCast(
            caster_id="mage",
            spell_id="shield_of_faith",
            spell_name="Shield of Faith",
            slot_level=1,
            target_id=None,
        )
    )
    assert "Shield of Faith" in out and " at " not in out


def test_healing_applied() -> None:
    out = _capture(
        HealingApplied(
            healer_id="cleric",
            target_id="hero",
            amount=7,
            hp_after=9,
            hp_max=12,
        )
    )
    assert "hero" in out and "7" in out and "9/12" in out


def test_item_used_potion() -> None:
    """U5-2: рендер ItemUsed для зелья — 🧪 «drinks» (``is_scroll=False``)."""
    out = _capture(
        ItemUsed(
            actor_id="hero",
            item_id=ItemId("healing_potion"),
            item_name="Healing Potion",
            effect="heal",
            target_id="hero",
            is_scroll=False,
        )
    )
    assert "hero" in out and "Healing Potion" in out
    assert "🧪" in out and "drinks" in out
    assert "📜" not in out


def test_item_used_scroll() -> None:
    """U5-2: рендер ItemUsed для свитка — 📜 «reads» (``is_scroll=True``)."""
    out = _capture(
        ItemUsed(
            actor_id="hero",
            item_id=ItemId("scroll_of_fireball"),
            item_name="Scroll of Fireball",
            effect="save",
            is_scroll=True,
        )
    )
    assert "hero" in out and "Scroll of Fireball" in out
    assert "📜" in out and "reads" in out
    assert "🧪" not in out


def test_item_used_renders_by_data_not_id() -> None:
    """Регрессия: ребрендинг id предмета не должен ломать иконку (рендер
    по данным ``is_scroll``, не по подстроке 'scroll' в id)."""
    # Имя «scroll» в id, но это зелье → 🧪.
    potion_like_scroll = _capture(
        ItemUsed(
            actor_id="hero",
            item_id=ItemId("hero_special_scroll_potion"),
            item_name="Special Potion",
            effect="heal",
            is_scroll=False,
        )
    )
    assert "🧪" in potion_like_scroll and "📜" not in potion_like_scroll
    # Безымянный id, но это свиток → 📜.
    scroll_no_keyword = _capture(
        ItemUsed(
            actor_id="hero",
            item_id=ItemId("ancient_paper"),
            item_name="Ancient Paper",
            effect="save",
            is_scroll=True,
        )
    )
    assert "📜" in scroll_no_keyword and "🧪" not in scroll_no_keyword

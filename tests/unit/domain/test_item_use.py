"""ItemUseSpec — обвязка доставки эффекта предмета (U2).

Domain-VO: ссылка на запись эффект-пакета в каталоге заклинаний (``effect_id``)
+ метаданные «как доставить» (экономика, расходник, является ли свитком).
``economy`` хранится строкой, чтобы domain не зависел от application — конверсию
в ``ActionEconomyCost`` делает ``UseItemAction``."""

from __future__ import annotations

import pytest

from dnd.domain.values.ids import SpellId
from dnd.domain.values.item_use import ItemUseSpec


def test_defaults_action_consumed_not_scroll() -> None:
    use = ItemUseSpec(effect_id=SpellId("cure_wounds"))
    assert use.effect_id == SpellId("cure_wounds")
    assert use.economy == "action"
    assert use.consumed is True
    assert use.is_scroll is False


def test_economy_bonus_action_allowed() -> None:
    use = ItemUseSpec(effect_id=SpellId("potion_healing"), economy="bonus_action")
    assert use.economy == "bonus_action"


def test_economy_unknown_value_rejected() -> None:
    with pytest.raises(ValueError, match="economy"):
        ItemUseSpec(effect_id=SpellId("x"), economy="reaction")


def test_is_scroll_flag_independent_of_consumed() -> None:
    use = ItemUseSpec(
        effect_id=SpellId("fireball"), economy="action", consumed=True, is_scroll=True
    )
    assert use.is_scroll is True
    assert use.consumed is True

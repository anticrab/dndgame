"""SpellPower — источник Сл/атаки/мода эффекта (U1)."""

from __future__ import annotations

from dnd.domain.values.spell_power import SpellPower


def test_scroll_dc_attack_by_level() -> None:
    assert SpellPower.scroll(0) == SpellPower(save_dc=13, attack_bonus=5, ability_mod=0)
    assert SpellPower.scroll(2) == SpellPower(save_dc=13, attack_bonus=5, ability_mod=0)
    assert SpellPower.scroll(3) == SpellPower(save_dc=15, attack_bonus=7, ability_mod=0)
    assert SpellPower.scroll(9) == SpellPower(save_dc=19, attack_bonus=11, ability_mod=0)


def test_potion_has_zero_mod() -> None:
    assert SpellPower.potion() == SpellPower(save_dc=0, attack_bonus=0, ability_mod=0)

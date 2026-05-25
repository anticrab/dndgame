"""spell_ability — превращает :class:`Spell` в :class:`Ability` для action-bar.

Заклинания из ``Creature.known_spells`` показываются в TUI отдельной полосой с
hotkey'ями ``1..9``. Ability несёт ``intent_factory`` → :class:`CastSpellIntent`.
``id`` префиксуется :data:`SPELL_ABILITY_PREFIX`, чтобы BattleScreen отличал
заклинания от базовых умений и выбирал правильный набор целей (враги для урона,
союзники для heal/buff).
"""
from __future__ import annotations

from dnd.application.abilities.ability import Ability, AbilityId
from dnd.application.dto.action import ActionEconomyCost
from dnd.application.dto.player_intent import CastSpellIntent, PlayerIntent
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.spell import Spell, TargetKind

SPELL_ABILITY_PREFIX = "spell:"


def spell_ability_id(spell: Spell) -> AbilityId:
    return AbilityId(f"{SPELL_ABILITY_PREFIX}{spell.id}")


def is_spell_ability(ability: Ability) -> bool:
    return str(ability.id).startswith(SPELL_ABILITY_PREFIX)


def spell_ability(spell: Spell, hotkey: str) -> Ability:
    """Построить Ability из заклинания с заданным hotkey'ем (обычно ``"1".."9"``)."""

    def _factory(target_id: CreatureId | None = None) -> PlayerIntent:
        return CastSpellIntent(spell_id=spell.id, target_id=target_id)

    return Ability(
        id=spell_ability_id(spell),
        name=spell.name,
        icon=hotkey,
        default_hotkey=hotkey,
        economy_cost=ActionEconomyCost.ACTION,
        requires_target=spell.targeting.kind is TargetKind.SINGLE,
        requires_path=False,
        intent_factory=_factory,
    )


__all__ = [
    "SPELL_ABILITY_PREFIX",
    "is_spell_ability",
    "spell_ability",
    "spell_ability_id",
]

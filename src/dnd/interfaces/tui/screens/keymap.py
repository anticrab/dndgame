"""build_keymap — собирает ``{hotkey: Ability}`` для конкретного актора.

Алгоритм: сначала раскладываем default hotkey'и из ``Ability.default_hotkey``,
затем накатываем override'ы из ``Creature.keybindings``. При override
старый default hotkey этого умения вычищается, иначе одна и та же
ability оказалась бы привязана к двум клавишам (играющему это
непонятно — какая клавиша «настоящая»).
"""
from __future__ import annotations

from dnd.application.abilities.ability import Ability
from dnd.application.abilities.registry import AbilityRegistry
from dnd.domain.entities.creature import Creature


def build_keymap(actor: Creature, registry: AbilityRegistry) -> dict[str, Ability]:
    keymap: dict[str, Ability] = {}
    for aid in actor.ability_ids:
        ab = registry.get(aid)
        keymap[ab.default_hotkey] = ab
    for key, aid in actor.keybindings.items():
        ab = registry.get(aid)
        old = ab.default_hotkey
        if old in keymap and keymap[old] is ab:
            del keymap[old]
        keymap[key] = ab
    return keymap


__all__ = ["build_keymap"]

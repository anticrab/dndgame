"""E2E smoke этапа T1 — PC-волшебник из сценария `mage_skirmish`.

Проверяем сквозную сборку волшебника из контента:

1. ``mage_apprentice`` собран как ``wizard`` 1-го уровня;
2. из класса подтянулись профициентные спасброски (INT, WIS);
3. ячейки заклинаний — по таблице Волшебника L1 (две ячейки 1-го круга);
4. боевой цикл сходится: маг кастует Magic Missile (авто-попадание)
   и снимает гоблина, бой заканчивается победой PARTY.

Это смок-тест сборки, а не доказательство правил каста — конкретика
покрыта юнит-тестами заклинаний.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dnd.application.dto.action import Allowed
from dnd.application.dto.engine_event import EncounterEnded, EngineEvent
from dnd.application.engine.actions.cast_spell import CastSpellAction, CastSpellParams
from dnd.application.engine.encounter import Encounter
from dnd.application.engine.scenario_builder import build_encounter_from_scenario
from dnd.composition import build_default_runtime_services
from dnd.domain.values.ability import Ability
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import SpellId
from dnd.infrastructure.content.yaml_class_repository import YamlClassRepository
from dnd.infrastructure.content.yaml_repository import YamlContentRepository
from dnd.infrastructure.content.yaml_spell_repository import YamlSpellRepository

_CONTENT = Path("data/content")
_MAX_TURNS = 30


def _build_mage_scene() -> Encounter:
    repo = YamlContentRepository(_CONTENT)
    scenario = repo.scenario_by_id("mage_skirmish")
    services = build_default_runtime_services()
    class_repo = YamlClassRepository(_CONTENT / "classes.yaml")
    return build_encounter_from_scenario(
        scenario, content=repo, services=services, class_repository=class_repo
    )


@pytest.mark.e2e
def test_mage_built_as_wizard_with_save_profs_and_slots() -> None:
    enc = _build_mage_scene()
    mage = next(
        enc.participants[cid] for cid, f in enc.factions.items() if f is Faction.PARTY
    )
    assert mage.character_class == "wizard"
    assert mage.level == 1
    assert mage.saving_throw_proficiencies == frozenset({Ability.INT, Ability.WIS})
    assert mage.spell_slots == {1: 2}, "Волшебник L1 — две ячейки 1-го круга"
    assert mage.spellcasting_ability is Ability.INT


@pytest.mark.e2e
def test_mage_magic_missile_resolves_combat() -> None:
    """Маг кастует Magic Missile (3 авто-дротика в гоблина) — бой сходится.

    Magic Missile не бросает атаку (auto), 3×(1d4+1) ≥ 6 урона за каст,
    у мага 2 ячейки — гоблина (7 HP) снимет гарантированно даже на реальном
    RNG, поэтому смок детерминированно сходится.
    """
    enc = _build_mage_scene()
    spell_repo = YamlSpellRepository(_CONTENT / "spells.yaml")

    captured: list[EngineEvent] = []
    enc.event_bus.subscribe(EngineEvent, captured.append)
    enc.start()

    goblin_ids = [cid for cid, f in enc.factions.items() if f is Faction.MONSTERS]
    action = CastSpellAction(spell_repository=spell_repo)

    turns = 0
    while not enc.is_concluded and turns < _MAX_TURNS:
        turns += 1
        actor_id = enc.current_actor_id
        ctx = enc.start_turn()
        actor = enc.participants[actor_id]
        if not actor.is_alive or actor.is_at_zero_hp:
            enc.end_turn()
            continue

        if enc.factions[actor_id] is Faction.PARTY and actor.spell_slots.get(1, 0) > 0:
            target = next(
                (gid for gid in goblin_ids if enc.participants[gid].is_alive
                 and not enc.participants[gid].is_at_zero_hp),
                None,
            )
            if target is not None:
                # 3 дротика в одну цель — MULTI с allow_repeat_target.
                params = CastSpellParams(
                    spell_id=SpellId("magic_missile"),
                    target_ids=(target, target, target),
                )
                if isinstance(action.can_perform_against(actor, params, ctx), Allowed):
                    action.execute(actor, params, ctx)
        enc.end_turn()

    assert enc.is_concluded is True, f"бой не сошёлся за {_MAX_TURNS} ходов"
    ended = next(e for e in captured if isinstance(e, EncounterEnded))
    assert ended.winners is Faction.PARTY

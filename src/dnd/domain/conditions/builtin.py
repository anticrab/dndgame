"""Восемь базовых состояний MVP (Книга 2024, стр. 367, Глоссарий состояний).

Содержательно: каждое состояние — простой dataclass, реализующий
``Condition`` Protocol. Поведение «как влияет на броски» закодировано
в ``provides_modifiers`` — это интегрируется с :class:`ModifierApplier`.

Реализованы:

* ``Incapacitated`` — без действий/реакций/бонусных действий
  (это смысл — действия запрещены; модификаторы броска отдельно).
* ``Prone`` — лежащий ничком.
* ``Poisoned`` — отравлен.
* ``Frightened`` — испуган.
* ``Stunned`` — оглушён (implies Incapacitated).
* ``Paralyzed`` — парализован (implies Incapacitated).
* ``Unconscious`` — бессознательный (implies Incapacitated + Prone).
* ``Invisible`` — невидимый.

Self-эффекты (помехи на свои броски: Poisoned/Frightened/Prone) — через
``provides_modifiers`` (T3: подмешиваются на момент броска
``ConditionService.collect_modifiers``).

Cross-creature правила (атаки **по** носителю, авто-провал спасбросков,
авто-крит в упор) выражаются декларативными полями состояния (T3):
``grants_advantage_to_attackers``, ``melee_advantage_ranged_disadvantage``
(Prone), ``auto_fail_saves`` — их читают ``attack.py`` / ``saving_throw`` через
``ConditionService`` (``incoming_attack_adjustment`` / ``auto_fails_save``).
Невидимость как источник cross-creature adv/disadv пока не реализована (задел).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dnd.domain.values.ability import Ability
from dnd.domain.values.ids import ConditionId, CreatureId
from dnd.domain.values.modifiers import (
    DisadvantageEffect,
    Modifier,
    ModifierSourceKind,
    ModifierTargetKind,
)

# Канонические ConditionId для базовых состояний.
INCAPACITATED = ConditionId("incapacitated")
PRONE = ConditionId("prone")
POISONED = ConditionId("poisoned")
FRIGHTENED = ConditionId("frightened")
STUNNED = ConditionId("stunned")
PARALYZED = ConditionId("paralyzed")
UNCONSCIOUS = ConditionId("unconscious")
INVISIBLE = ConditionId("invisible")


def _self_disadvantage(
    owner_id: CreatureId,
    condition_id: ConditionId,
    *targets: ModifierTargetKind,
) -> tuple[Modifier, ...]:
    """Удобная фабрика: «существо имеет помеху на броски такого-то типа»."""
    return tuple(
        Modifier(
            source_id=f"condition:{condition_id}",
            source_kind=ModifierSourceKind.CONDITION,
            target_kind=target,
            effect=DisadvantageEffect(),
            owner_id=owner_id,
            stack_key=f"condition:{condition_id}:{target.value}",
        )
        for target in targets
    )


@dataclass(frozen=True, slots=True)
class IncapacitatedCondition:
    """Книга 2024 стр. 367, «Недееспособный».

    Не может совершать действий, бонусных действий и реакций.
    Не накладывает прямых модификаторов на броски — ограничение
    действий обрабатывается в Encounter (TurnBudget).
    """

    id: ConditionId = INCAPACITATED
    implies: frozenset[ConditionId] = field(default_factory=frozenset)
    grants_advantage_to_attackers: bool = False
    melee_advantage_ranged_disadvantage: bool = False
    auto_fail_saves: frozenset[Ability] = frozenset()

    def provides_modifiers(self, owner_id: CreatureId) -> tuple[Modifier, ...]:
        return ()


@dataclass(frozen=True, slots=True)
class ProneCondition:
    """Книга 2024 стр. 367, «Лежащий ничком».

    * Свои броски атак — с **помехой**.
    * Атаки по нему в 5 фут — с преимуществом; >5 фут — с помехой
      (это cross-creature, реализуется в attack_roll).
    * Перемещение — ползком (cost ×2).
    """

    id: ConditionId = PRONE
    implies: frozenset[ConditionId] = field(default_factory=frozenset)
    grants_advantage_to_attackers: bool = False
    # Prone: атака в упор (melee ≤5) — с преимуществом, иначе — с помехой.
    melee_advantage_ranged_disadvantage: bool = True
    auto_fail_saves: frozenset[Ability] = frozenset()

    def provides_modifiers(self, owner_id: CreatureId) -> tuple[Modifier, ...]:
        return _self_disadvantage(owner_id, self.id, ModifierTargetKind.ATTACK_ROLL)


@dataclass(frozen=True, slots=True)
class PoisonedCondition:
    """Книга 2024 стр. 367, «Отравленный».

    Помеха на броски атак и проверки характеристик.
    """

    id: ConditionId = POISONED
    implies: frozenset[ConditionId] = field(default_factory=frozenset)
    grants_advantage_to_attackers: bool = False
    melee_advantage_ranged_disadvantage: bool = False
    auto_fail_saves: frozenset[Ability] = frozenset()

    def provides_modifiers(self, owner_id: CreatureId) -> tuple[Modifier, ...]:
        return _self_disadvantage(
            owner_id,
            self.id,
            ModifierTargetKind.ATTACK_ROLL,
            ModifierTargetKind.ABILITY_CHECK,
        )


@dataclass(frozen=True, slots=True)
class FrightenedCondition:
    """Книга 2024 стр. 367, «Испуганный».

    * Помеха на броски атак и проверки характеристик, пока источник
      страха в поле зрения.
    * Не может **по своей воле** приближаться к источнику страха.

    Условие «источник в поле зрения» — это ``ModifierCondition``
    (Specification), MVP его не выражает; считаем активным.
    Запрет на сближение — обрабатывается в Action.can_perform для Move.
    """

    id: ConditionId = FRIGHTENED
    implies: frozenset[ConditionId] = field(default_factory=frozenset)
    grants_advantage_to_attackers: bool = False
    melee_advantage_ranged_disadvantage: bool = False
    auto_fail_saves: frozenset[Ability] = frozenset()

    def provides_modifiers(self, owner_id: CreatureId) -> tuple[Modifier, ...]:
        return _self_disadvantage(
            owner_id,
            self.id,
            ModifierTargetKind.ATTACK_ROLL,
            ModifierTargetKind.ABILITY_CHECK,
        )


@dataclass(frozen=True, slots=True)
class StunnedCondition:
    """Книга 2024 стр. 367, «Ошеломлённый».

    Implies Incapacitated. Авто-провал спасбросков Силы и Ловкости
    (T3: через ``auto_fail_saves`` → ``ConditionService.auto_fails_save``).
    Атаки по ошеломлённому — с преимуществом (``grants_advantage_to_attackers``).
    """

    id: ConditionId = STUNNED
    implies: frozenset[ConditionId] = field(default_factory=lambda: frozenset({INCAPACITATED}))
    grants_advantage_to_attackers: bool = True
    melee_advantage_ranged_disadvantage: bool = False
    # T3: авто-провал спасбросков Силы и Ловкости (PHB-2024 стр. 367).
    auto_fail_saves: frozenset[Ability] = frozenset({Ability.STR, Ability.DEX})

    def provides_modifiers(self, owner_id: CreatureId) -> tuple[Modifier, ...]:
        # T3: авто-провал STR/DEX-спасбросков теперь через auto_fail_saves
        # (ConditionService.auto_fails_save). provides_modifiers не нужен —
        # SAVING_THROW-помеха была приближением до появления авто-провала.
        return ()


@dataclass(frozen=True, slots=True)
class ParalyzedCondition:
    """Книга 2024 стр. 367, «Парализованный».

    Implies Incapacitated. Авто-провал спасбросков Силы и Ловкости (T3:
    ``auto_fail_saves``). Атаки по парализованному — с преимуществом; в упор
    ≤5 фт melee — авто-крит (T3: ``attack.py``).
    """

    id: ConditionId = PARALYZED
    implies: frozenset[ConditionId] = field(default_factory=lambda: frozenset({INCAPACITATED}))
    # T3: атаки по парализованному — с преимуществом; в упор ≤5 melee — крит
    # (авто-крит в attack.py). Авто-провал спасбросков Силы и Ловкости.
    grants_advantage_to_attackers: bool = True
    melee_advantage_ranged_disadvantage: bool = False
    auto_fail_saves: frozenset[Ability] = frozenset({Ability.STR, Ability.DEX})

    def provides_modifiers(self, owner_id: CreatureId) -> tuple[Modifier, ...]:
        # T3: STR/DEX-спасброски авто-проваливаются через auto_fail_saves;
        # blanket-помеха на ВСЕ спасброски была неточной (CON/WIS не страдают).
        return ()


@dataclass(frozen=True, slots=True)
class UnconsciousCondition:
    """Книга 2024 стр. 367, «Бессознательный».

    Implies Incapacitated + Prone. Автопровал STR/DEX-спасбросков;
    атаки в 5 фут — крит. См. комментарий к Stunned/Paralyzed.

    Это **Condition**, не ``Creature.is_at_zero_hp`` (тот — про факт HP=0).
    Бессознательное состояние накладывается **на** падение в 0 HP
    (Character) или явно эффектом (заклинание Sleep).
    """

    id: ConditionId = UNCONSCIOUS
    implies: frozenset[ConditionId] = field(
        default_factory=lambda: frozenset({INCAPACITATED, PRONE})
    )
    # T3: атаки по бессознательному — с преимуществом; в упор — авто-крит.
    grants_advantage_to_attackers: bool = True
    melee_advantage_ranged_disadvantage: bool = False
    auto_fail_saves: frozenset[Ability] = frozenset({Ability.STR, Ability.DEX})

    def provides_modifiers(self, owner_id: CreatureId) -> tuple[Modifier, ...]:
        # T3: STR/DEX-спасброски авто-проваливаются через auto_fail_saves.
        return ()


@dataclass(frozen=True, slots=True)
class InvisibleCondition:
    """Книга 2024 стр. 367, «Невидимый».

    * Атаки **по** невидимому — с помехой (cross-creature).
    * Атаки **от** невидимого — с преимуществом (cross-creature).
    * При определении surprise — считается невидимым.

    Сам по себе self-эффект (на свои броски) Invisible не даёт.
    Поэтому `provides_modifiers` пуст — взаимодействия будут через
    attack_roll, когда появятся.
    """

    id: ConditionId = INVISIBLE
    implies: frozenset[ConditionId] = field(default_factory=frozenset)
    grants_advantage_to_attackers: bool = False
    melee_advantage_ranged_disadvantage: bool = False
    auto_fail_saves: frozenset[Ability] = frozenset()

    def provides_modifiers(self, owner_id: CreatureId) -> tuple[Modifier, ...]:
        return ()


# -- регистрация ----------------------------------------------------------


def register_default_conditions(registry: object) -> None:
    """Зарегистрировать 8 базовых MVP-состояний в ``ConditionRegistry``.

    Сигнатура с ``object`` — чтобы избежать циклического импорта
    ``registry → builtin → registry``. Тип проверяется ``hasattr``.
    """
    if not hasattr(registry, "register"):
        raise TypeError(
            f"register_default_conditions expects ConditionRegistry, got {type(registry).__name__}"
        )
    registry.register(IncapacitatedCondition())
    registry.register(ProneCondition())
    registry.register(PoisonedCondition())
    registry.register(FrightenedCondition())
    registry.register(StunnedCondition())
    registry.register(ParalyzedCondition())
    registry.register(UnconsciousCondition())
    registry.register(InvisibleCondition())


__all__ = [
    "FRIGHTENED",
    "INCAPACITATED",
    "INVISIBLE",
    "PARALYZED",
    "POISONED",
    "PRONE",
    "STUNNED",
    "UNCONSCIOUS",
    "FrightenedCondition",
    "IncapacitatedCondition",
    "InvisibleCondition",
    "ParalyzedCondition",
    "PoisonedCondition",
    "ProneCondition",
    "StunnedCondition",
    "UnconsciousCondition",
    "register_default_conditions",
]

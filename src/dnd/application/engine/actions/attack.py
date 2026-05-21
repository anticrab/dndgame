"""AttackAction — атака оружием (melee и ranged).

См. ``docs/ACTIONS.md`` §2 и «Книгу Игрока 2024» стр. 25.

Что делает:

* ``can_perform`` — проверяет экономику, состояния-блокеры (Incapacitated /
  Stunned / Paralyzed / Unconscious), наличие цели в боя, LoS, cover != TOTAL,
  дальность (melee: ≤ reach; ranged: ≤ long_range);
* ``execute`` — собирает модификаторы атаки, бросает d20, считает
  effective_AC цели с учётом cover, фиксирует crit/miss, бросает урон
  (с удвоением кубов на крите), применяет ``Creature.take_damage`` и
  публикует ``AttackRolled`` / ``DamageDealt`` / ``AttackResolved``.

Что **не** делает:

* не управляет concentration save цели (только сигналит через
  ``concentration_save_dc`` в ``AttackResolved`` — отдельный путь);
* не моделирует «ranged-в-упор → disadvantage» (PHB-2024 стр. 25,
  «Ranged Attacks Against Close Targets»). Помечено TODO;
* не выбирает оружие/проверяет proficiency — параметры броска (бонус
  к попаданию, формула урона, тип, дальности) берёт из ``AttackParams``.
  Связь с инвентарём — этап персонажа.

Параметры атаки приходят готовыми: вызывающий уровень (``Character``
с экипированным оружием) собирает их.
"""

from __future__ import annotations

from dataclasses import replace
from enum import StrEnum
from typing import ClassVar, Final

from pydantic import Field

from dnd.application.dto.action import (
    ActionAvailability,
    ActionEconomyCost,
    ActionOutcome,
    ActionParams,
    Allowed,
    Forbidden,
    ForbiddenReason,
)
from dnd.application.dto.engine_event import (
    AttackResolved,
    AttackRolled,
    DamageDealt,
)
from dnd.application.dto.ids import ActionId, CreatureId
from dnd.application.dto.modifiers import ModifierTargetKind
from dnd.application.dto.rolls import RollContext, RollPurpose
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.conditions.builtin import (
    INCAPACITATED,
    PARALYZED,
    STUNNED,
    UNCONSCIOUS,
)
from dnd.domain.entities.creature import Creature
from dnd.domain.values.damage import DamageInstance, DamageType
from dnd.domain.values.dice import DiceExpr
from dnd.domain.values.terrain import CoverLevel

# Состояния, при которых нельзя выполнять действия с атакой.
# PHB-2024 стр. 367: Incapacitated → нет actions, reactions, bonus actions.
# Stunned / Paralyzed / Unconscious → implies Incapacitated.
_BLOCKING_CONDITIONS: Final = frozenset(
    {INCAPACITATED, STUNNED, PARALYZED, UNCONSCIOUS}
)


class AttackKind(StrEnum):
    MELEE = "melee"
    RANGED = "ranged"


class AttackParams(ActionParams):
    """Параметры одной атаки оружием.

    ``range_ft`` для MELEE — это reach (обычно 5; для глефы/копья 10).
    Для RANGED — нормальная дальность; за её пределами до
    ``long_range_ft`` действует disadvantage; дальше — нельзя.

    ``long_range_ft`` для MELEE игнорируется (должен быть 0). Для
    RANGED 0 означает «нет длинной дистанции, диапазон ровно range_ft».

    **Разделение ответственности с ModifierApplier** (аудит 08 AT-A004):

    * ``attack_bonus`` — **статический** бонус оружия: proficiency_bonus
      + ability_mod (STR/DEX) + ranks плюс ``+N`` зачарования.
      Не включает ситуативные модификаторы.
    * ``damage_expr`` — **базовый** урон оружия (``"1d8+3"`` для long sword
      с STR=16), включая ability_mod. Без ситуативных бонусов.
    * Ситуативные модификаторы (Bless, Bardic Inspiration, conditions
      на actor'е и т.п.) собираются ``ModifierApplier`` в ``execute`` по
      ``ATTACK_ROLL`` / ``DAMAGE_ROLL`` и комбинируются с этими полями.
    """

    target_id: CreatureId
    kind: AttackKind
    attack_bonus: int = Field(ge=-20, le=30)
    damage_expr: str  # парсится через DiceExpr.parse (e.g. "1d8+3")
    damage_type: DamageType
    range_ft: int = Field(ge=5)
    long_range_ft: int = Field(default=0, ge=0)


class AttackAction:
    """Стандартная атака оружием.

    Один экземпляр на всё приложение — действие не имеет состояния.
    Метаданные хранятся в ``ClassVar``: id, name_key, economy_cost.
    """

    id_value: ClassVar[ActionId] = ActionId("attack")
    name_key_value: ClassVar[str] = "action.attack"
    economy_cost_value: ClassVar[ActionEconomyCost] = ActionEconomyCost.ACTION

    @property
    def id(self) -> ActionId:
        return self.id_value

    @property
    def name_key(self) -> str:
        return self.name_key_value

    @property
    def economy_cost(self) -> ActionEconomyCost:
        return self.economy_cost_value

    # --- can_perform ---------------------------------------------------

    def _check_economy(
        self, actor: Creature, ctx: TurnContext
    ) -> ActionAvailability:
        """Проверка бюджета. Подклассы (``OpportunityAttack``) переопределяют
        её для reaction-режима, где «бюджет» — это
        ``actor.reaction_used`` per-round, а не ``ctx.reaction_used``."""
        if not ctx.can_spend(self.economy_cost_value):
            return Forbidden(reason=ForbiddenReason.NO_ECONOMY_LEFT)
        return Allowed()

    def _spend_economy(self, actor: Creature, ctx: TurnContext) -> None:
        """Списать бюджет атаки. Парная переопределяемая ручка к
        ``_check_economy``."""
        ctx.spend(self.economy_cost_value)

    def can_perform(
        self, actor: Creature, ctx: TurnContext
    ) -> ActionAvailability:
        # Этот метод НЕ принимает params (мы ещё не знаем, что игрок выберет);
        # глобальные блокеры — экономика и состояния. Конкретные проверки
        # «можно ли атаковать ИМЕННО эту цель» — в ``can_perform_against``,
        # которое UI вызывает после выбора цели.
        budget = self._check_economy(actor, ctx)
        if isinstance(budget, Forbidden):
            return budget
        for cond in _BLOCKING_CONDITIONS:
            if actor.has_condition(cond):
                return Forbidden(
                    reason=ForbiddenReason.CONDITION_BLOCKS_ACTION,
                    details=cond,
                )
        return Allowed()

    def can_perform_against(
        self,
        actor: Creature,
        params: AttackParams,
        ctx: TurnContext,
    ) -> ActionAvailability:
        """Проверка с учётом конкретной цели. UI/AI вызывает после
        ``can_perform`` и до ``execute``.

        Все правила, требующие знания цели: распознать цель в боя,
        LoS, cover, дальность.
        """
        base = self.can_perform(actor, ctx)
        if isinstance(base, Forbidden):
            return base

        target = ctx.participants.get(params.target_id)
        if target is None:
            return Forbidden(reason=ForbiddenReason.NO_VALID_TARGETS)

        attacker_pos = ctx.battlefield.position_of(actor.id)
        target_pos = ctx.battlefield.position_of(target.id)

        if not ctx.battlefield.line_of_sight(attacker_pos, target_pos):
            return Forbidden(reason=ForbiddenReason.NO_LINE_OF_SIGHT)

        cover = ctx.battlefield.cover_against(attacker_pos, target_pos)
        if cover is CoverLevel.TOTAL:
            return Forbidden(reason=ForbiddenReason.TARGET_HAS_TOTAL_COVER)

        distance_ft = attacker_pos.distance_to_feet(target_pos)
        max_range = (
            params.long_range_ft
            if (params.kind is AttackKind.RANGED and params.long_range_ft > 0)
            else params.range_ft
        )
        if distance_ft > max_range:
            return Forbidden(reason=ForbiddenReason.OUT_OF_RANGE)

        return Allowed()

    # --- execute -------------------------------------------------------

    def execute(
        self,
        actor: Creature,
        params: ActionParams,
        ctx: TurnContext,
    ) -> ActionOutcome:
        """Выполнить атаку. Контракт ACTIONS.md §6: вызывающий обязан
        проверить ``can_perform`` и ``can_perform_against`` ДО ``execute``.

        Этот метод **не дублирует** валидацию (см. §6 «никаких двойных
        вычислений»). Если контракт нарушен:

        * нет цели в ``participants`` → ``RuntimeError`` («can_perform_against
          не был вызван»);
        * цель не на карте → ``KeyError`` из ``Battlefield.position_of``;
        * LoS отсутствует / total cover — атака пойдёт «как есть» и
          скорее всего промахнётся (effective_ac будет обычным, cover
          не добавит, но запретов не будет).

        Это сознательно — Action не страхует UI/AI.
        """
        if not isinstance(params, AttackParams):
            raise TypeError(
                f"AttackAction expects AttackParams, got {type(params).__name__}"
            )

        target = ctx.participants.get(params.target_id)
        if target is None:
            raise RuntimeError(
                f"contract violation: target {params.target_id!r} not in "
                f"participants; AttackAction.can_perform_against must be "
                f"called before execute"
            )
        attacker_pos = ctx.battlefield.position_of(actor.id)
        target_pos = ctx.battlefield.position_of(target.id)
        cover = ctx.battlefield.cover_against(attacker_pos, target_pos)
        distance_ft = attacker_pos.distance_to_feet(target_pos)

        self._spend_economy(actor, ctx)

        # 1) Собрать модификаторы атаки.
        atk_mods = ctx.modifier_applier.collect(
            owner_id=actor.id,
            target_kind=ModifierTargetKind.ATTACK_ROLL,
        )
        atk_adj = ctx.modifier_applier.to_roll_adjustments(atk_mods)

        # Ranged за нормальной дальностью → disadvantage (PHB-2024 стр. 25).
        long_range_penalty = (
            params.kind is AttackKind.RANGED
            and params.long_range_ft > 0
            and distance_ft > params.range_ft
        )

        # Цель в Dodge-стойке → атаки по ней с помехой (PHB-2024 стр. 22).
        # Книжная оговорка «если цель видит атакующего» — на MVP считаем
        # выполненной (LoS уже проверен и симметричен).
        # "dodging" — значение CombatStance.DODGING; не импортируем
        # enum здесь, чтобы action attack не зависел от модуля stances.
        dodge_penalty = "dodging" in target.combat_stances

        # Help-бонус: союзник назначил advantage на эту атаку
        # (PHB-2024 стр. 22). One-shot — сбрасывается после броска.
        help_bonus = actor.helped_against == target.id
        if help_bonus:
            actor.helped_against = None

        # 2) Бросок атаки.
        total_atk_bonus = params.attack_bonus + atk_adj.numeric_bonus
        attack_expr = DiceExpr.parse(f"d20{total_atk_bonus:+d}")
        attack_ctx = RollContext(
            purpose=RollPurpose.ATTACK,
            actor_id=actor.id,
            target_id=target.id,
            advantage=atk_adj.advantage or help_bonus,
            disadvantage=(
                atk_adj.disadvantage or long_range_penalty or dodge_penalty
            ),
            extra_dice=atk_adj.extra_dice,
        )
        attack_roll = ctx.dice_roller.roll(attack_expr, attack_ctx)

        # 3) Эффективный КД цели: armor_class + cover_bonus + AC-модификаторы.
        ac_mods = ctx.modifier_applier.collect(
            owner_id=target.id,
            target_kind=ModifierTargetKind.ARMOR_CLASS,
        )
        ac_adj = ctx.modifier_applier.to_roll_adjustments(ac_mods)
        effective_ac = target.armor_class + cover.ac_bonus + ac_adj.numeric_bonus

        # 4) Hit/Crit. Книга стр. 25: natural 20 — критическое попадание
        # (всегда попадает); natural 1 — критический промах (всегда мимо).
        is_crit = attack_roll.is_natural_20()
        is_crit_miss = attack_roll.is_natural_1()
        if is_crit:
            hit = True
        elif is_crit_miss:
            hit = False
        else:
            hit = attack_roll.total >= effective_ac

        ctx.event_bus.publish(
            AttackRolled(
                attacker_id=actor.id,
                target_id=target.id,
                attack_roll_id=attack_roll.roll_id,
                effective_ac=effective_ac,
                is_critical_hit=is_crit,
                is_critical_miss=is_crit_miss,
                hit=hit,
            )
        )

        published: list[str] = ["attack.rolled"]
        downed = False
        concentration_dc: int | None = None

        if hit:
            # 5) Урон: на крите DiceRoller сам удваивает основные и
            # extra dice (см. ADR/комментарий в ComputerDiceRoller).
            dmg_mods = ctx.modifier_applier.collect(
                owner_id=actor.id,
                target_kind=ModifierTargetKind.DAMAGE_ROLL,
            )
            dmg_adj = ctx.modifier_applier.to_roll_adjustments(dmg_mods)
            base_expr = DiceExpr.parse(params.damage_expr)
            # Сборка через dataclasses.replace, не строковая конкатенация —
            # DiceExpr.parse не поддерживает «1d8+3+2» (одно опциональное
            # `[+-]\d+` в паттерне). Аудит 08 AT-R001.
            full_expr = (
                base_expr
                if dmg_adj.numeric_bonus == 0
                else replace(base_expr, modifier=base_expr.modifier + dmg_adj.numeric_bonus)
            )
            dmg_ctx = RollContext(
                purpose=RollPurpose.DAMAGE,
                actor_id=actor.id,
                target_id=target.id,
                crit=is_crit,
                extra_dice=dmg_adj.extra_dice,
            )
            damage_roll = ctx.dice_roller.roll(full_expr, dmg_ctx)

            # 6) Применить урон.
            damage_result = target.take_damage(
                DamageInstance(amount=damage_roll.total, type_=params.damage_type),
                is_critical=is_crit,
            )

            ctx.event_bus.publish(
                DamageDealt(
                    attacker_id=actor.id,
                    target_id=target.id,
                    damage_roll_id=damage_roll.roll_id,
                    damage_type=params.damage_type,
                    raw_amount=damage_roll.total,
                    final_amount=damage_result.final_amount,
                    is_critical=is_crit,
                )
            )
            published.append("damage.dealt")
            downed = damage_result.was_lethal
            concentration_dc = damage_result.concentration_save_dc

        ctx.event_bus.publish(
            AttackResolved(
                attacker_id=actor.id,
                target_id=target.id,
                attack_roll_id=attack_roll.roll_id,
                hit=hit,
                is_critical=is_crit,
                downed=downed,
                concentration_save_dc=concentration_dc,
            )
        )
        published.append("attack.resolved")

        return ActionOutcome(
            success=True,
            consumed=self.economy_cost_value,
            events_published=tuple(published),
            notes=(
                f"hit={hit} crit={is_crit} target={target.id} "
                f"effective_ac={effective_ac}"
            ),
        )


__all__ = ["AttackAction", "AttackKind", "AttackParams"]

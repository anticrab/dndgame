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
from dnd.application.dto.rolls import RollContext, RollPurpose
from dnd.application.engine.features.fighting_styles import (
    fighting_style_attack_bonus,
    fighting_style_damage_bonus,
)
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.conditions.builtin import (
    INCAPACITATED,
    PARALYZED,
    STUNNED,
    UNCONSCIOUS,
)
from dnd.domain.entities.creature import Creature
from dnd.domain.values.attack_kind import AttackKind
from dnd.domain.values.damage import DamageInstance, DamageType
from dnd.domain.values.dice import DiceExpr
from dnd.domain.values.ids import ActionId, CreatureId, FeatureId
from dnd.domain.values.modifiers import ModifierTargetKind
from dnd.domain.values.terrain import CoverLevel

# Состояния, при которых нельзя выполнять действия с атакой.
# PHB-2024 стр. 367: Incapacitated → нет actions, reactions, bonus actions.
# Stunned / Paralyzed / Unconscious → implies Incapacitated.
_BLOCKING_CONDITIONS: Final = frozenset(
    {INCAPACITATED, STUNNED, PARALYZED, UNCONSCIOUS}
)

# Состояния, при которых Dodge-стойка цели перестаёт давать
# disadvantage атакующему (PHB-2024 стр. 22: «benefit ends if you are
# Incapacitated or your Speed drops to 0»). Аудит 10 ST-R001.
_DODGE_SUPPRESSING_CONDITIONS: Final = frozenset(
    {INCAPACITATED, STUNNED, PARALYZED, UNCONSCIOUS}
)


def _dodge_suppressed(target: Creature) -> bool:
    """True, если у цели Dodge не действует (PHB-2024 стр. 22)."""
    return any(target.has_condition(c) for c in _DODGE_SUPPRESSING_CONDITIONS)


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

        # PHB-2024 стр. 18-20: атака идёт на «существо, которое ты можешь
        # видеть» — сам ты не «другое существо».
        if target.id == actor.id:
            return Forbidden(reason=ForbiddenReason.SELF_TARGET)

        # Цель на 0 HP. «Добивание» лежачего спасаемого (PC при смерти)
        # РАЗРЕШЕНО: удар в упор = авто-крит = 2 провала спасброска
        # (PHB-2024 стр. 27, см. _resolve ниже). Это закрывает «ничью-
        # зависание» (этап D): соло-PC без сознания иначе лежал бы стабильным,
        # а бой висел бы до round-limit. Прочие 0-HP цели (мёртвые NPC) бить
        # нельзя — для них смерть окончательна.
        if not target.is_alive or target.is_at_zero_hp:
            finishable = (
                target.uses_death_saves
                and target.death_saves is not None
                and not target.death_saves.is_dead
            )
            if not finishable:
                return Forbidden(reason=ForbiddenReason.TARGET_DOWN)

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
        # T3: self-помехи от состояний атакующего (Poisoned/Frightened/Prone) —
        # раньше provides_modifiers были осиротевшими; теперь подмешиваем.
        atk_mods = atk_mods + ctx.condition_service.collect_modifiers(
            actor, ModifierTargetKind.ATTACK_ROLL
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
        #
        # PHB-2024 стр. 22: «benefit ends if you are Incapacitated or
        # your Speed drops to 0». Stunned / Paralyzed / Unconscious все
        # impply Incapacitated; Paralyzed/Stunned/Unconscious дают также
        # speed=0. Поэтому если у цели любое из этих условий — Dodge
        # больше не действует. Аудит 10 ST-R001.
        dodge_penalty = (
            "dodging" in target.combat_stances
            and not _dodge_suppressed(target)
        )

        # Help-бонус: союзник назначил advantage на эту атаку
        # (PHB-2024 стр. 22). One-shot — сбрасывается после броска.
        #
        # Книжная оговорка (аудит 11 HS-R001): «benefit ends if the
        # target is no longer within 5 feet of you [helper] when the
        # attack is made». Проверяем позицию helper'а сейчас, а не на
        # момент Help-action.
        help_bonus = False
        if actor.helped_against == target.id:
            helper = (
                ctx.participants.get(actor.helped_by)
                if actor.helped_by is not None
                else None
            )
            if helper is not None and ctx.battlefield.has_creature(helper.id):
                helper_pos = ctx.battlefield.position_of(helper.id)
                if helper_pos.distance_to_feet(target_pos) <= 5:
                    help_bonus = True
            # One-shot: помощь «израсходована», даже если её отменил
            # уход helper'а — это согласуется с RAW (бонус «теряется»,
            # а не «копится»).
            actor.helped_against = None
            actor.helped_by = None

        # T3: cross-creature — преимущество/помеха от состояний ЦЕЛИ
        # (Paralyzed/Unconscious/Stunned → advantage; Prone → advantage в упор
        # ≤5 melee, иначе disadvantage). PHB-2024 стр. 367.
        tgt_adv, tgt_disadv = ctx.condition_service.incoming_attack_adjustment(
            target, distance_ft=distance_ft, attack_kind=params.kind
        )

        # 2) Бросок атаки. T4: боевой стиль Archery — +2 к ranged-атаке.
        total_atk_bonus = (
            params.attack_bonus
            + atk_adj.numeric_bonus
            + fighting_style_attack_bonus(actor, params.kind)
        )
        attack_expr = DiceExpr.parse(f"d20{total_atk_bonus:+d}")
        attack_ctx = RollContext(
            purpose=RollPurpose.ATTACK,
            actor_id=actor.id,
            target_id=target.id,
            advantage=atk_adj.advantage or help_bonus or tgt_adv,
            disadvantage=(
                atk_adj.disadvantage or long_range_penalty or dodge_penalty
                or tgt_disadv
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
        # Порог крита берётся из actor.crit_range_min (по умолчанию 20 — обычное
        # существо; Improved Critical Чемпиона ставит 19). R1.
        _d20 = attack_roll.d20_raw if attack_roll.d20_raw is not None else 0
        is_crit = _d20 >= actor.crit_range_min
        is_crit_miss = attack_roll.is_natural_1()
        if is_crit:
            hit = True
        elif is_crit_miss:
            hit = False
        else:
            hit = attack_roll.total >= effective_ac

        # Q-4 / T3: попадание в упор (≤5 фт, melee) по беспомощной цели —
        # авто-крит (PHB-2024 стр. 27, 367). Беспомощность: 0 HP (умирает)
        # ИЛИ Paralyzed / Unconscious (даже при полном HP, напр. Hold Person).
        melee_point_blank = params.kind is AttackKind.MELEE and distance_ft <= 5
        helpless = (
            target.is_at_zero_hp
            or target.has_condition(PARALYZED)
            or target.has_condition(UNCONSCIOUS)
        )
        if hit and melee_point_blank and helpless:
            is_crit = True

        # d20_raw=None бывает для не-d20 бросков; здесь это всегда d20,
        # но pydantic-поле int — гонзим к 0 на всякий случай.
        d20_raw_safe = attack_roll.d20_raw if attack_roll.d20_raw is not None else 0
        ctx.event_bus.publish(
            AttackRolled(
                attacker_id=actor.id,
                target_id=target.id,
                attack_roll_id=attack_roll.roll_id,
                effective_ac=effective_ac,
                is_critical_hit=is_crit,
                is_critical_miss=is_crit_miss,
                hit=hit,
                d20_raw=d20_raw_safe,
                total=attack_roll.total,
                advantage=attack_ctx.advantage,
                disadvantage=attack_ctx.disadvantage,
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
            # T4: боевой стиль Dueling — +2 к урону melee.
            dmg_numeric = dmg_adj.numeric_bonus + fighting_style_damage_bonus(
                actor, params.kind
            )
            # Сборка через dataclasses.replace, не строковая конкатенация —
            # DiceExpr.parse не поддерживает «1d8+3+2» (одно опциональное
            # `[+-]\d+` в паттерне). Аудит 08 AT-R001.
            full_expr = (
                base_expr
                if dmg_numeric == 0
                else replace(base_expr, modifier=base_expr.modifier + dmg_numeric)
            )
            dmg_ctx = RollContext(
                purpose=RollPurpose.DAMAGE,
                actor_id=actor.id,
                target_id=target.id,
                crit=is_crit,
                extra_dice=dmg_adj.extra_dice,
            )
            damage_roll = ctx.dice_roller.roll(full_expr, dmg_ctx)

            # PHB-2024 стр. 26: «Минимальный урон». Атака с отрицательным
            # модификатором (например, STR=6 → mod=-2, 1d4-2 → возможен
            # total=-1) не лечит цель — урон клампится к 0. Аудит 14 VS-R002.
            raw_damage = max(0, damage_roll.total)

            # 6) Применить урон.
            damage_result = target.take_damage(
                DamageInstance(amount=raw_damage, type_=params.damage_type),
                is_critical=is_crit,
            )

            ctx.event_bus.publish(
                DamageDealt(
                    attacker_id=actor.id,
                    target_id=target.id,
                    damage_roll_id=damage_roll.roll_id,
                    damage_type=params.damage_type,
                    raw_amount=raw_damage,
                    final_amount=damage_result.final_amount,
                    is_critical=is_crit,
                    hp_after=target.hit_points.current,
                    hp_max=target.hit_points.maximum,
                    was_lethal=damage_result.was_lethal,
                )
            )
            published.append("damage.dealt")
            downed = damage_result.was_lethal
            concentration_dc = damage_result.concentration_save_dc

            # R1: Sneak Attack плута — доп. урон при выполнении условий.
            _maybe_sneak_attack(actor, target, params, attack_ctx, ctx, is_crit)

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


_SNEAK_ATTACK = FeatureId("sneak_attack")


def _maybe_sneak_attack(
    actor: Creature,
    target: Creature,
    params: AttackParams,
    attack_ctx: RollContext,
    ctx: TurnContext,
    is_crit: bool,
) -> None:
    """Плут: +⌈level/2⌉d6 раз за ход при finesse/дальнобойном оружии и
    (преимущество ИЛИ союзник цели рядом с целью). PHB-2024. Доп. урон того же
    типа, что оружие; на крите кости удваиваются (crit прокинут в RollContext)."""
    if _SNEAK_ATTACK not in actor.features or actor.sneak_used_this_turn:
        return
    # PHB-2024: Sneak Attack нельзя при помехе на бросок атаки (REV-5) —
    # даже если рядом с целью стоит союзник.
    if attack_ctx.disadvantage:
        return
    weapon = actor.equipped_weapon
    if weapon is None or not (weapon.finesse or params.kind is AttackKind.RANGED):
        return
    has_advantage = attack_ctx.advantage and not attack_ctx.disadvantage
    if not (has_advantage or _ally_adjacent_to(target, actor, ctx)):
        return
    n = (actor.level + 1) // 2
    sneak_roll = ctx.dice_roller.roll(
        DiceExpr.parse(f"{n}d6"),
        RollContext(
            purpose=RollPurpose.DAMAGE, actor_id=actor.id,
            target_id=target.id, crit=is_crit, tags=("sneak_attack",),
        ),
    )
    actor.sneak_used_this_turn = True
    raw = max(0, sneak_roll.total)
    result = target.take_damage(DamageInstance(amount=raw, type_=params.damage_type))
    ctx.event_bus.publish(
        DamageDealt(
            attacker_id=actor.id, target_id=target.id,
            damage_roll_id=sneak_roll.roll_id, damage_type=params.damage_type,
            raw_amount=raw, final_amount=result.final_amount, is_critical=is_crit,
            hp_after=target.hit_points.current, hp_max=target.hit_points.maximum,
            was_lethal=result.was_lethal,
        )
    )


def _ally_adjacent_to(target: Creature, attacker: Creature, ctx: TurnContext) -> bool:
    """Есть ли у цели союзник атакующего в 5 фт (кроме самого атакующего) —
    условие Sneak Attack (PHB-2024)."""
    attacker_faction = ctx.factions.get(attacker.id)
    tpos = ctx.battlefield.position_of(target.id)
    for cid, cr in ctx.participants.items():
        if cid in (attacker.id, target.id) or not cr.is_alive:
            continue
        if ctx.factions.get(cid) != attacker_faction:
            continue
        if tpos.distance_to_feet(ctx.battlefield.position_of(cid)) <= 5:
            return True
    return False


__all__ = ["AttackAction", "AttackKind", "AttackParams"]

"""Encounter — entity «бой».

См. ``docs/ENCOUNTER.md``. Этот модуль покрывает F1: участники +
инициатива + базовые счётчики хода. Lifecycle-события и условие
конца боя — F2-F4 (см. план в ENCOUNTER.md §8).

Mutable entity application-уровня. Зависимости упакованы в
``EncounterDependencies`` — чтобы конструктор был кратким и чтобы
их же можно было переиспользовать при создании ``TurnContext``
для каждого хода.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dnd.application.dto.engine_event import (
    EncounterEnded,
    InitiativeRolled,
    OpportunityAttackProvoked,
    RoundEnded,
    RoundStarted,
    TurnEnded,
    TurnStarted,
)
from dnd.application.dto.ids import ConditionId, CreatureId
from dnd.application.dto.initiative import InitiativeEntry
from dnd.application.dto.rolls import RollContext, RollPurpose
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.conditions.builtin import (
    INCAPACITATED,
    PARALYZED,
    STUNNED,
    UNCONSCIOUS,
)
from dnd.domain.values.ability import Ability
from dnd.domain.values.dice import DiceExpr
from dnd.domain.values.faction import Faction

_log = logging.getLogger(__name__)

# Условия с speed=0 / без действий (PHB-2024 стр. 367). При них actor
# не получает движения в свой ход. _effective_speed_ft возвращает 0.
# Аудит 13 EN-R001.
_ZERO_SPEED_CONDITIONS: frozenset[ConditionId] = frozenset(
    {INCAPACITATED, PARALYZED, STUNNED, UNCONSCIOUS}
)

if TYPE_CHECKING:
    from dnd.application.engine.condition_service import ConditionService
    from dnd.application.engine.modifier_applier import ModifierApplier
    from dnd.application.ports.dice_roller import DiceRoller
    from dnd.application.ports.event_bus import EventBus
    from dnd.domain.entities.battlefield import Battlefield
    from dnd.domain.entities.creature import Creature
    from dnd.domain.ports.rng import RNG


@dataclass(slots=True)
class EncounterDependencies:
    """Группировка внешних сервисов, нужных и ``Encounter``, и
    ``TurnContext`` (которые Encounter создаст в F2).
    """

    battlefield: Battlefield
    dice_roller: DiceRoller
    modifier_applier: ModifierApplier
    condition_service: ConditionService
    event_bus: EventBus
    rng: RNG


class EncounterAlreadyStartedError(RuntimeError):
    """``start()`` вызван второй раз."""


class EncounterNotStartedError(RuntimeError):
    """Доступ к ``current_actor_id`` / order до ``start()``."""


# Тип политики реакций. Получает событие и сам Encounter; решает —
# делать ли OA, какое оружие и т.п. Возвращать ничего не должно;
# вся работа — через ``Encounter`` (его battlefield, participants,
# deps). См. ``docs/ENCOUNTER.md`` §6.
ReactionPolicy = Callable[[OpportunityAttackProvoked, "Encounter"], None]


def noop_reaction_policy(
    _event: OpportunityAttackProvoked, _encounter: Encounter
) -> None:
    """Дефолтная политика — ничего не делает; провокация публикуется,
    но реакция остаётся неиспользованной. Подходит для UI-режима,
    где игрок сам решает."""


# Стойки, очищаемые на старте каждого хода владельца
# (PHB-2024 стр. 22: «benefit ends at the start of your next turn»).
# Это значения CombatStance из stances.py — дублируем строками здесь,
# чтобы Encounter не зависел от модуля stances.
_STANCES_CLEARED_ON_TURN_START = frozenset({"dodging", "dashing", "disengaged"})


@dataclass(slots=True)
class _State:
    """Внутреннее состояние Encounter (mutable). Снаружи доступ через
    свойства самого Encounter — это даёт чистый API без рутины
    мутирования полей dataclass'а."""

    started: bool = False
    concluded: bool = False
    round_number: int = 0
    current_turn_index: int = 0
    initiative_order: tuple[InitiativeEntry, ...] = field(default_factory=tuple)


class Encounter:
    """Сценарий боя: участники, фракции, поле, инициатива.

    Конструктор не запускает бой. Запуск — :meth:`start`, после
    которого доступны ``initiative_order`` / ``current_actor_id`` /
    ``round_number``.

    **Single-shot**: после :class:`EncounterEnded` Encounter
    становится бесполезным — повторный ``start()`` запрещён, любые
    ``start_turn``/``end_turn`` → ``RuntimeError``. Для нового боя
    создавайте новый объект. Аудит 13 EN-A006.

    **Hard-guard от зацикливания**: при превышении ``MAX_ROUNDS``
    раундов бой принудительно завершается с ``winners=None``.
    Аудит 14 VS-G001.
    """

    # Защита от багов AI/handler'ов. 100 раундов = 10 минут игрового
    # времени; реалистичный бой укладывается в 5-10 раундов.
    MAX_ROUNDS: int = 100

    def __init__(
        self,
        *,
        participants: dict[CreatureId, Creature],
        factions: dict[CreatureId, Faction],
        deps: EncounterDependencies,
        reaction_policy: ReactionPolicy | None = None,
    ) -> None:
        if not participants:
            raise ValueError("encounter must have at least one participant")
        missing = set(participants) - set(factions)
        if missing:
            raise ValueError(
                f"factions missing for participants: {sorted(missing)}"
            )
        unknown = set(factions) - set(participants)
        if unknown:
            raise ValueError(
                f"factions has unknown creature_ids: {sorted(unknown)}"
            )

        # Делаем неглубокую копию: добавление participants после start()
        # в MVP не поддерживается — initiative_order фиксирован при start(),
        # и новый existo не получит хода (см. аудит 13 EN-A003).
        # Полноценный API `add_participant(...)` — пост-F4.
        self._participants = dict(participants)
        self._factions = dict(factions)
        self._deps = deps
        self._reaction_policy: ReactionPolicy = (
            reaction_policy or noop_reaction_policy
        )
        self._state = _State()
        self._unsubscribe_provoked: Callable[[], None] | None = None

    # --- read-only API ------------------------------------------------

    @property
    def participants(self) -> dict[CreatureId, Creature]:
        return self._participants

    @property
    def factions(self) -> dict[CreatureId, Faction]:
        return self._factions

    @property
    def battlefield(self) -> Battlefield:
        return self._deps.battlefield

    @property
    def deps(self) -> EncounterDependencies:
        return self._deps

    @property
    def has_started(self) -> bool:
        return self._state.started

    @property
    def round_number(self) -> int:
        if not self._state.started:
            raise EncounterNotStartedError(
                "round_number is undefined until start() is called"
            )
        return self._state.round_number

    @property
    def initiative_order(self) -> tuple[InitiativeEntry, ...]:
        if not self._state.started:
            raise EncounterNotStartedError(
                "initiative_order is undefined until start() is called"
            )
        return self._state.initiative_order

    @property
    def current_turn_index(self) -> int:
        if not self._state.started:
            raise EncounterNotStartedError(
                "current_turn_index is undefined until start() is called"
            )
        return self._state.current_turn_index

    @property
    def current_actor_id(self) -> CreatureId:
        if not self._state.started:
            raise EncounterNotStartedError(
                "current_actor_id is undefined until start() is called"
            )
        return self._state.initiative_order[self._state.current_turn_index].creature_id

    # --- запуск ------------------------------------------------------

    def start(self) -> None:
        """Бросить инициативу всем живым participants и сформировать
        порядок ходов. Публикует :class:`InitiativeRolled`,
        :class:`RoundStarted` (1) и сбрасывает reactions всех existo.

        Мёртвые на момент старта (``not is_alive``) в порядок не
        попадают — они и так не ходят (PHB-2024 стр. 22).
        """
        if self._state.started:
            raise EncounterAlreadyStartedError(
                "Encounter.start() may be called only once"
            )

        entries: list[InitiativeEntry] = []
        for insertion_order, (cid, creature) in enumerate(self._participants.items()):
            if not creature.is_alive:
                continue
            entries.append(self._roll_initiative_for(cid, creature, insertion_order))

        # Сортировка: total DESC, d20 DESC, dex DESC, insertion_order ASC.
        entries.sort(
            key=lambda e: (-e.total, -e.d20_raw, -e.dex_score, e.insertion_order)
        )

        order = tuple(entries)
        self._state.started = True
        self._state.initiative_order = order
        self._state.round_number = 1
        self._state.current_turn_index = 0

        self._deps.event_bus.publish(InitiativeRolled(order=order))
        # Сразу же — старт первого раунда (сброс reactions + RoundStarted).
        self._begin_round(1)
        # Если одна из воюющих сторон уже выкошена до начала (offscreen
        # урон, scripted setup) — закрыть бой сразу, без пустых ходов
        # (аудит 13 EN-A002).
        if self._check_end_condition():
            return
        # Подписка на провокации — handler политики решает, делать ли OA.
        self._unsubscribe_provoked = self._deps.event_bus.subscribe(
            OpportunityAttackProvoked, self._on_provoked
        )

    def _on_provoked(self, event: OpportunityAttackProvoked) -> None:
        """Делегирование политике. Бой может уже быть concluded — тогда
        провокация игнорируется (политику не дёргаем).

        **Контракт ReactionPolicy** (аудит 13 EN-A001):
        - policy НЕ должна вызывать lifecycle-методы Encounter
          (start_turn / end_turn / start) — это приведёт к расхождению
          ходового указателя;
        - policy может читать state Encounter и исполнять Action'ы
          (например, OpportunityAttack.execute);
        - если policy бросит — исключение ловится, логируется как
          ERROR, бой продолжается; реакция считается несделанной.
          Иначе шина проглотила бы исключение молча, и диагностика
          «почему враг не сделал OA» становилась бы невозможной.
        """
        if self._state.concluded:
            return
        try:
            self._reaction_policy(event, self)
        except Exception:
            _log.exception(
                "reaction_policy raised for OpportunityAttackProvoked "
                "(threatener=%s, actor=%s); reaction skipped",
                event.threatener_id,
                event.actor_id,
            )

    # --- lifecycle (F2) ----------------------------------------------

    @property
    def is_concluded(self) -> bool:
        """``True`` после публикации :class:`EncounterEnded`."""
        return self._state.concluded

    def start_turn(self) -> TurnContext:
        """Начать ход текущего actor'а: очистить его stances, создать
        свежий ``TurnContext``, опубликовать :class:`TurnStarted`.

        Если actor `is_at_zero_hp` или иначе не может ходить, событие
        публикуется с ``skipped=True``, TurnContext всё равно возвращается
        (вызывающий обычно сразу делает ``end_turn``).

        После :meth:`is_concluded` любой ``start_turn`` — ошибка.
        """
        self._require_started()
        if self._state.concluded:
            raise RuntimeError("encounter is concluded; no more turns")

        actor_id = self.current_actor_id
        actor = self._participants[actor_id]

        # Сброс stances своего хода (PHB-2024 стр. 22).
        actor.combat_stances -= _STANCES_CLEARED_ON_TURN_START

        # Сброс Help-якорей (PHB-2024 стр. 22: «until the start of your
        # next turn or until you have advantaged an attack»). Аудит 13 EN-A004.
        self._clear_pending_help(actor)

        # Свежий TurnContext.
        ctx = TurnContext(
            actor_id=actor_id,
            battlefield=self._deps.battlefield,
            dice_roller=self._deps.dice_roller,
            modifier_applier=self._deps.modifier_applier,
            condition_service=self._deps.condition_service,
            event_bus=self._deps.event_bus,
            rng=self._deps.rng,
            participants=self._participants,
            movement_remaining_ft=self._effective_speed_ft(actor),
            round_number=self._state.round_number,
            turn_number_in_round=self._state.current_turn_index,
        )

        skipped = actor.is_at_zero_hp or not actor.is_alive
        self._deps.event_bus.publish(
            TurnStarted(
                actor_id=actor_id,
                round_number=self._state.round_number,
                skipped=skipped,
            )
        )
        return ctx

    def end_turn(self) -> None:
        """Закрыть ход текущего actor'а; опубликовать :class:`TurnEnded`.

        Проверить условие конца боя (см. :meth:`_check_end_condition`).
        Если бой не завершён — сдвинуть указатель на следующего actor'а,
        при достижении конца initiative — закрыть раунд и начать новый.
        """
        self._require_started()
        if self._state.concluded:
            raise RuntimeError("encounter is concluded; cannot end_turn")

        actor_id = self.current_actor_id
        self._deps.event_bus.publish(
            TurnEnded(
                actor_id=actor_id,
                round_number=self._state.round_number,
            )
        )

        if self._check_end_condition():
            return  # _check_end_condition опубликует EncounterEnded и пометит concluded

        self._advance_turn_pointer()

    # --- внутренние helper'ы -----------------------------------------

    def _require_started(self) -> None:
        if not self._state.started:
            raise EncounterNotStartedError("call start() first")

    def _effective_speed_ft(self, creature: Creature) -> int:
        """Скорость actor'а в момент его хода.

        PHB-2024 стр. 367: Paralyzed / Stunned / Unconscious /
        Incapacitated → speed=0. Аудит 13 EN-R001.

        TODO: интегрировать с ``ModifierApplier`` через
        ``ModifierTargetKind.SPEED`` для Bless-/Slow-/Haste-эффектов
        (после расширения MODIFIERS.md).
        """
        for cond in _ZERO_SPEED_CONDITIONS:
            if creature.has_condition(cond):
                return 0
        if not creature.is_alive or creature.is_at_zero_hp:
            return 0
        return creature.speed_ft

    def _clear_pending_help(self, helper: Creature) -> None:
        """На старте хода helper'а сбросить неиспользованную помощь
        (PHB-2024 стр. 22: «until the start of your next turn»).

        Поле ``helped_against`` хранится у того, кто **получает помощь**
        (ally), а парное ``helped_by`` указывает на helper'а. Так что мы
        пробегаемся по participants и сбрасываем у тех, у кого
        ``helped_by == helper.id``.
        """
        for cr in self._participants.values():
            if cr.helped_by == helper.id:
                cr.helped_against = None
                cr.helped_by = None

    def _advance_turn_pointer(self) -> None:
        """Сдвинуть current_turn_index или открыть следующий раунд.

        Hard-guard от бесконечного боя (аудит 14 VS-G001): если число
        раундов превысило :attr:`MAX_ROUNDS`, бой принудительно
        завершается ничьей.
        """
        next_index = self._state.current_turn_index + 1
        if next_index < len(self._state.initiative_order):
            self._state.current_turn_index = next_index
            return
        # Конец круга — закрыть текущий, открыть следующий.
        closed_round = self._state.round_number
        self._deps.event_bus.publish(RoundEnded(round_number=closed_round))
        next_round = self._state.round_number + 1
        if next_round > self.MAX_ROUNDS:
            self._force_end_by_round_limit()
            return
        self._state.round_number = next_round
        self._state.current_turn_index = 0
        self._begin_round(self._state.round_number)

    def _force_end_by_round_limit(self) -> None:
        """Принудительное закрытие боя — превышен лимит раундов.

        Это защита от багов AI / handler'ов, которые могут привести к
        зацикленному «Dodge / Dodge / Dodge» без урона. winners=None,
        survivors — все, кто ещё жив. Аудит 14 VS-G001.
        """
        _log.warning(
            "encounter forcefully ended: round limit %d reached",
            self.MAX_ROUNDS,
        )
        survivors = tuple(
            cid for cid, cr in self._participants.items() if cr.is_alive
        )
        self._state.concluded = True
        if self._unsubscribe_provoked is not None:
            self._unsubscribe_provoked()
            self._unsubscribe_provoked = None
        self._deps.event_bus.publish(
            EncounterEnded(
                winners=None,
                round_number=self._state.round_number,
                survivors=survivors,
            )
        )

    def _begin_round(self, n: int) -> None:
        """Сброс reactions у всех живых participants + публикация
        :class:`RoundStarted`."""
        for cr in self._participants.values():
            if cr.is_alive:
                cr.reaction_used = False
        self._deps.event_bus.publish(RoundStarted(round_number=n))

    # --- условие конца (F3) ------------------------------------------

    def _check_end_condition(self) -> bool:
        """Проверить, не закончился ли бой. Если да — опубликовать
        :class:`EncounterEnded` и пометить ``concluded=True``.

        Бой считается законченным, когда **меньше одной** не-NEUTRAL
        фракции имеет живых participants.

        Returns:
            True если бой завершён (вызывающему не нужно продолжать).
        """
        alive_by_faction: dict[Faction, list[CreatureId]] = {}
        for cid, cr in self._participants.items():
            if not cr.is_alive:
                continue
            alive_by_faction.setdefault(self._factions[cid], []).append(cid)

        combat_factions = {
            f: ids
            for f, ids in alive_by_faction.items()
            if f is not Faction.NEUTRAL
        }

        if len(combat_factions) > 1:
            return False  # обе стороны ещё в бою

        # Победитель — единственная оставшаяся не-NEUTRAL фракция, либо
        # None (обе стороны выкошены — или остались только NEUTRAL).
        winners = next(iter(combat_factions)) if combat_factions else None

        survivors: tuple[CreatureId, ...] = tuple(
            cid for ids in alive_by_faction.values() for cid in ids
        )

        self._state.concluded = True
        # Отписаться от провокаций — нет смысла слушать после конца боя.
        if self._unsubscribe_provoked is not None:
            self._unsubscribe_provoked()
            self._unsubscribe_provoked = None
        self._deps.event_bus.publish(
            EncounterEnded(
                winners=winners,
                round_number=self._state.round_number,
                survivors=survivors,
            )
        )
        return True

    def _roll_initiative_for(
        self,
        cid: CreatureId,
        creature: Creature,
        insertion_order: int,
    ) -> InitiativeEntry:
        dex_score = creature.abilities.get(Ability.DEX).score
        dex_mod = creature.abilities.modifier(Ability.DEX)
        expr = DiceExpr.parse(f"d20{dex_mod:+d}")
        ctx = RollContext(
            purpose=RollPurpose.INITIATIVE,
            actor_id=cid,
            tags=("initiative",),
        )
        result = self._deps.dice_roller.roll(expr, ctx)
        # d20_raw обязателен для tie-break: инициатива по PHB-2024 — это
        # d20-бросок. Если кастомный DiceRoller вернул не-d20, лучше
        # упасть громко, чем тихо разрушать tie-break нулями.
        # Аудит 13 EN-R003.
        if result.d20_raw is None:
            raise RuntimeError(
                f"INITIATIVE roll for {cid!r} must be d20-based; "
                f"DiceRoller returned EngineRollResult without d20_raw"
            )
        d20_raw = result.d20_raw
        return InitiativeEntry(
            creature_id=cid,
            total=result.total,
            d20_raw=d20_raw,
            dex_score=dex_score,
            insertion_order=insertion_order,
            roll_id=result.roll_id,
        )


__all__ = [
    "Encounter",
    "EncounterAlreadyStartedError",
    "EncounterDependencies",
    "EncounterNotStartedError",
    "ReactionPolicy",
    "noop_reaction_policy",
]

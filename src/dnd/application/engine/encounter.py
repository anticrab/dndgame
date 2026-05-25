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
    AttackResolved,
    CreatureDied,
    DeathSaveRolled,
    EncounterEnded,
    InitiativeRolled,
    OpportunityAttackProvoked,
    RoundEnded,
    RoundStarted,
    TurnEnded,
    TurnStarted,
)
from dnd.application.dto.ids import ConditionId, CreatureId, ObjectId
from dnd.application.dto.initiative import InitiativeEntry
from dnd.application.dto.rolls import RollContext, RollPurpose
from dnd.application.engine.spells.handlers import concentration_source
from dnd.application.engine.turn_context import TurnContext
from dnd.application.inventory.loot_helpers import dump_loot_entries
from dnd.domain.conditions.builtin import (
    INCAPACITATED,
    PARALYZED,
    STUNNED,
    UNCONSCIOUS,
)
from dnd.domain.entities.interactable import InteractableObject
from dnd.domain.values.ability import Ability
from dnd.domain.values.dice import DiceExpr
from dnd.domain.values.faction import Faction
from dnd.domain.values.object_kind import ObjectKind

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
    """Политика для UI-режима, где игрок сам решает.

    Дефолтом для production не подходит: в боевке без OA-реакций
    отходить от противника — бесплатно. Это нарушает PHB-2024 стр. 22
    («provokes an opportunity attack»). Дефолтно подключаем
    :func:`~dnd.application.engine.reaction_policy.auto_melee_oa_policy`
    (см. ниже)."""


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
        if reaction_policy is None:
            # Импорт здесь — иначе цикл reaction_policy.py → encounter.
            from dnd.application.engine.reaction_policy import (
                auto_melee_oa_policy,
            )

            reaction_policy = auto_melee_oa_policy
        self._reaction_policy: ReactionPolicy = reaction_policy
        self._state = _State()
        self._unsubscribe_provoked: Callable[[], None] | None = None
        self._unsubscribe_downed: Callable[[], None] | None = None

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
    def event_bus(self) -> EventBus:
        """Прямой доступ к шине событий (proxy через deps).

        Удобство для подписчиков (UI / журналов): не нужно лазать через
        ``enc.deps.event_bus``. Аудит 15 CL-A002.
        """
        return self._deps.event_bus

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
        # Q-2: реакция на падение цели в 0 HP (PC → dying, NPC → CORPSE).
        self._unsubscribe_downed = self._deps.event_bus.subscribe(
            AttackResolved, self._on_downed
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

    def _on_downed(self, event: AttackResolved) -> None:
        """Реакция на падение цели в 0 HP (PHB-2024 стр. 27).

        PC (uses_death_saves) → переход в dying: Unconscious + DeathSaveState.
        NPC (расходник) → превращение в труп (CORPSE) — реализуется в Q-8.
        """
        if not event.downed or self._state.concluded:
            return
        target = self._participants.get(event.target_id)
        if target is None:
            return
        # MAJOR-1 (P1-audit): летальный урон авто-рвёт концентрацию
        # (Creature.take_damage обнулил target.concentration); снимаем и
        # модификатор-бафф этого кастера (иначе +AC «висел» бы вечно).
        self._deps.modifier_applier.remove_by_source(
            concentration_source(target.id)
        )
        if target.uses_death_saves and target.is_at_zero_hp:
            target.begin_dying()
            # Огромный урон (massive damage) убивает PC мгновенно: take_damage
            # уже выставил failures=3, begin_dying() стал no-op. Публикуем
            # CreatureDied здесь, иначе смерть пройдёт «молча» (audit M-1).
            if target.is_dead:
                self._deps.event_bus.publish(CreatureDied(actor_id=target.id))
        elif not target.uses_death_saves and target.is_at_zero_hp:
            # NPC-расходник: труп с лутом (Q-8). CreatureDied для лога.
            self._spawn_corpse(target)
            self._deps.event_bus.publish(CreatureDied(actor_id=target.id))

    def _spawn_corpse(self, dead: Creature) -> None:
        """Положить CORPSE-объект с инвентарём павшего NPC для лута (Q-8).

        Само мёртвое существо остаётся на сетке (рендерится как ``%``);
        CORPSE-объект — контейнер лута, лутается тем же Interact+Pickup,
        что и сундук. Идемпотентно: повторный вызов ничего не делает.
        """
        corpse_id = ObjectId(f"corpse-{dead.id}")
        try:
            self._deps.battlefield.object_at(corpse_id)
            return  # труп уже есть
        except KeyError:
            pass
        if not self._deps.battlefield.has_creature(dead.id):
            return  # нет позиции — нечего класть
        pos = self._deps.battlefield.position_of(dead.id)
        self._deps.battlefield.place_object(InteractableObject(
            id=corpse_id,
            kind=ObjectKind.CORPSE,
            pos=pos,
            state={
                "open": False,
                "locked": False,
                "hp": 1,
                "ac": 5,
                "contents": dump_loot_entries(dead.inventory.stacks),
            },
        ))

    def _roll_death_save_for(self, actor: Creature) -> None:
        """Бросить за лежачего PC спасбросок от смерти (PHB-2024 стр. 27).

        Спасброски от смерти без модификаторов — чистый d20. Публикует
        :class:`DeathSaveRolled`; при 3-м провале — :class:`CreatureDied`.
        """
        ctx = RollContext(
            purpose=RollPurpose.DEATH_SAVE,
            actor_id=actor.id,
            tags=("death_save",),
        )
        result = self._deps.dice_roller.roll(DiceExpr.parse("d20"), ctx)
        d20_raw = result.d20_raw if result.d20_raw is not None else result.total
        outcome = actor.roll_death_save(d20_raw)
        self._deps.event_bus.publish(
            DeathSaveRolled(
                actor_id=actor.id,
                d20_raw=outcome.d20_raw,
                result=outcome.result,
                successes=outcome.successes,
                failures=outcome.failures,
            )
        )
        if actor.is_dead:
            self._deps.event_bus.publish(CreatureDied(actor_id=actor.id))

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

        # Q-3: лежачий PC на старте своего хода бросает спасбросок от смерти
        # (PHB-2024 стр. 27). Stable/dead — не бросают.
        if (
            actor.death_saves is not None
            and not actor.death_saves.is_dead
            and not actor.death_saves.is_stable
        ):
            self._roll_death_save_for(actor)

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
            factions=self._factions,
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
        if self._unsubscribe_downed is not None:
            self._unsubscribe_downed()
            self._unsubscribe_downed = None
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

    def outcome_decided(self) -> bool:
        """Решён ли исход боя прямо сейчас (без публикации события).

        Возвращает True, когда живых из разных воюющих фракций уже не
        больше одной — то есть `_check_end_condition` опубликовал бы
        EncounterEnded, если бы его вызвали сию секунду. Используется
        GameRunner внутри цикла PC-турна, чтобы досрочно прерваться
        сразу после удара, убившего последнего врага (иначе игрок
        получает ещё один prompt уже в законченном бою).
        """
        return self._is_outcome_decided()

    @staticmethod
    def _is_combatant(cr: Creature) -> bool:
        """Существо ещё «в бою»: живо ИЛИ спасаемо (dying, но не мёртв).

        Q-5: лежачий PC (0 HP, uses_death_saves, не is_dead) держит свою
        фракцию в бою — спасброски от смерти отыгрываются (PHB-2024 стр. 27).
        """
        if cr.is_alive:
            return True
        return (
            cr.uses_death_saves
            and cr.death_saves is not None
            and not cr.death_saves.is_dead
        )

    def _is_outcome_decided(self) -> bool:
        combatant_by_faction: dict[Faction, list[CreatureId]] = {}
        for cid, cr in self._participants.items():
            if not self._is_combatant(cr):
                continue
            combatant_by_faction.setdefault(self._factions[cid], []).append(cid)
        combat_factions = [
            f for f in combatant_by_faction if f is not Faction.NEUTRAL
        ]
        return len(combat_factions) <= 1

    def _check_end_condition(self) -> bool:
        """Проверить, не закончился ли бой. Если да — опубликовать
        :class:`EncounterEnded` и пометить ``concluded=True``.

        Бой считается законченным, когда **меньше одной** не-NEUTRAL
        фракции имеет живых participants.

        Returns:
            True если бой завершён (вызывающему не нужно продолжать).
        """
        combatant_by_faction: dict[Faction, list[CreatureId]] = {}
        for cid, cr in self._participants.items():
            if not self._is_combatant(cr):
                continue
            combatant_by_faction.setdefault(self._factions[cid], []).append(cid)

        combat_factions = {
            f: ids
            for f, ids in combatant_by_faction.items()
            if f is not Faction.NEUTRAL
        }

        if len(combat_factions) > 1:
            return False  # обе стороны ещё в бою

        # Победитель — единственная оставшаяся не-NEUTRAL фракция, либо
        # None (обе стороны выкошены — или остались только NEUTRAL).
        winners = next(iter(combat_factions)) if combat_factions else None

        # Survivors — только реально живые (HP>0). Лежачий-но-спасаемый PC
        # держал бой, но survivor'ом не считается (он dying).
        survivors: tuple[CreatureId, ...] = tuple(
            cid for cid, cr in self._participants.items() if cr.is_alive
        )

        self._state.concluded = True
        # Отписаться от провокаций — нет смысла слушать после конца боя.
        if self._unsubscribe_provoked is not None:
            self._unsubscribe_provoked()
            self._unsubscribe_provoked = None
        if self._unsubscribe_downed is not None:
            self._unsubscribe_downed()
            self._unsubscribe_downed = None
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

"""Creature — базовое существо в игре (PC и NPC/монстр).

Это **mutable entity**, в отличие от value-объектов. Операции
``take_damage``/``heal``/``apply_condition`` меняют состояние на месте
и возвращают **DTO-результат** с тем, что произошло — это нужно
вызывающему слою (Encounter/GameEngine) для публикации событий через
EventBus. Сам Creature остаётся pure domain без зависимости от
EventBus.

Связь с другими сущностями:

* `Character` (PC) — композиция поверх `Creature` (см. Q25). Добавляет
  level/xp/alignment/biography/death_saves/spell_slots.
* `Monster` (NPC-противник) — расширение `Creature` (или композиция,
  по решению пост-MVP). Добавляет challenge_rating, ai_profile,
  loot_table.

Книжные правила, реализованные здесь:

* HP с временными хитами и переход в 0 HP (Книга 2024 стр. 26-27).
* Применение урона по типу с учётом сопротивления/уязвимости/
  иммунитета (Книга 2024 стр. 26 «Сопротивление и Уязвимость»).
* Конкуррентность с правилом «Концентрация» (Книга 2024 стр. 352,
  глоссарий): при ненулевом уроне требуется CON-save с
  ``DC = min(30, max(10, damage // 2))``; при падении в 0 HP или
  смерти концентрация **обрывается автоматически без save**.
* Истощение (Exhaustion) как отдельное поле 0..6, не Condition (Q34;
  Книга 2024 стр. 352, глоссарий «Истощённый»).
* Состояния как множество ConditionId — реальное поведение Condition
  будет в отдельной задаче #28; здесь только трекер.
* CreatureSize — для размера, занимаемого на карте (в MVP всегда MEDIUM).
* Vision — для последующей интеграции с VisibilitySystem.

Что **не** делает Creature:

* не публикует события в EventBus (это делает Encounter);
* не бросает кости (DiceRoller — снаружи);
* не валидирует line-of-sight (VisibilitySystem — снаружи);
* не знает про сценарий, локации, диалоги (Application).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dnd.application.dto.ids import ConditionId, CreatureId, SpellId
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.creature_size import CreatureSize
from dnd.domain.values.damage import (
    DamageInstance,
    DamageMultiplier,
    apply_damage_multiplier,
    combine_multipliers,
)
from dnd.domain.values.hit_points import HitPoints
from dnd.domain.values.vision import NORMAL_VISION, Vision

_MAX_EXHAUSTION = 6
_CONCENTRATION_DC_FLOOR = 10
_CONCENTRATION_DC_CAP = 30


def concentration_save_dc(damage: int) -> int:
    """Сложность спасброска CON на сохранение концентрации.

    Книга 2024, стр. 352, глоссарий «Концентрация»: «Сложность равна
    10 или половине полученного урона (округляется в меньшую сторону),
    в зависимости от того, какое число больше, **но не более Сл. 30**».
    """
    if damage < 0:
        raise ValueError(f"damage must be >= 0, got {damage}")
    return min(_CONCENTRATION_DC_CAP, max(_CONCENTRATION_DC_FLOOR, damage // 2))


@dataclass(frozen=True, slots=True)
class DamageResult:
    """Что произошло в результате take_damage. Передаётся в EventBus
    вызывающим слоем."""

    raw_amount: int
    """Урон ДО применения резистов/уязвимостей — то, что прилетело."""

    final_amount: int
    """Урон ПОСЛЕ применения резистов и иммунитетов."""

    overflow: int
    """Сколько урона ушло «за 0» — нужно для massive-damage правила."""

    was_lethal: bool
    """Снизился ли HP до 0 этим уроном."""

    killed_outright: bool
    """Massive damage: overflow >= maximum — мгновенная смерть NPC."""

    concentration_save_dc: int | None = None
    """Сложность CON-save, который вызывающий слой должен сделать через
    DiceRoller, чтобы решить, сохранилась ли концентрация. ``None``,
    если у существа не было концентрации или урон был 0."""

    concentration_ended_automatically: bool = False
    """Концентрация **закончилась без save**. По книге так происходит,
    когда существо падает в 0 HP или умирает (стр. 352). Если этот флаг
    True, то ``self.concentration`` уже очищена методом take_damage."""


@dataclass(frozen=True, slots=True)
class HealResult:
    """Что произошло в результате heal."""

    raw_amount: int
    """Сколько было «заявлено»."""

    final_amount: int
    """Сколько реально восстановили (с учётом max и стартового HP)."""

    revived: bool
    """Поднял ли с 0 HP в сознание."""


@dataclass(slots=True)
class Creature:
    """Базовое существо. Mutable entity.

    Создаётся через :meth:`Creature.create`, чтобы гарантировать
    согласованные стартовые значения (current_hp = max_hp, etc.).
    """

    id: CreatureId
    name: str
    """Технический идентификатор-имя (английский). Для UI идёт через
    i18n-ключ ``creature.{id}.name`` — см. docs/I18N.md."""

    abilities: AbilityScores
    hit_points: HitPoints
    armor_class: int
    speed_ft: int
    """Скорость в футах (5 фут = 1 клетка). Базовая скорость без
    модификаторов; реальная — пересчитывается с учётом ModifierBag."""

    size: CreatureSize = CreatureSize.MEDIUM
    vision: tuple[Vision, ...] = (NORMAL_VISION,)

    resistances: frozenset[str] = field(default_factory=frozenset)
    vulnerabilities: frozenset[str] = field(default_factory=frozenset)
    immunities: frozenset[str] = field(default_factory=frozenset)
    """Сопротивления/уязвимости/иммунитеты по строковым ID DamageType
    (``DamageType.FIRE.value``). frozenset, чтобы было хешируемо и
    сериализуемо. Изменения — через явные операции, не прямой доступ."""

    condition_immunities: frozenset[ConditionId] = field(default_factory=frozenset)
    """Состояния, к которым существо имеет иммунитет (например,
    конструкт против Charmed). См. Q28 — Conditions registry."""

    exhaustion: int = 0
    """0..6. На 6 — смерть (Q34). Влияет на броски через
    ModifierApplier (-2 ко всем d20 за каждый уровень начиная с 1)."""

    conditions: set[ConditionId] = field(default_factory=set)
    """Активные состояния. Полноценная Condition-логика — в отдельном
    регистре (task #28); здесь только трекинг наложен/снят."""

    reaction_used: bool = False
    """Использовал ли реакцию в **этом раунде**.

    Reaction — per-creature per-round, не per-turn (PHB-2024 стр. 22).
    Поле тут, а не в TurnContext, потому что реакции случаются в чужой
    ход (например, opportunity attack). Очищает ``Encounter`` на старте
    каждого нового раунда.
    """

    helped_against: CreatureId | None = None
    """ID цели, на которую этому существу полагается advantage на
    следующую атаку (PHB-2024 стр. 22, Help action).

    One-shot: сбрасывается в ``AttackAction.execute`` сразу после
    использования (atk-роллу даётся advantage, затем поле = None).
    Также Encounter сбросит на старте следующего хода owner'а
    (если не использовал).
    """

    helped_by: CreatureId | None = None
    """ID того, кто оказал Help. Нужен, чтобы в момент атаки проверить
    «if the target is no longer within 5 feet of you when the attack
    is made, you lose the benefit» (PHB-2024 стр. 22).

    Парное к ``helped_against`` — оба поля выставляются/сбрасываются
    вместе. Аудит 11 HS-R001.
    """

    combat_stances: set[str] = field(default_factory=set)
    """Активные «стойки» этого хода/раунда: DODGING / DASHING / DISENGAGED.

    Не Condition — стойка живёт до начала следующего хода владельца
    (DODGING/DISENGAGED) или текущего хода (DASHING — маркер
    дополнительного движения, бюджет уже выдан в момент Dash).
    Очищает ``Encounter`` (этап F) на старте хода. Значения декларирует
    ``dnd.application.engine.actions.stances.CombatStance``; здесь —
    ``set[str]``, чтобы domain не зависел от application-слоя.
    """

    concentration: SpellId | None = None
    """ID **заклинания**, которое существо удерживает концентрацией.

    Концентрация — это связь с конкретным spell-эффектом, не Condition
    (см. Книгу 2024, стр. 352, глоссарий «Концентрация»; ADR Q27).
    None для MVP-классов (Воин/Плут) и большинства NPC."""

    # --- фабрика --------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        id_: CreatureId,
        name: str,
        abilities: AbilityScores,
        max_hp: int,
        armor_class: int,
        speed_ft: int = 30,
        size: CreatureSize = CreatureSize.MEDIUM,
        vision: tuple[Vision, ...] = (NORMAL_VISION,),
        resistances: frozenset[str] = frozenset(),
        vulnerabilities: frozenset[str] = frozenset(),
        immunities: frozenset[str] = frozenset(),
    ) -> Creature:
        """Создать существо с полными HP.

        Используем фабрику вместо прямого ``__init__``, чтобы:

        * гарантировать ``current == maximum`` на старте;
        * валидировать входные параметры в одном месте;
        * иметь стабильное API при будущих расширениях полей.
        """
        if max_hp < 1:
            raise ValueError(f"creature max_hp must be >= 1, got {max_hp}")
        if armor_class < 1:
            raise ValueError(f"armor_class must be >= 1, got {armor_class}")
        if speed_ft < 0:
            raise ValueError(f"speed_ft must be >= 0, got {speed_ft}")
        return cls(
            id=id_,
            name=name,
            abilities=abilities,
            hit_points=HitPoints(current=max_hp, maximum=max_hp),
            armor_class=armor_class,
            speed_ft=speed_ft,
            size=size,
            vision=vision,
            resistances=resistances,
            vulnerabilities=vulnerabilities,
            immunities=immunities,
        )

    # --- состояние HP ---------------------------------------------------

    @property
    def is_alive(self) -> bool:
        """Существо живо, пока HP > 0. Отдельный флаг «мертво» (для NPC)
        или DeathSaveState (для PC) обрабатывается в `Character`/`Monster`."""
        return self.hit_points.current > 0

    @property
    def is_at_zero_hp(self) -> bool:
        """HP == 0 (механический факт), но **не** Condition Unconscious.

        Состояние Unconscious — это отдельный Condition с эффектами
        (Incapacitated, лежит, атаки в 5 фт — крит, провал STR/DEX-saves;
        Книга 2024 стр. 27 и стр. 367). Оно **накладывается** на PC при
        is_at_zero_hp, но для NPC просто означает смерть, и Condition
        не накладывается.

        Этот геттер — лишь индикатор «HP исчерпаны»; решение, нужен ли
        Condition и DeathSaveState, принимается в Character/Monster."""
        return self.hit_points.current == 0

    # --- damage --------------------------------------------------------

    def _damage_multiplier_for(self, damage_type: str) -> DamageMultiplier:
        return combine_multipliers(
            resistant=damage_type in self.resistances,
            vulnerable=damage_type in self.vulnerabilities,
            immune=damage_type in self.immunities,
        )

    def take_damage(
        self,
        damage: DamageInstance,
        *,
        is_critical: bool = False,
    ) -> DamageResult:
        """Принять одну порцию урона. Книга 2024 стр. 26.

        Алгоритм:

        1. Определить множитель урона из (resist/vulnerable/immune)
           для конкретного типа урона.
        2. Применить множитель.
        3. Списать урон с HP (через ``HitPoints.take_damage``): сначала
           temp HP, потом current; излишек на current.
        4. Зафиксировать overflow — если current уже был >0, а урон
           превысил его на N, то N — это overflow.
        5. Massive damage: если overflow >= maximum, ставится флаг
           ``killed_outright`` (книга, стр. 27).
        6. Концентрация (книга 2024 стр. 352, глоссарий «Концентрация»):
           a) ``was_lethal=True`` + ``concentration is not None`` →
              концентрация обрывается **автоматически, без save**;
              ``self.concentration = None`` сразу;
              ``concentration_ended_automatically=True``.
           b) Иначе если урон > 0 + ``concentration is not None`` →
              требуется CON-save; ``concentration_save_dc`` несёт
              ``min(30, max(10, final // 2))``. Реальный бросок —
              на DiceRoller уровнем выше.
           c) Урон 0 (иммунитет) — концентрация сохраняется без save.

        Возвращает :class:`DamageResult` для последующей публикации
        событий вызывающим слоем (Encounter).

        ``is_critical`` не влияет на сам урон — удвоение костей делает
        DiceRoller заранее. Параметр носится для уровня Character,
        чтобы при уроне на 0 HP отметить +2 провала спасбросков.
        """
        if damage.amount < 0:
            raise ValueError(f"damage amount must be >= 0, got {damage.amount}")

        multiplier = self._damage_multiplier_for(damage.type_.value)
        final = apply_damage_multiplier(damage.amount, multiplier)

        # Снимок состояния ДО удара — нужен, чтобы посчитать overflow
        # (temp HP «съедают» урон первыми), was_lethal и решить,
        # обрывается ли концентрация автоматически.
        was_alive = self.is_alive
        had_concentration = self.concentration is not None
        before_buffer = self.hit_points.current + self.hit_points.temporary

        self.hit_points = self.hit_points.take_damage(final)

        was_lethal = was_alive and not self.is_alive
        # Книга 2024 стр. 27 «Огромный урон»: если урон опустил HP до 0
        # и оставшийся урон (overflow) >= maximum — мгновенная смерть.
        # Overflow = сколько «не уместилось» в (current + temp) до удара.
        overflow = max(0, final - before_buffer)
        killed_outright = self.is_at_zero_hp and overflow >= self.hit_points.maximum

        # Концентрация (см. docstring пункт 6).
        concentration_ended_automatically = False
        save_dc: int | None = None
        if had_concentration:
            if was_lethal:
                self.concentration = None
                concentration_ended_automatically = True
            elif final > 0:
                save_dc = concentration_save_dc(final)

        return DamageResult(
            raw_amount=damage.amount,
            final_amount=final,
            overflow=overflow,
            was_lethal=was_lethal,
            killed_outright=killed_outright,
            concentration_save_dc=save_dc,
            concentration_ended_automatically=concentration_ended_automatically,
        )

    # --- heal ----------------------------------------------------------

    def heal(self, amount: int) -> HealResult:
        """Восстановить HP. Книга 2024 стр. 26 «Лечение».

        Возвращает :class:`HealResult` с информацией, поднял ли с 0 HP
        в сознание (это важно вызывающему слою для сброса
        DeathSaveState и снятия Unconscious).
        """
        if amount < 0:
            raise ValueError(f"heal amount must be >= 0, got {amount}")
        was_at_zero = self.is_at_zero_hp
        before = self.hit_points.current
        self.hit_points = self.hit_points.heal(amount)
        final = self.hit_points.current - before
        return HealResult(
            raw_amount=amount,
            final_amount=final,
            revived=was_at_zero and not self.is_at_zero_hp,
        )

    def gain_temporary_hp(self, amount: int) -> int:
        """Получить временные хиты. Возвращает реально применённое
        количество (старые могут быть больше — тогда новых не получает)."""
        if amount < 0:
            raise ValueError(f"temp HP amount must be >= 0, got {amount}")
        before = self.hit_points.temporary
        self.hit_points = self.hit_points.with_temporary(amount)
        return self.hit_points.temporary - before

    # --- conditions ---------------------------------------------------

    def apply_condition(self, condition: ConditionId) -> bool:
        """Наложить состояние. Возвращает True, если состояние было
        фактически добавлено (не было уже и нет иммунитета).

        Полная логика влияния состояния (модификаторы, ограничение
        действий, спасброски на снятие) — в Condition-плагине
        (см. task #28). Здесь только трекинг.
        """
        if condition in self.condition_immunities:
            return False
        if condition in self.conditions:
            return False
        self.conditions.add(condition)
        return True

    def remove_condition(self, condition: ConditionId) -> bool:
        """Снять состояние. Возвращает True, если оно было."""
        if condition not in self.conditions:
            return False
        self.conditions.discard(condition)
        return True

    def has_condition(self, condition: ConditionId) -> bool:
        return condition in self.conditions

    # --- exhaustion ----------------------------------------------------

    def add_exhaustion(self, levels: int = 1) -> int:
        """Прибавить уровни истощения (0..6). Возвращает новый уровень.

        Истощение — отдельная подсистема (Q34), не Condition. Уровень
        6 — смерть (вызывающий слой должен это обработать). Книга 2024
        упростила истощение: -2 ко всем d20 за каждый уровень.
        """
        if levels < 0:
            raise ValueError(f"exhaustion levels must be >= 0, got {levels}")
        self.exhaustion = min(_MAX_EXHAUSTION, self.exhaustion + levels)
        return self.exhaustion

    def remove_exhaustion(self, levels: int = 1) -> int:
        """Снять уровни истощения. Возвращает новый уровень."""
        if levels < 0:
            raise ValueError(f"exhaustion levels must be >= 0, got {levels}")
        self.exhaustion = max(0, self.exhaustion - levels)
        return self.exhaustion

    @property
    def is_exhaustion_lethal(self) -> bool:
        """Истощение 6 — мгновенная смерть существа."""
        return self.exhaustion >= _MAX_EXHAUSTION

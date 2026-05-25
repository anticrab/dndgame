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
from typing import Literal

from dnd.application.dto.ids import ConditionId, CreatureId, SpellId
from dnd.domain.conditions.builtin import UNCONSCIOUS
from dnd.domain.entities.inventory import Inventory
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.ability_id import AbilityId
from dnd.domain.values.creature_size import CreatureSize
from dnd.domain.values.damage import (
    DamageInstance,
    DamageMultiplier,
    apply_damage_multiplier,
    combine_multipliers,
)
from dnd.domain.values.death_save_state import DeathSaveState
from dnd.domain.values.hit_points import HitPoints
from dnd.domain.values.vision import NORMAL_VISION, Vision
from dnd.domain.values.weapon import WeaponProfile

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


@dataclass(frozen=True, slots=True)
class DeathSaveOutcome:
    """Результат одного спасброска от смерти (для публикации события)."""

    result: Literal["success", "failure", "recovered"]
    successes: int
    failures: int
    d20_raw: int


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

    proficiency_bonus: int = 2
    """Бонус мастерства (PHB-2024 стр. 32: +2 на уровнях 1–4, +3 на
    5–8, +4 на 9–12, +5 на 13–16, +6 на 17–20). Применяется ко всем
    атакам и проверкам, в которых существо обучено.

    По умолчанию +2 — это уровень 1; для монстров PHB MM указывает
    конкретный бонус. Используется helper'ом
    :func:`equipped_weapon_attack_params`.
    """

    equipped_weapon: WeaponProfile | None = None
    """Экипированное оружие. Используется AI и UI для построения
    ``AttackParams`` (см. ``application/engine/actions/attack.py``).

    None означает «безоружный»; AI должен либо взять UNARMED_STRIKE,
    либо пропустить атаку. На MVP — без полноценного инвентаря, оружие
    задаётся при создании существа.
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

    uses_death_saves: bool = False
    """True у персонажей игроков и важных NPC: при 0 HP уходят в спасброски
    от смерти (PHB-2024 стр. 27), а не умирают мгновенно. NPC-расходники —
    False (default): при 0 HP их превращает в труп (CORPSE) Encounter."""

    death_saves: DeathSaveState | None = None
    """Не None ⟺ существо в dying (0 HP, ещё не мёртв и не поднят). Ставится
    через begin_dying(); сбрасывается в None при лечении/нат-20. Инвариант
    синхронизируется с HitPoints и Condition Unconscious."""

    spellcasting_ability: Ability | None = None
    """Заклинательная характеристика (INT/WIS/CHA). None — не-кастер (P1).
    От неё считаются spell attack bonus и save DC (PHB-2024 стр. 233)."""

    spell_slots: dict[int, int] = field(default_factory=dict)
    """Ячейки заклинаний: level → осталось. Заговоры (level 0) безлимитны и
    в словаре не хранятся. Упрощённая модель P1 — без классовой таблицы
    (она появится на этапе R). Mutable dict: расходуется при касте."""

    known_spells: tuple[SpellId, ...] = ()
    """ID известных существу заклинаний (разрешаются в Spell через
    SpellRepository). Из них BattleScreen строит action-bar (P1-10)."""

    ability_ids: tuple[AbilityId, ...] = (
        AbilityId("weapon_attack"),
        AbilityId("dodge"),
        AbilityId("dash"),
        AbilityId("disengage"),
        AbilityId("interact"),
        AbilityId("break_object"),
    )
    """Доступные существу умения (id'ы, разрешаются в Ability через
    AbilityRegistry). Default — 6 базовых, синхронизирован с
    register_default_abilities (L2-3). Per-creature override — через
    Creature.create(..., ability_ids=...) или прямую сборку поля; этап
    L2 ещё не подключает это к AI/чарактер-фабрикам, только готовит
    инфраструктуру."""

    keybindings: dict[str, AbilityId] = field(default_factory=dict)
    """Пользовательский override hotkey'я → ability id. Пусто = используем
    Ability.default_hotkey. Заполняется через настройки (L2 — только
    модель; UI для редактирования — отдельный этап). Mutable dict
    допустим: dataclass(slots=True) не frozen, поле менять можно."""

    inventory: Inventory = field(default_factory=Inventory)
    """Рюкзак существа. Default — пустой без лимитов (для упрощения
    тестов и legacy-сетапа). При создании PC через сценарий или
    monster-фабрику сюда кладётся стартовый набор. Этап O-7 будет
    лутать содержимое с трупов через InteractAction."""

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
        proficiency_bonus: int = 2,
        equipped_weapon: WeaponProfile | None = None,
        inventory: Inventory | None = None,
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
        if proficiency_bonus < 2 or proficiency_bonus > 6:
            raise ValueError(
                f"proficiency_bonus must be 2..6 (PHB-2024 стр. 32), "
                f"got {proficiency_bonus}"
            )
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
            proficiency_bonus=proficiency_bonus,
            equipped_weapon=equipped_weapon,
            inventory=inventory if inventory is not None else Inventory(),
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

        # Q-1: спасброски от смерти (PHB-2024 стр. 27). Только для тех, кто
        # uses_death_saves; NPC просто становятся not is_alive.
        if self.uses_death_saves:
            if killed_outright:
                # Огромный урон — мгновенная смерть, минуя спасброски.
                self.death_saves = DeathSaveState(failures=3)
            elif not was_alive and self.death_saves is not None:
                # Удар по уже лежачему (был 0 HP до удара): провал, крит → 2.
                self.death_saves = self.death_saves.apply_damage_at_zero(
                    is_critical=is_critical
                )

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
        revived = was_at_zero and not self.is_at_zero_hp
        # Q-1: лечение поднимает из dying в сознание — сброс DeathSaveState
        # и снятие Unconscious (PHB-2024 стр. 27).
        if revived and self.death_saves is not None:
            self.death_saves = None
            self.remove_condition(UNCONSCIOUS)
        return HealResult(
            raw_amount=amount,
            final_amount=final,
            revived=revived,
        )

    # --- dying / спасброски от смерти ----------------------------------

    def begin_dying(self) -> bool:
        """Войти в состояние умирания. Вызывает Encounter при падении в 0 HP.

        Возвращает True, если переход состоялся (PC при 0 HP, ещё не dying).
        Накладывает Unconscious. Для NPC (uses_death_saves=False) — no-op.
        """
        if not self.uses_death_saves:
            return False
        if not self.is_at_zero_hp:
            return False
        if self.death_saves is not None:
            return False
        self.death_saves = DeathSaveState()
        self.apply_condition(UNCONSCIOUS)
        return True

    def roll_death_save(self, d20_raw: int) -> DeathSaveOutcome:
        """Применить бросок спасброска от смерти. ``d20_raw`` — сырое d20.

        Нат-20 → восстановление 1 HP и выход из dying. Иначе делегирует в
        DeathSaveState; result определяется по тому, вырос успех или провал.
        """
        if self.death_saves is None:
            raise ValueError("roll_death_save called on a creature not dying")
        if d20_raw == 20:
            self.hit_points = self.hit_points.heal(1)
            self.death_saves = None
            self.remove_condition(UNCONSCIOUS)
            return DeathSaveOutcome(
                result="recovered", successes=0, failures=0, d20_raw=20
            )
        before = self.death_saves
        self.death_saves = before.apply_save_roll(d20_raw)
        result: Literal["success", "failure"] = (
            "success"
            if self.death_saves.successes > before.successes
            else "failure"
        )
        return DeathSaveOutcome(
            result=result,
            successes=self.death_saves.successes,
            failures=self.death_saves.failures,
            d20_raw=d20_raw,
        )

    @property
    def is_dead(self) -> bool:
        """Окончательно мёртв (3 провала). Только для uses_death_saves; NPC
        «мертвы» через is_alive=False + CORPSE (решает Encounter)."""
        return (
            self.uses_death_saves
            and self.death_saves is not None
            and self.death_saves.is_dead
        )

    # --- spellcasting (P1) ---------------------------------------------

    def spell_attack_bonus(self) -> int:
        """Бонус атаки заклинанием = proficiency_bonus + mod(заклинательной
        характеристики). ValueError, если существо не кастер."""
        if self.spellcasting_ability is None:
            raise ValueError(f"{self.id} is not a spellcaster")
        return self.proficiency_bonus + self.abilities.modifier(self.spellcasting_ability)

    def spell_save_dc(self) -> int:
        """Сл. спасброска от заклинаний = 8 + proficiency_bonus + mod
        (PHB-2024 стр. 233). ValueError, если не кастер."""
        if self.spellcasting_ability is None:
            raise ValueError(f"{self.id} is not a spellcaster")
        return 8 + self.proficiency_bonus + self.abilities.modifier(self.spellcasting_ability)

    def has_spell_slot(self, level: int) -> bool:
        """Есть ли ячейка нужного уровня. Заговор (level 0) — всегда True."""
        if level == 0:
            return True
        return self.spell_slots.get(level, 0) > 0

    def consume_spell_slot(self, level: int) -> None:
        """Потратить ячейку. Заговор — no-op. ValueError, если ячеек нет."""
        if level == 0:
            return
        if self.spell_slots.get(level, 0) <= 0:
            raise ValueError(f"no spell slot of level {level} for {self.id}")
        self.spell_slots[level] -= 1

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

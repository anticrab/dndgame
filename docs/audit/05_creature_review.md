# Audit 05: Creature vs book rules

Независимый ревью игровой механики D&D 5e (2024) применительно к
`Creature` и сопутствующим VO. Дата: 2026-05-21. Ревьюер: внешний.

Источники правды:
- «Книга Игрока 2024» (русский перевод), стр. 26-27 («Урон и лечение»,
  «Сопротивление и Уязвимость», «Огромный урон», «Падение до 0 хитов»,
  «Временные хиты»); стр. 352-353 в Глоссарии правил («Истощённый»,
  «Концентрация»). NB: указанная в брифе стр. 31 содержит «Создание
  персонажа», а определение истощения переехало из главы в глоссарий.
- `src/dnd/domain/entities/creature.py`, `src/dnd/domain/values/{hit_points,death_save_state,damage}.py`,
  `tests/unit/domain/test_creature.py`, `tests/unit/domain/test_death_save_state.py`,
  `tests/unit/domain/test_hit_points.py`, `tests/unit/domain/test_damage.py`.
- `docs/DESIGN.md` §2.5, §4.7, §5.1; `docs/OPEN_QUESTIONS.md` Q24-Q35.

## Резюме

- Расхождений с правилами книги: **5** (S0=1, S1=2, S2=2).
- Тонких багов в логике: **2** (CR-002, CR-006).
- Пропущенных edge cases в тестах: **4** (CR-004, CR-008, CR-009, CR-010).
- Архитектурных замечаний: **3** (CR-001, CR-003, CR-011).
- Документация/комментарии: **1** (CR-012).

Главная находка — **CR-001**: тип `concentration: ConditionId | None` не
соответствует ни смыслу понятия (концентрация — это удерживаемое
**заклинание**, не Condition), ни ADR Q27 (там зафиксировано
`ConcentrationState` с `spell_id`). Это «тихая» архитектурная мина,
которая взорвётся при первом же добавлении заклинания концентрации.

---

## Найденные проблемы

### CR-001. Тип `Creature.concentration` — `ConditionId`, а должен быть `SpellId`/`ConcentrationState`

**Серьёзность:** S0
**Книга:** стр. 352, глоссарий «Концентрация»: «Некоторые заклинания
и другие эффекты требуют концентрации, чтобы оставаться активными».
Концентрация — это удерживаемое **заклинание**, не отдельное Condition.
**Код:** `src/dnd/domain/entities/creature.py:138-140`, `creature.py:266`.

```python
concentration: ConditionId | None = None
"""ID заклинания концентрации, которое поддерживает существо."""
```

**Проблема.** Тип лжёт о смысле поля. Реальное содержимое — «ID
заклинания», но аннотация — `ConditionId`. На уровне `NewType` (см.
`application/dto/ids.py`) `ConditionId` и `SpellId` — разные типы,
именно для того, чтобы их нельзя было путать. Тест
`test_concentration_broken_signal_when_damage_arrived` присваивает
`ConditionId("bless")` — но `bless` это заклинание, не состояние.

Кроме того, ADR Q27 (`docs/OPEN_QUESTIONS.md:339-353`) явно говорит:
«В Creature будет поле `concentration: ConcentrationState | None`,
где ConcentrationState хранит `spell_id`, `applied_modifiers`».
Текущая реализация — даже не упрощённый вариант, а **другой** тип.

**Рекомендация.**
1. Заменить `concentration: ConditionId | None` на `concentration: SpellId | None`
   как минимум (ConcentrationState можно отложить до первого
   concentration-заклинания, но `SpellId` уже сейчас).
2. Поправить тесты `test_concentration_broken_signal_when_damage_arrived`
   и `test_concentration_not_broken_by_zero_damage` — использовать
   `SpellId("bless")`.
3. Привести docstring поля и комментарий в `take_damage` в порядок:
   убрать упоминание Condition.

---

### CR-002. Концентрация **не** прерывается автоматически при падении в 0 HP

**Серьёзность:** S1
**Книга:** стр. 352, глоссарий «Концентрация»: «**Состояние
Бессознательный или смерть.** Ваша концентрация заканчивается, если
вы получаете состояние бессознательный или умираете.»
**Код:** `src/dnd/domain/entities/creature.py:210-275`.

**Проблема.** `Creature.take_damage` ставит `concentration_broken=True`
только при `final > 0`. Но он:

* не очищает `self.concentration = None` ни в каком случае (даже когда
  ставит флаг);
* не отрабатывает специальный случай «existing concentration → 0 HP»,
  где по книге концентрация заканчивается **гарантированно**, без
  спасброска.

Дополнительно: семантика флага `concentration_broken` спутана. Сейчас
он означает «надо сделать CON-save» (комментарий
`creature.py:262-263`). Но при падении в 0 HP save **не нужен** —
концентрация просто заканчивается. Вызывающий слой (Encounter) из
текущего DamageResult не отличит «нужен save DC=X» от «прервалось
автоматически».

**Рекомендация.** Либо:
(а) добавить в `DamageResult` отдельное поле
`concentration_ended_automatically: bool` для случая `was_lethal=True`
с concentration!=None, плюс прямо в `take_damage` очищать
`self.concentration = None` в этом случае;
(б) переименовать `concentration_broken` → `concentration_check_required`
с DC, а отдельным флагом отражать «закончилась без save».

Также — добавить тест:
`test_concentration_ends_when_dropped_to_zero` (раз сам код этого не
делает — в тестах это даже не зафиксировано как known limitation).

---

### CR-003. Верхняя граница DC для concentration save (≤30) пропущена в формуле и в DESIGN

**Серьёзность:** S1
**Книга:** стр. 352, глоссарий «Концентрация»: «Сл. проверки равна 10
или половине полученного урона (округляется в меньшую сторону), в
зависимости от того, какое число больше, **но не более Сл. 30**.»
**Код:** `src/dnd/domain/entities/creature.py:24,231,262`; формула
тиражируется в комментариях и docstring.
**Документация:** `docs/DESIGN.md:165-167` («DC = max(10, damage //
2)»), `docs/DESIGN.md:304-306` (та же формула в §4.7), `OPEN_QUESTIONS.md:346`
(«CON-save DC = max(10, damage // 2)»).

**Проблема.** Все эти места указывают `DC = max(10, damage // 2)`,
**без** верхней границы 30. Сейчас Creature ничего не считает (только
флаг), но формула живёт в комментариях как «правильная» и попадёт в
будущий код Encounter/DiceRoller.

**Рекомендация.**
1. Поправить комментарий в `creature.py:24, 231, 262` на
   `min(30, max(10, damage // 2))` с явной ссылкой «Книга 2024 стр.
   352, глоссарий „Концентрация“».
2. Поправить `DESIGN.md` §2.5 (`165-167`) и §4.7 (`304-306`).
3. Поправить `OPEN_QUESTIONS.md:346`.

При появлении первого concentration-заклинания — формулу прокидывать
из этой константы, а не переписывать на местах.

---

### CR-004. Урон ровно в `maximum` при `was_lethal` НЕ считается «огромным» — соответствует книге, но граница «массивности» в книге дана через ≥, а в тестах — отсутствует

**Серьёзность:** S2
**Книга:** стр. 27 «Огромный урон»: «персонаж умирает, если оставшийся
урон **равен или превышает** его максимальный запас хитов».
Сценарий из книги: max=12, current=6, damage=18. Оставшийся = 18-6 = 12,
12 равен max(12) → смерть.
**Код:** `src/dnd/domain/entities/creature.py:259-260`. Условие
`overflow >= self.hit_points.maximum` — корректно.

**Проблема.** Сама формула верна; **расхождения нет**. Замечание
**в тесте** `test_exact_max_damage_does_not_trigger_outright`
(`test_creature.py:245-251`) — здесь max=14, current=14, damage=14.
overflow = 14-14 = 0 → ОК, не massive. Это правильный тест.

Но **отсутствует** именно «книжный» сценарий: max=12, current=6
(уже частично ранен), damage=18 → overflow=12, 12>=12 → killed_outright.
Сейчас все «massive»-тесты на полностью здоровом существе.

**Рекомендация.** Добавить тест:
```python
def test_book_scenario_massive_damage_when_partially_wounded():
    """Книга стр. 27: max=12, current=6, ловит 18 → overflow 12 >= max → outright."""
    c = make_creature(max_hp=12)
    c.take_damage(DamageInstance(6, DamageType.SLASHING))  # current=6
    res = c.take_damage(DamageInstance(18, DamageType.SLASHING))
    assert res.killed_outright is True
    assert res.overflow == 12
```

---

### CR-005. `gain_temporary_hp` автоматически берёт `max(старые, новые)` — книга оставляет выбор игроку

**Серьёзность:** S2
**Книга:** стр. 27 «Они не суммируются»: «Если у вас уже есть
временные хиты и вы получаете новые, то **вы можете** оставить
старые или взять новые, но не 22» (выбор игрока).
**Код:** `src/dnd/domain/values/hit_points.py:98-113`, `creature.py:298-305`.

```python
temporary=max(self.temporary, amount)
```

**Проблема.** Решение «брать больший буфер» — безопасный дефолт, но
жёсткое в коде. Книга оставляет выбор игроку: для некоторых эффектов
важно сбросить старые (например, новые имеют другой источник или
другую длительность). Сам автор VO это пометил TODO в комментарии
(`hit_points.py:106`: «В будущем можно сделать prefer_new-параметр»).

**Рекомендация.** Не блокер для MVP, но добавить параметр
`prefer: Literal["larger","new","old"] = "larger"` и пробрасывать его
через `Creature.gain_temporary_hp`. Сейчас зафиксировать как известное
упрощение в `DESIGN.md` §2.5 — иначе при появлении первого PC-класса
с temp HP (Barbarian, Fiend Warlock) код придётся менять и тесты
ломать.

---

### CR-006. `was_lethal` неверно интерпретируется при наличии temp HP буфера, когда удар точно «опустошил» current

**Серьёзность:** S2
**Книга:** стр. 27 «Временные хиты»: «временные хиты — буфер ПЕРЕД
вашими настоящими хитами; они теряются первыми». Стр. 27 «Падение до
0 хитов»: триггерится по current=0.
**Код:** `src/dnd/domain/entities/creature.py:250-255`.

**Проблема.** `was_lethal = was_alive and not self.is_alive`.
`was_alive` = `current > 0`. Если у существа было `current=5, temp=10`
и пришёл удар `final=15` (поглощает temp 10, current 5 → 0), то
`was_alive=True, is_alive=False, was_lethal=True` — **правильно**.

Но если было `current=5, temp=10`, удар `final=10` (поглотил всё
temp, current=5 нетронут — реализация HitPoints разделяет temp и
current): после `take_damage(10)` будет `temp=0, current=5`. То есть
**не** прошёл насквозь. Это правильно (см. `HitPoints.take_damage`:
если `temporary>=amount`, current не страдает).

Edge case прошёл. **Расхождения нет**, но тест отсутствует.

**Рекомендация.** Это пометка-про-тесты, а не баг: добавить
`test_temp_hp_exact_match_keeps_current` и
`test_temp_hp_drained_then_lethal_through` (см. CR-008).

(Понизил CR-006 до S2, так как код корректен; помечаю для покрытия.)

---

### CR-007. `is_unconscious` называется так, но не соответствует Condition Unconscious из правил

**Серьёзность:** S2
**Книга:** стр. 27 «Потеря сознания»: «если ваши хиты опустились до
0, но вы не умерли мгновенно, вы получаете **состояние
Бессознательный**, пока не восстановите любое количество хитов».
Само Unconscious — Condition с эффектами (Incapacitated, лежит, провал
STR/DEX-saves, атаки в 5 фт — крит). См. также `docs/DESIGN.md:367`.
**Код:** `src/dnd/domain/entities/creature.py:196-199`, `hit_points.py:53-56`.

**Проблема.** `Creature.is_unconscious` означает `current==0` — это
**триггер** Condition Unconscious, но не **сам** Condition. У NPC
триггер ≠ Condition (NPC умирает мгновенно). У PC — нужно ещё
накладывать Condition Unconscious в `Character.conditions`. Имя
читателя сбивает: «is_unconscious» звучит как «состояние наложено».

**Рекомендация.** Переименовать в `is_at_zero_hp` или
`is_dropped_to_zero`. Это поможет отличить «HP=0 факт» от «Condition
Unconscious наложен». ConditionId(`unconscious`) при первом
implementation Condition-плагина никогда не путать с этим геттером.

Альтернатива — оставить имя, но добавить docstring в обоих местах
с явным разделением «HP-факт vs Condition» и ссылкой на §5.2 DESIGN.

---

### CR-008. Пропущенные edge cases в тестах: heal на мёртвом NPC (без death saves)

**Серьёзность:** S2
**Где:** `tests/unit/domain/test_creature.py`.

**Проблема.** `Creature.heal` поднимает с 0 HP, не зная, был ли NPC
«мгновенно мёртв» (Q26: NPC при 0 HP мёртв) или PC (DeathSaveState).
Это семантическое решение принимается на уровне `Character`/`Monster`
снаружи, но **внутри Creature** heal работает одинаково: «было 0 →
стало >0 → revived=True». Это **корректно** (Creature не знает про
PC vs NPC), но тест `test_heal_from_zero_marks_revived` проверяет
только revived-флаг. Сценарий «NPC truly dead но Creature всё ещё
оживает» зафиксирован только в комментарии Q26, и в коде Creature
выходит, что любое существо с current=0 — кандидат на воскрешение.

**Рекомендация.** Добавить тест-смог
`test_heal_revives_creature_unconditionally` с явным комментарием:
«семантика мёртв-навсегда — на уровне Character/Monster».

---

### CR-009. Пропущенный тест: `exhaustion` с `levels=0`

**Серьёзность:** S2
**Где:** `tests/unit/domain/test_creature.py`.

**Проблема.** `add_exhaustion(0)` и `remove_exhaustion(0)` — валидные
(`levels >= 0`). Они должны быть no-op. Тестом это не покрыто.

**Рекомендация.**
```python
def test_add_exhaustion_zero_is_noop():
    c = make_creature()
    assert c.add_exhaustion(0) == 0
def test_remove_exhaustion_zero_is_noop():
    c = make_creature()
    c.add_exhaustion(2)
    assert c.remove_exhaustion(0) == 2
```

---

### CR-010. Пропущенный тест: сопротивление **одного** типа + уязвимость **другого** (на одном существе)

**Серьёзность:** S2
**Где:** `tests/unit/domain/test_creature.py`.

**Проблема.** Покрыт случай «resist+vulnerable одного типа = NORMAL»
(хорошо). Не покрыт случай «существо с resist огнём + vulnerability
холодом»: удар огнём → halve, удар холодом → double. Это тривиально
работает, но **именно** такого теста нет.

**Рекомендация.**
```python
def test_resistance_and_vulnerability_apply_independently_per_type():
    c = make_creature(max_hp=40,
                     resistances=frozenset({DamageType.FIRE.value}),
                     vulnerabilities=frozenset({DamageType.COLD.value}))
    assert c.take_damage(DamageInstance(10, DamageType.FIRE)).final_amount == 5
    assert c.take_damage(DamageInstance(7, DamageType.COLD)).final_amount == 14
```

---

### CR-011. `apply_condition`: иммунитет проверяется ДО проверки «уже наложено» — корректно, но семантически расходится с книгой (без накопления, кроме истощения)

**Серьёзность:** S2
**Книга:** стр. 27 «Без накопления»: «Если на вас наложены несколько
эффектов, накладывающих одно и то же состояние, то **каждый эффект
имеет свою продолжительность, но эффект состояния не ухудшается**.
Либо вы находитесь под действием состояния, либо нет.»
**Код:** `src/dnd/domain/entities/creature.py:309-322`.

**Проблема.** Метод возвращает `False`, если состояние уже есть.
Это технически корректно (состояние не дублируется), **но**
вызывающий слой не отличит:

* «уже есть» (длительность нового источника надо бы где-то учесть);
* «иммунитет» (новый источник вообще не сработал).

В будущем при добавлении Condition-плагина с длительностью (например,
Frightened от двух разных источников) `apply_condition` должен
сохранять оба источника. Сейчас этого нет — `conditions: set[ConditionId]`
не различает источников.

**Рекомендация.** Это известное ограничение (трекер ↔ полноценный
ConditionRegistry, task #28). Зафиксировать как известное упрощение в
`DESIGN.md` §5 и в docstring метода (там сейчас «Полная логика — task
#28», но конкретно про длительности/источники — не сказано).

Добавить отдельный возврат-discriminator (например, `apply_condition`
возвращает Enum `ConditionApplyResult`: `APPLIED | ALREADY_HAD |
IMMUNE`) — даст вызывающему слою явные коды для логирования.

---

### CR-012. Документация: «book stub» в комментарии устаревший

**Серьёзность:** S2
**Где:** `src/dnd/domain/entities/creature.py:24` (docstring модуля),
`creature.py:230-240` (docstring `take_damage`).

**Проблема.** Комментарии содержат `DC = max(10, damage // 2)` без
верхней границы 30 (см. CR-003). Кроме того, в docstring модуля
сказано «6 уровней истощения, -2 ко всем d20» — корректно, но без
указания страницы книги (стр. 352, не стр. 31 как в брифе задачи).

**Рекомендация.** Поправить вместе с CR-003. Скорректировать ссылки на
страницы — «истощение: глоссарий правил, стр. 352».

---

## Что точно соответствует

1. **Сопротивление = floor(damage / 2)** — `apply_damage_multiplier`
   (`damage.py:85-86`, `// 2`). Книга стр. 26 «уменьшается вдвое
   (округляется в меньшую сторону)». ✓
2. **Уязвимость = ×2** — `damage.py:87-88`. Книга стр. 26. ✓
3. **Иммунитет = 0**, перекрывает всё остальное — `combine_multipliers`
   (`damage.py:108-110`). Книга стр. 26. ✓
4. **Resist + Vulnerable одного типа = NORMAL** — `damage.py:110-112`.
   Книга стр. 26 «Не складываются»: «множества… считаются одним».
   Корректное прочтение: один из источников гасит другой. ✓
5. **Временные хиты не складываются** — `HitPoints.with_temporary` берёт
   `max` (`hit_points.py:111-113`). Книга стр. 27. ✓ (но см. CR-005 о
   выборе игрока).
6. **Лишний урон по temp HP переносится на current** —
   `HitPoints.take_damage` (`hit_points.py:82-84`). Книга стр. 27
   «временные хиты теряются первыми; …получив 7 урона, теряете эти
   хиты, а затем 2 обычных». ✓
7. **Лечение не выше максимума** — `HitPoints.heal` (`hit_points.py:92-93`,
   `min(maximum, ...)`). Книга стр. 26. ✓
8. **Огромный урон = overflow ≥ maximum → instant death** —
   `Creature.take_damage` (`creature.py:259-260`). Книга стр. 27
   «равен или превышает». ✓
9. **DeathSaveState: 10+ = успех, <10 = провал, нат-20 = recovery, нат-1
   = 2 fails** — `apply_save_roll` (`death_save_state.py:74-104`). Книга
   стр. 27. ✓
10. **DeathSaveState: урон при 0 HP — провал; крит — 2 провала** —
    `apply_damage_at_zero` (`death_save_state.py:106-119`). Книга стр.
    27. ✓
11. **3 успеха → stable, 3 провала → death** — `is_dead` / `is_stable`
    (`death_save_state.py:65-70`). Книга стр. 27. ✓
12. **Stabilized сохраняет накопленные счётчики** —
    `stabilized()` (`death_save_state.py:121-130`). Совпадает с тестом
    `test_stabilized_preserves_counters`. Книга стр. 27 «успехи и
    провалы сбрасываются до нуля, когда вы восстанавливаете хиты или
    стабилизируетесь» — формулировка двусмысленна; принятая интерпретация
    («stable хранит снимок») — разумна.
13. **Истощение 6 = смерть** — `is_exhaustion_lethal` (`creature.py:355-358`).
    Книга стр. 352. ✓
14. **При снижении максимума ниже current — current тоже снижается** —
    `HitPoints.with_maximum` (`hit_points.py:115-123`). Книга стр. 26 «эффекты,
    истощающие жизненную энергию, уменьшают максимум хитов существа». ✓
15. **Стабилизация Медициной DC 10** — формулировка в DESIGN
    (`DESIGN.md:142-143`). Реализуется выше Creature (Encounter +
    Medicine-check). Книга стр. 27. ✓

---

## Сводный TODO по приоритетам

### S0 (блокеры)

- **CR-001** Сменить тип `Creature.concentration` с `ConditionId | None` на
  `SpellId | None` (или ConcentrationState | None, как зафиксировано в Q27).
  Поправить два теста.

### S1 (важные)

- **CR-002** В `take_damage` при `was_lethal=True` + `concentration is not None`:
  очищать `self.concentration = None` и сообщать через отдельное поле
  `DamageResult.concentration_ended_automatically: bool`. Без CON-save —
  книга прерывает напрямую.
- **CR-003** Поправить формулу DC concentration save во всех 5 местах:
  `min(30, max(10, damage // 2))`. Указать ссылку «стр. 352, глоссарий
  „Концентрация“».

### S2 (улучшения)

- **CR-004** Добавить тест «массивный урон при частичном ранении».
- **CR-005** Параметризовать выбор temp HP (`prefer="larger" | "new" | "old"`).
- **CR-006** Покрыть edge case «temp HP buffer exact match» и
  «temp+current прорыв насквозь» тестами.
- **CR-007** Переименовать `is_unconscious` → `is_at_zero_hp` (или
  расширить docstring).
- **CR-008** Тест: heal на мёртвом NPC оживляет (Creature не различает
  PC/NPC).
- **CR-009** Тесты `add_exhaustion(0)` / `remove_exhaustion(0)` — noop.
- **CR-010** Тест: resist одного типа + vulnerable другого — раздельная
  работа.
- **CR-011** Возврат discriminator-enum из `apply_condition`
  (`APPLIED|ALREADY_HAD|IMMUNE`).
- **CR-012** Поправить страницы книги в docstring (истощение — стр.
  352, не 31).

---

## Особо отмечено

- **`is_critical` параметр в `Creature.take_damage`** — игнорируется.
  Это **правильно**: на уровне Creature урон уже удвоен DiceRoller-ом
  заранее (книга стр. 26 «бросьте кости урона дважды»). Параметр носится
  для `Character`, чтобы при `was_lethal=True` `is_critical=True`
  поставить **2** провала death-save вместо 1 (книга стр. 27 «крит на
  бессознательном — два провала»). См. `creature.py:238-241` — комментарий
  это объясняет корректно.

- **`take_damage(amount=0)` с активной концентрацией.** В коде
  `concentration_broken = self.concentration is not None and final > 0`.
  Урон 0 (иммунитет либо изначально 0) не срывает концентрацию — это
  **соответствует** правилу. Тест `test_concentration_not_broken_by_zero_damage`
  это покрывает. ✓

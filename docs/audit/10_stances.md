# Audit 10: Stance Actions (E4) — Dodge / Dash / Disengage

Независимый ревью этапа E4:

- `src/dnd/application/engine/actions/stances.py`
- `tests/unit/application/actions/test_stances.py`
- (затронуто) `src/dnd/application/engine/actions/attack.py` — интеграция
  Dodge → disadvantage цели (строки 270, 287).
- (затронуто) `src/dnd/domain/entities/creature.py` — поле
  `combat_stances: set[str]` (строки 181-190).

Источники правды:

- `docs/ACTIONS.md` §2 (Action protocol), §6 (жизненный цикл «без
  двойной валидации»), §8 (план E4).
- `docs/MODIFIERS.md` §2.4 (`HasCondition`, специфы), §2.5 (`UntilEndOfNextTurn`).
- «Книга Игрока 2024»: стр. 22 (Dodge — атаки с помехой и DEX-save с
  advantage; Dash — доп. движение = скорости; Disengage — нет AoO),
  стр. 367 (Incapacitated: нет actions/reactions/bonus actions).

Дата: 2026-05-21. Ревьюер: внешний.

Запуск: `pytest tests/unit/application/actions/test_stances.py -v` —
**25 passed**.

Не оценивалось (по запросу): Cunning Action Плута, очистка
`combat_stances` в `Encounter` (этап F).

---

## 1. Краткое резюме

Реализация компактна (≈200 строк на три экшна) и точно следует
`Action Protocol` из `ACTIONS.md` §2: метаданные через `ClassVar`,
`can_perform` без побочных эффектов, `execute` тратит экономию и
мутирует контекст ровно один раз. Общая шапка блокеров вынесена в
`_check_action_blockers` — нет повторов из `AttackAction._BLOCKING_CONDITIONS`
по семантике, но фактически они дублируют один и тот же `frozenset`
(MOD `ST-A001` ниже).

Главные риски:

- **ST-R001 (S1):** Dodge не «выключается», если actor стал
  `Incapacitated` или его `speed_ft == 0` **между** Dodge и атакой
  врага. PHB-2024 стр. 22 явно: «Стойка прекращается, если ты
  Incapacitated или твоя скорость падает до 0». Сейчас
  `AttackAction.execute` читает `target.combat_stances` без оглядки
  на состояние цели.
- **ST-R002 (S1, помечено пост-MVP):** Dodge не даёт advantage на
  DEX-saves (отложено до `SavingThrowAction`). В коде это **явный
  TODO** в docstring stances.py:13 — приемлемо при условии, что есть
  follow-up задача; в `OPEN_QUESTIONS.md` её нет — стоит зафиксировать.
- **ST-A001 (S2):** дублирование набора блокирующих conditions
  (`_ACTION_BLOCKERS` в stances.py и `_BLOCKING_CONDITIONS` в
  attack.py) — оба `frozenset({INCAPACITATED, STUNNED, PARALYZED, UNCONSCIOUS})`.
  Один источник правды напрашивается (`conditions/builtin.py:ACTION_BLOCKERS`).
- **ST-A002 (S2):** AttackAction знает строковый литерал `"dodging"`
  (attack.py:270) — coupling в обход enum. Комментарий это объясняет
  («чтобы action attack не зависел от модуля stances»), но решение
  спорное: enum мог жить в `domain/values/combat_stance.py` без
  application-зависимости. См. §2.
- **ST-G001 (S1):** нет теста на сценарий «actor под Dodge → получает
  Stunned → атака пробивается без disadvantage». См. §4.

---

## 2. Архитектура

### 2.1 S0

Не обнаружено.

### 2.2 S1

#### ST-A003 (S1) — `combat_stances: set[str]` в `Creature` нарушает «closed enum»

`Creature.combat_stances` — `set[str]`, значения декларируются в
`application/engine/actions/stances.CombatStance` (StrEnum). Контракт
держится только комментарием в `creature.py:188`. Это:

1. **обход типизации:** в `combat_stances` можно положить произвольную
   строку и никто не упадёт (mypy/pyright тоже — `str` шире, чем
   `Literal["dodging","dashing","disengaged"]`);
2. **создаёт перекрёстную зависимость** «domain читает строки,
   определённые в application»: чтобы понять, какие значения валидны,
   нужно открыть `application/engine/actions/stances.py` — это
   разворачивает стрелку зависимости из `ARCHITECTURE.md` в обратную
   сторону;
3. **открывает дрейф:** опечатка `"dodgign"` в новом коде не приведёт
   к ошибке тестов, тихо станет неактивной стойкой.

**Компромисс приемлем для MVP**, но решение должно быть зафиксировано
ADR. Чище — `domain/values/combat_stance.py` с `StrEnum` (или
`Literal`), `combat_stances: set[CombatStance]` в `Creature`. Аргумент
«domain не должен импортировать enum action-уровня» снимается
переносом enum в `domain/values/`.

#### ST-A002 (S1, повтор) — coupling AttackAction → строка `"dodging"`

`attack.py:270`:

```python
dodge_penalty = "dodging" in target.combat_stances
```

Тот же риск, что и в ST-A003: опечатка не пойдёт в типчек. Если в
будущем добавится `CombatStance.DODGING_HEAVY` или ребрендинг —
поиск по подстроке `"dodging"` промахнётся. Минимум — импорт
`from ...stances import CombatStance` и сравнение с
`CombatStance.DODGING.value`. Аргумент «attack не должен зависеть от
stances» аналогично снимается переносом enum в domain.

### 2.3 S2

#### ST-A001 (S2) — дублирование `_ACTION_BLOCKERS` ↔ `_BLOCKING_CONDITIONS`

`stances.py:46-48` и `attack.py:69-71` объявляют один и тот же
`frozenset({INCAPACITATED, STUNNED, PARALYZED, UNCONSCIOUS})`. Если
завтра добавим `PETRIFIED` (PHB-2024 стр. 368, тоже implies
Incapacitated) — придётся править в двух местах и можно забыть.
Вынести в `domain/conditions/builtin.py`:

```python
ACTION_BLOCKING_CONDITIONS: Final = frozenset(
    {INCAPACITATED, STUNNED, PARALYZED, UNCONSCIOUS}
)
```

#### ST-A004 (S2) — `DashAction.execute` не помечает «что бюджет уже выдан»

Docstring класса `DashAction` обещает, что повторный Dash (Cunning
Action в будущем) прибавит speed_ft ещё раз — это правильно по
правилам. Но текущая запись `combat_stances.add("dashing")` — это
**set**: повторное добавление не отличить от первого. Если когда-то
понадобится узнать «сколько раз использован Dash в ход» — set не
поможет. Это не баг сегодня, но проектное ограничение: stance-маркер
≠ счётчик. Стоит документировать (одной строкой), что `dashing` —
**идемпотентный** маркер, не «счётчик использований».

#### ST-A005 (S2) — `DashAction` пропускает запрет при `speed_ft == 0`

`can_perform` опирается на `_ACTION_BLOCKERS` (Paralyzed/Stunned
выставят speed=0 косвенно — через свои эффекты). Но **прямого**
условия `speed_ft > 0` нет. Если в будущем появится эффект
`grappled`-подобный, понижающий speed без conditions из блокеров,
Dash будет «работает», выдавая +0 ft. Поведенчески безвредно (просто
ничего не добавит), но pad`er контракт: лучше отдельный
`Forbidden(reason=NOT_ENOUGH_MOVEMENT)` (или новый `SPEED_IS_ZERO`).

---

## 3. Правила «Книга Игрока 2024»

### 3.1 S0

Не обнаружено.

### 3.2 S1

#### ST-R001 (S1) — Dodge не прекращается, если actor стал Incapacitated/speed=0

**PHB-2024 стр. 22, Dodge**: «Стойка прекращается, если ты
Incapacitated или твоя скорость падает до 0».

Сейчас `DodgeAction.execute` ставит `"dodging"` в `combat_stances` и
никогда не сверяется с состоянием actor'а при атаке по нему. Если
between Dodge → атака враг наложил `Stunned` (через
`apply_condition`), `target.combat_stances` всё ещё содержит
`"dodging"`, и `AttackAction.execute` навешивает disadvantage. Это
**нарушение правила**: stun снимает Dodge.

Корректный путь:

```python
# attack.py — место, где читается dodge:
dodge_active = (
    "dodging" in target.combat_stances
    and not any(target.has_condition(c) for c in INCAPACITATED_FAMILY)
    and target.speed_ft > 0  # или эффективная скорость через ModifierApplier
)
```

Альтернатива в духе MODIFIERS.md — выразить Dodge как `Modifier` с
`condition = And(HasFlag("dodging"), Not(HasCondition("incapacitated")), SpeedGreaterThan(0))`
и `target = AttackRollTarget` с эффектом `DisadvantageEffect` на
атаки **по** owner'у. Это требует расширений `ModifierTarget`
(сейчас `AttackRollTarget` про *attacker*, а нужно «атаки против
этого существа»). Пометить как S1: правило явно есть в книге, и без
него «прятался под Dodge — превратили в камень — атаки всё равно с
помехой» — заметный баг.

#### ST-R002 (S1, частично обоснованно) — Dodge не даёт DEX-save advantage

**PHB-2024 стр. 22, Dodge**: «Когда ты делаешь Спасбросок Ловкости,
ты получаешь Преимущество на этот бросок».

В stances.py:13 это **честно помечено** как «после реализации
SavingThrowAction (вне MVP)». Сам пропуск приемлем, но:

1. в `docs/ROADMAP.md` / `OPEN_QUESTIONS.md` не нашлось явной TODO-ссылки;
2. нет «отрицательного» теста, который зафиксировал бы текущее
   поведение («сегодня Dodge DEX-save advantage не даёт») — без него
   риск, что реализующий SavingThrowAction агент забудет дёрнуть
   `target.combat_stances`.

**Рекомендация:** добавить запись в `OPEN_QUESTIONS.md` и тест-фиксатор
с `xfail(reason="ST-R002, post-MVP")`.

### 3.3 S2

#### ST-R003 (S2) — Dodge требует «ты видишь атакующего»

**PHB-2024 стр. 22:** «Любой бросок атаки против тебя имеет помеху,
если ты видишь атакующего». В `attack.py:266-269` есть комментарий
«на MVP считаем выполненной (LoS уже проверен и симметричен)». Это
оправдано, **но**:

- LoS симметричен на текущем `Battlefield`, но `Blinded` (или
  магическая темнота) выключает «видишь атакующего» при сохранённом
  LoS у атакующего;
- в книге это явно отдельное условие, не следствие LoS.

Когда появится `BlindedCondition` / VisibilitySystem — потребуется
проверка `not target.has_condition(BLINDED)` (или через
`condition_service`). Пометить как S2 — на MVP не критично.

#### ST-R004 (S2) — Disengage не помечен в DocString как «только для своего движения»

`DisengageAction` ставит `ctx.disengaged = True` до конца хода. По
правилам это корректно: «до конца этого хода твоё движение не
провоцирует opportunity attacks». В коде `MoveAction` действительно
читает флаг (move.py:190). Но docstring `DisengageAction` не уточняет,
что флаг **per-turn** (не действует на чужие движения этого actor'а
вне хода — например, принудительные перемещения телекинезом). На MVP
это теоретическая возможность, но стоит уточнить — пост-MVP грэплы /
push-эффекты обнажат вопрос.

---

## 4. Пропущенные тесты

### ST-G001 (S1) — нет теста «Dodge гасится Incapacitated/speed=0»

Сценарий, описанный в ST-R001. Минимальный набор:

```python
@pytest.mark.rules
def test_dodge_disabled_when_target_incapacitated() -> None:
    # actor Dodge → потом получает Stunned → атака пробивается без disadvantage
    ...

@pytest.mark.rules
def test_dodge_disabled_when_target_speed_zero() -> None:
    # actor с speed_ft=0 → DodgeAction.execute допустимо отказать,
    # либо attack по такому target — без disadvantage.
    ...
```

Сейчас оба сценария **не покрыты ни одним тестом**. Из-за ST-R001
они и не пройдут.

### ST-G002 (S2) — нет теста «Dash при speed_ft=0 даёт +0 ft»

Параметризованный assertion на `DashAction.execute` с `speed=0`. Тест
не страшный, но фиксирует поведение (ST-A005).

### ST-G003 (S2) — нет теста «двойной Dash в ход прибавляет speed дважды»

Docstring `DashAction` явно обещает поддержку Cunning Action (через
bonus action в будущем): «Допускается дважды за ход … каждое
разрешение прибавляет speed_ft ещё раз». Без теста-симулятора
(`Dash + Dash → movement_remaining_ft == speed*3` с начальной = speed)
это лишь обещание в комментариях.

### ST-G004 (S2) — нет теста «DodgeAction не даёт advantage самой атаке actor'а»

Семантический negative-test: actor Dodge, потом атакует кого-то — у
**его** атаки не должно быть advantage/disadvantage из-за Dodge.
Сейчас невозможно ошибиться (Dodge ничего не пишет в actor's
attack_roll), но один регрессионный тест фиксирует контракт.

### ST-G005 (S2) — нет теста «Disengage не отменяет AoO от движений в **следующем** ходу»

Уже частично за пределами E4 (очистка флага — этап F), но
`ctx.disengaged` живёт по контексту хода. Тест уровня
`DisengageAction → next-turn TurnContext (новый) → не disengaged`
закрепит контракт.

---

## 5. Сводный TODO

### S0

- (пусто)

### S1

- [ ] **ST-R001** — реализовать «Dodge заканчивается при Incapacitated /
      speed=0». Минимальный путь: в `attack.py` обернуть `dodge_penalty`
      проверкой `_BLOCKING_CONDITIONS` на цель + `target.speed_ft > 0`.
      Долгий путь — перенести в `ModifierApplier` через `condition`-предикат.
- [ ] **ST-R002** — зафиксировать пост-MVP TODO в `OPEN_QUESTIONS.md` /
      `ROADMAP.md`: «Dodge → DEX-save advantage реализуется при
      `SavingThrowAction`». Добавить `xfail`-тест.
- [ ] **ST-A002 / ST-A003** — решить (ADR): переносим ли `CombatStance`
      в `domain/values/` и типизируем ли `combat_stances` как
      `set[CombatStance]`. Сейчас два места знают строковый литерал
      `"dodging"` без типчека.
- [ ] **ST-G001** — добавить два теста (Stunned-target и speed=0-target),
      проверяющие, что атака идёт без disadvantage.

### S2

- [ ] **ST-A001** — вынести `ACTION_BLOCKING_CONDITIONS` в
      `domain/conditions/builtin.py`. Использовать его в
      `stances._ACTION_BLOCKERS` и `attack._BLOCKING_CONDITIONS`.
- [ ] **ST-A004** — уточнить в docstring `DashAction`, что `"dashing"` —
      идемпотентный маркер, не счётчик использований.
- [ ] **ST-A005** — добавить явный отказ Dash при `speed_ft == 0` или
      хотя бы зафиксировать поведение тестом ST-G002.
- [ ] **ST-R003** — TODO-комментарий в `attack.py:266-269`: «при появлении
      `BLINDED` уточнить проверку видения атакующего».
- [ ] **ST-R004** — уточнить в docstring `DisengageAction`, что флаг
      действует только на *собственное* движение actor'а в этом ходу.
- [ ] **ST-G002 / ST-G003 / ST-G004 / ST-G005** — четыре регрессионных
      теста (см. §4).

---

**Итог:** этап E4 закрыт по букве `ACTIONS.md` §2/§6, тесты зелёные
(25/25), но скрыт один S1-баг правил (ST-R001) и один открытый S1-вопрос
типизации `combat_stances` (ST-A003). После их закрытия — этап готов
как фундамент под E5 (Help/Search) и F (Encounter, который очистит
`combat_stances` на старте хода).

---

## Применённые фиксы (2026-05-21)

**S1 — закрыто:**

* **ST-R001** — Dodge-стойка теперь гасится, если у цели любое из
  Incapacitated/Stunned/Paralyzed/Unconscious (PHB-2024 стр. 22:
  «benefit ends if you are Incapacitated or your Speed drops to 0»).
  Helper `_dodge_suppressed(target)` в `attack.py`; параметризованный
  тест `test_dodge_suppressed_when_target_incapacitated` × 4 condition.

**Отложено (S1/S2):**

- **ST-R002** — DEX-save advantage от Dodge. Помечено как «реализуется
  после SavingThrowAction»; добавление xfail-теста-якоря — отдельная
  задача.
- **ST-A002 / ST-A003** — `combat_stances: set[str]` → enum.
  Требует переноса `CombatStance` в `domain/values/`; план — после
  Encounter (этап F), когда станет понятным контракт между domain и
  application для очистки stances.

**Цифры:** test_stances.py: 29 passed (+4); общее 605 passed.

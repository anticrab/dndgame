# Audit 08: AttackAction (E2)

Независимый ревью **кода и тестов** этапа E2 — `AttackAction`:

- `src/dnd/application/engine/actions/attack.py`
- `src/dnd/application/dto/engine_event.py` (подклассы `AttackRolled`,
  `DamageDealt`, `AttackResolved`)
- `src/dnd/application/engine/turn_context.py` (новое поле
  `participants`)
- `tests/unit/application/actions/test_attack_action.py`

Источники правды:

- `docs/ACTIONS.md` §2 (Action protocol), §4 (Availability), §5
  (Outcome — «расписка»), §6 (жизненный цикл «без двойной валидации»).
- `docs/ENGINE.md` §4 (Action как Command), §5.2 (EventBus FIFO),
  §7.4 (двухфазная модель бросков).
- `docs/MODIFIERS.md` §2.2 / §6.1 (как Action собирает модификаторы
  через `ModifierApplier`).
- `docs/VISIBILITY.md` §3 (cover/LoS на этапе атаки).
- «Книга Игрока 2024»: стр. 23–24 (Chebyshev, размещение),
  стр. 25 (Совершение атаки, КД, natural 20 / 1, удвоение кубов,
  укрытие, ranged за нормальной дистанцией → disadvantage),
  стр. 367 (Incapacitated и его implies: Stunned / Paralyzed /
  Unconscious).

Дата: 2026-05-21. Ревьюер: внешний.

Запуск: `pytest tests/unit/application/actions/test_attack_action.py -v`
— **22 passed**.

---

## 1. Краткое резюме

Дизайн совпадает с `ACTIONS.md`: `can_perform` без побочных эффектов,
двухуровневая проверка (`can_perform` глобально + `can_perform_against`
по конкретной цели), `execute` тратит экономику и публикует события
ровно один раз, `ActionOutcome` — лаконичная расписка без дублирования
содержимого событий. Контракт `EngineEvent` соблюдён: новые подклассы
frozen + `extra="forbid"`. Двухфазная модель бросков из ENGINE.md §7.4
не нарушается — `DiceRoller.roll` сам публикует `RollIssued/RollApplied`,
а `AttackRolled` идёт **после** них, как и заявлено комментарием в
`engine_event.py`.

Главные риски:

- **AT-R001 (S0):** при ненулевом `numeric_bonus` от модификаторов
  урона `execute` падает с `DiceParseError` (ветка
  `DiceExpr.parse(f"{params.damage_expr}{dmg_adj.numeric_bonus:+d}")`
  собирает выражение с двумя модификаторами — `_PATTERN` это не
  парсит). Все 22 теста проходят, потому что используют пустой
  `ModifierBag`. Это бьёт по любой ситуации «+1 магическое оружие»
  или «Sneak Attack mod 0»; «нога в гранату» для первого же реального
  персонажа.
- **AT-A001 (S1):** между `can_perform_against` и `execute` нет
  страховки на стороне `execute` — если контракт нарушится, мы либо
  получим `KeyError` (нет цели в participants), либо «уже мёртвую»
  цель примет урон. Это не противоречит ACTIONS.md §6 («никаких
  двойных вычислений»), но единственный тест-симулятор «нарушения
  контракта» отсутствует (тест `test_execute_rejects_wrong_params_type`
  страхует только типизацию). См. также AT-G002.
- **AT-G001 (S1):** ни одного теста на «концентрация цели → CON-save
  DC проброшен в `AttackResolved.concentration_save_dc`», хотя ветка
  реализована и поле в DTO документировано. Регрессия не будет
  поймана.

Дальше — поэлементный разбор.

---

## 2. Архитектурные находки

### AT-A001. `execute` молча падает, если контракт нарушен после `can_perform_against`
**Тип:** architecture / contract
**Серьёзность:** S1
**Где:** `attack.py:191-195`

```python
target = ctx.participants[params.target_id]
attacker_pos = ctx.battlefield.position_of(actor.id)
target_pos   = ctx.battlefield.position_of(target.id)
cover        = ctx.battlefield.cover_against(attacker_pos, target_pos)
```

ACTIONS.md §6 явно говорит, что вызывающий обязан вызвать
`can_perform_against` (или эквивалент) **до** `execute`. Это правильно
для архитектуры. Но `execute` не страхует себя `assert`-инвариантами и
не пишет в комментарий, что произойдёт при нарушении (`KeyError` /
`ValueError` от Battlefield). При интеграции с MonsterAI это станет
ловушкой.

Минимум — в docstring к `execute` явно записать: «контрактная ошибка,
если params.target_id не в participants / target не на карте». Опция —
сделать `target = ctx.participants.get(...)`, и при `None` поднять
`RuntimeError("contract violation: can_perform_against was not called")`.
Это **не** валидация правила, это страховка вызывающего.

### AT-A002. `_BLOCKING_CONDITIONS` дублирует знание из `ConditionRegistry.implies`
**Тип:** architecture / DRY
**Серьёзность:** S2
**Где:** `attack.py:68-70`

В `ConditionRegistry` Stunned / Paralyzed / Unconscious имеют
`implies = {INCAPACITATED}` (и Prone). `ConditionService.apply_with_implies`
накладывает Incapacitated автоматически. Тогда `_BLOCKING_CONDITIONS`
по правилам книги можно свести к одному `INCAPACITATED`: если каскад
применён, проверка `has_condition(INCAPACITATED)` достаточна.

Текущий код избыточен — но не **некорректен**, потому что тесты
накладывают условия напрямую `Creature.apply_condition` (без implies),
и без перечисления stunned/paralyzed/unconscious проверка бы не
сработала. Это «hardening» против неправильного использования, но
ценой того, что любое будущее блокирующее состояние (Petrified, Sleep
по 2024) надо будет руками добавлять в эту константу.

Рекомендация: перейти на `actor.has_condition(INCAPACITATED)` **при
условии**, что в Encounter все Conditions накладываются через
`ConditionService`. Зафиксировать это инвариантом теста-симулятора.

### AT-A003. `AttackResolved` не сообщает `final_amount` и не различает «downed» vs «killed_outright»
**Тип:** architecture / contract
**Серьёзность:** S2
**Где:** `engine_event.py:122-137`

`AttackResolved` несёт `downed: bool`, но не `killed_outright` (PHB-2024
стр. 27 «Огромный урон»: overflow >= maximum → мгновенная смерть NPC и
автопровал death save для PC). `Creature.take_damage` уже возвращает
`DamageResult.killed_outright`, и эта семантика теряется на уровне
события — а это именно то, что нужно журналу/UI/ИИ («труп уже не
встанет»).

Симметрично, `DamageDealt.final_amount` есть, но `AttackResolved` —
финальное событие — его не дублирует. UI/AI вынужден держать связь
по `attack_roll_id` между DamageDealt и AttackResolved. Это решаемо,
но в текущей модели «AttackResolved — итог атаки» странно, что итог
не содержит суммарного урона.

Рекомендация: добавить `killed_outright: bool = False` и
`damage_final: int = 0` в `AttackResolved`. Это эволюция DTO без
ломающих изменений (defaults пустые).

### AT-A004. `AttackParams` использует `int` для `attack_bonus`, не RollAdjustments
**Тип:** architecture / contract
**Серьёзность:** S2
**Где:** `attack.py:91, 214`

```python
attack_bonus: int = Field(ge=-20, le=30)
...
total_atk_bonus = params.attack_bonus + atk_adj.numeric_bonus
```

`attack_bonus` — это **уже** сумма proficiency + ability_mod + расовых
и т.п. Если позже система ModifierBag научится их выдавать (а не
получать на вход), `AttackParams.attack_bonus` станет нулём и весь
смысл — в модификаторах. Сейчас это **двойной канал**: часть бонуса
сидит в params, часть — в ModifierBag. Для MVP это нормально, но
комментарий («параметры приходят готовыми; связь с инвентарём — этап
персонажа») должен явно говорить: «attack_bonus покрывает proficiency
+ ability_mod, а ModifierBag — ситуативные модификаторы (Bless, etc)».
Без этого через год никто не вспомнит, где проф. бонус.

### AT-A005. `economy_cost_value` как ClassVar используется только сам в себе
**Тип:** architecture / style
**Серьёзность:** S2
**Где:** `attack.py:104-116`

```python
economy_cost_value: Final = ActionEconomyCost.ACTION

@property
def economy_cost(self) -> ActionEconomyCost:
    return self.economy_cost_value
```

ClassVar и property через неё — типичный признак, что хочется наследовать
с переопределением. Но `AttackAction` единственный класс, и план E3-E6
показывает, что у каждого Action будет свой `economy_cost` (Action,
BonusAction для off-hand, Reaction для OA). Тогда правильнее — просто
константа `economy_cost: ClassVar[ActionEconomyCost] = ACTION`. Сейчас
паттерн ничего не упрощает, но добавляет два уровня индирекции
(constant + property).

Это `bad smell`, не баг. Низкий приоритет.

---

## 3. Расхождения с книгой

### AT-R001. `execute` падает при ненулевом numeric_bonus к урону
**Тип:** rules / runtime-bug
**Серьёзность:** **S0**
**Где:** `attack.py:269-275`

```python
base_expr = DiceExpr.parse(params.damage_expr)
full_expr = (
    base_expr if dmg_adj.numeric_bonus == 0
    else DiceExpr.parse(
        f"{params.damage_expr}{dmg_adj.numeric_bonus:+d}"
    )
)
```

`params.damage_expr` обычно уже содержит модификатор (`"1d8+3"` для
длинного меча с STR=16). Конкатенация с `+2` от модификатора даёт
`"1d8+3+2"`, что `DiceExpr._PATTERN` не парсит (он позволяет ровно
один опциональный `[+-]\s*\d+`). Доказано в репле:

```
>>> DiceExpr.parse("1d8+3+2")
DiceParseError: cannot parse dice expression: '1d8+3+2'
```

Все 22 теста проходят, потому что используют пустой `ModifierBag`,
и `dmg_adj.numeric_bonus` всегда 0. Это совершенно реальная ситуация
для любого магического оружия (+1, +2, +3), любого Bless-like
«+N к урону» эффекта.

PHB-2024 стр. 26 (Урон): «бонусы к броску урона прибавляются к итогу».
Книга на синтаксис кубовой строки не намекает — но движок обязан
поддержать сложение модификаторов.

Минимальное исправление: считать сумму модификатора отдельно, не через
конкатенацию строк. Например:

```python
base_expr = DiceExpr.parse(params.damage_expr)
extra_numeric = dmg_adj.numeric_bonus
# DiceExpr хранит modifier как int; собрать новый можно через replace
combined = replace(base_expr, modifier=base_expr.modifier + extra_numeric)
```

Либо отнести +N к `extra_dice` в `RollContext` — но это меняет
семантику крита (модификатор не удваивается, а если положить в
extra_dice — ComputerDiceRoller бросает с `crit=ctx.crit`, и
константный +N всё равно не удвоится, потому что это modifier, а
не roll; но **проверить**). Самый прямой путь — пересобрать `DiceExpr`
через `dataclasses.replace`.

Юнит-тест на сценарий «+1 магический меч» обязателен.

### AT-R002. На крите не удваивается **второй** инстанс кубов урона
**Тип:** rules / coverage
**Серьёзность:** S1
**Где:** `attack.py:265-289`

Книга 2024 стр. 25 «Критическое попадание»: «броски всех костей урона
атаки удваиваются». Это **включает** доп. кости (Sneak Attack 2d6,
Divine Smite 2d8, Hex 1d6 от заклинания) — все они удваиваются на
крите.

В реализации: `DiceBonusEffect` модификатора урона попадает в
`dmg_adj.extra_dice` → `RollContext.extra_dice` → `ComputerDiceRoller`
бросает каждую с `crit=ctx.crit`. Это **корректно** (см. явный
комментарий в dice_roller.py:62-68).

Однако:
- Юнит-тест отсутствует. Сценарий «крит + extra_dice=1d6» не покрыт.
- Если кто-то завтра поправит DiceRoller и забудет про крит для
  extra_dice, никто не узнает.

Тест на «Sneak Attack 1d6 на крите даёт 2d6 в extra_dice_rolls»
обязателен.

### AT-R003. Cover при `LowCover` (HALF) не покрыт ни одним тестом
**Тип:** rules / coverage
**Серьёзность:** S1
**Где:** тесты, `test_execute_cover_adds_to_effective_ac`

Есть тест на THREE_QUARTERS (HIGH_COVER, +5), но не на HALF (+2).
Книга PHB-2024 стр. 25 явно различает: half cover (+2 к КД и спас.
ЛОВ), three-quarters cover (+5), total cover (нельзя выбрать).
`CoverLevel.HALF.ac_bonus == 2` — это контракт `terrain.py`, и
аудит #07 уже отметил, что зона ответственности правильная. Но на
уровне AttackAction именно half-cover-путь не зафиксирован.

Тест: атакующий за LOW_COVER между → effective_ac = AC + 2,
попадание/промах проверены по конкретным значениям d20.

### AT-R004. Self-target не запрещён
**Тип:** rules / edge-case
**Серьёзность:** S2
**Где:** `attack.py:140-176`

`can_perform_against` не проверяет `params.target_id == actor.id`.
В книге явного запрета атаковать себя нет (есть для casting на себя
по правилам spell), но для **weapon attack** это бессмыслица: dist=0,
melee reach=5 → пройдёт, LoS True, cover NONE. Получим self-урон.

Не критично для MVP (UI не даст), но для AI и для замены UI это
крайний случай, который стоит закрыть `Forbidden(NO_VALID_TARGETS)`
или новой причиной `INVALID_TARGET`.

### AT-R005. Дистанция считается через `distance_to_feet` (Chebyshev) — корректно, но без явного теста
**Тип:** rules / coverage
**Серьёзность:** S2

PHB-2024 стр. 23-24 + ADR-0002: Chebyshev, 1 клетка = 5 фут.
`Square.distance_to_feet` это и делает. AttackAction вызывает его
правильно. Однако тесты на range проверяют только «слишком далеко по
оси X» (Square(0,0) → Square(2,0) для melee; Square(0,0) → Square(9,0)
для long range). Сценарий «диагональ — это тоже 5 фут на клетку»
(Square(0,0) → Square(1,1) для melee reach=5 OK, Square(0,0) →
Square(2,2) для melee reach=5 = OUT_OF_RANGE) не проверен — это
типичная ловушка для перехода на «1-2-1» в будущем.

---

## 4. Пропущенные тесты

### AT-G001. Нет теста на ветку `concentration_save_dc` в `AttackResolved`
**Серьёзность:** S1

`Creature.take_damage` возвращает `concentration_save_dc` для цели с
активной концентрацией. AttackAction прокидывает его в
`AttackResolved.concentration_save_dc`. Но тест на это отсутствует —
ни в `test_execute_lethal_damage_marks_downed` (там цель умирает,
`save_dc=None`), ни в обычных hit-тестах (там у Goblin нет
концентрации). Регрессия (например, забыли передать поле) не будет
поймана.

Сценарий: цель с `concentration = SpellId("bless")`, hit → damage 6 →
ожидаем `concentration_save_dc == max(10, 6//2) == 10` и **`downed=False`**.

### AT-G002. Нет «тест-симулятора», что `execute` не валидирует повторно
**Серьёзность:** S1

ACTIONS.md §6 явно требует: «всё, что прошло `can_perform`, выполняется
в `execute` без повторной проверки». Это контракт. Тест-симулятор —
вызвать `execute` напрямую, **минуя** `can_perform_against`, в условиях,
которые `can_perform` бы запретил (например, цель в total cover). По
текущему коду:

- цель есть в `participants` → `[params.target_id]` не падает;
- battlefield считает cover TOTAL → `effective_ac += 0` (TOTAL даёт
  `ac_bonus=0`), но **атака всё равно идёт**.

Это технически правильно по контракту, но **должно быть зафиксировано
тестом**: «execute не делает повторных запретов, потому что вызывающий
обязан был проверить can_perform_against». Без него легко скатиться к
«страховке через if» внутри execute.

### AT-G003. Нет теста на advantage от ModifierBag
**Серьёзность:** S2

Долговая нотация: реализация `attack.py:200-223` собирает модификаторы
с `ATTACK_ROLL` target_kind и применяет advantage / disadvantage /
numeric_bonus / extra_dice. Тесты проверяют только long-range
disadvantage (S1 покрытие), но не модификаторный путь. Сценарий:
`ModifierBag` с `AdvantageEffect` от Bless-like эффекта, два d20 в
RNG → берётся больший. **Это путь, через который тысяча будущих
заклинаний работает** — а он не покрыт.

### AT-G004. Нет теста, что `RollIssued` / `RollApplied` идут в порядке `…, RollIssued, RollApplied, AttackRolled, …`
**Серьёзность:** S2

ENGINE.md §5.2 FIFO + §7.4 двухфазная модель + комментарий в
`engine_event.py:69-83` явно описывают порядок:
`RollIssued → RollApplied → AttackRolled → (для damage аналогично) → DamageDealt → AttackResolved`.

`test_execute_hit_publishes_three_events_in_order` фильтрует события
по типу AttackRolled/DamageDealt/AttackResolved и проверяет только
их порядок. **Полная FIFO-цепочка** не проверена — это значит, если
в реализации однажды publish AttackRolled случайно произойдёт ДО
RollApplied, никто не узнает. А это нарушение контракта ENGINE.md §7.4.

Тест: captured-список, проверить полную последовательность типов.

### AT-G005. Нет теста на resistance / vulnerability / immunity цели
**Серьёзность:** S2

`Creature.take_damage` применяет resistant ×½ / vulnerable ×2 / immune
×0 (`damage.py:68-90`). AttackAction передаёт `DamageInstance` в
`take_damage`, и `DamageDealt.final_amount` отражает финал. Но в
текущих тестах у Goblin пустые `resistances/vulnerabilities/immunities`.

Книга PHB-2024 стр. 26 — это правило центральное. Тест с
`resistances={"slashing"}` → final_amount == raw_amount // 2 — must-have.

### AT-G006. Нет теста на участие `participants` при изменённом ID
**Серьёзность:** S2

`turn_context.py:61` добавлено поле `participants`. Тесты используют
participants только через `_setup`, где attacker и target положены
заранее. Не проверено: что если в `participants` есть третья сторона
— атака её не задевает; что если в `participants` стоит мёртвая
цель (HP=0) — атака **проходит** (`AttackAction` не запрещает атаку
по 0-HP цели, и это **сознательно**, потому что book допускает coup
de grace).

### AT-G007. Нет теста на критическое попадание + долгая дистанция (disadvantage)
**Серьёзность:** S2

Граничный случай: ranged за long-range disadvantage с natural-20.
В книге стр. 25: при disadvantage берём **меньший** d20. Если меньший
== 20 (т.е. **оба** d20 — 20), это natural-20 и крит. Если меньший
== 1 (т.е. **оба** d20 — 1), это natural-1 / автомисс.
`d20_raw` правильно смотрит в `kept` (после выбора большего/меньшего).
Но регрессия (например, кто-то начнёт читать `raw[0]`) не будет
поймана.

### AT-G008. `test_against_total_cover_forbidden` строит «странную» геометрию
**Серьёзность:** S2 (smell, не bug)

```python
ctx.battlefield.set_terrain(Square(3, 0), WALL)
# Цель стоит на клетке-стене (нестандартно, но движок должен это
# отлавливать): cover_against → TOTAL.
```

В `Battlefield.place_creature` есть проверка `not terrain.passable`
→ ValueError. Но в фикстуре цель размещается **до** установки WALL,
поэтому проверка не срабатывает. Тест читается как «специально
ставим невалидное состояние». Реалистичнее: атакующий за WALL **между**
им и целью — это и есть «total cover между» (а не «цель на стене»).
В `Battlefield.cover_against` уже есть тестируемая ветка «WALL между»
(аудит #07 TR-G001 жалуется на её отсутствие; этот тест её **не**
покрывает, потому что WALL стоит на клетке цели).

Лучше переписать: WALL на Square(2, 0), attacker (0,0), target (3,0)
— `cover_against` должна вернуть TOTAL, но при этом LoS тоже False
(`line_of_sight` блокирует). Какая Forbidden причина выиграет? По
текущему коду — `NO_LINE_OF_SIGHT` (потому что проверка LoS идёт
раньше). Это сценарий, который реально встречается в игре, и его
поведение должно быть зафиксировано тестом.

---

## 5. Сводный TODO по приоритету

| ID | Тип | S | Описание | Действие |
|---|---|---|---|---|
| **AT-R001** | rules | **S0** | DiceParseError при ненулевом numeric_bonus к урону | Пересобирать DiceExpr через `dataclasses.replace(modifier=…)`, не конкатенацией строк. Юнит-тест «+1 магический меч». |
| **AT-A001** | arch | S1 | execute не страхует контракт | docstring + опционально RuntimeError при missing target |
| **AT-R002** | rules | S1 | крит + extra_dice не покрыт тестом | Тест: Sneak Attack 1d6 → 2d6 в extra_dice_rolls на крите |
| **AT-R003** | rules | S1 | half cover (+2) не покрыт тестом | Тест: LOW_COVER → effective_ac == AC + 2 |
| **AT-G001** | gap | S1 | concentration_save_dc не покрыт | Тест с `target.concentration` |
| **AT-G002** | gap | S1 | нет тест-симулятора контракта can_perform/execute | Тест: вызвать execute без can_perform_against (для cover/LoS/range) |
| **AT-A002** | arch | S2 | дублирование implies в _BLOCKING_CONDITIONS | После Encounter — свести к INCAPACITATED + инвариант ConditionService |
| **AT-A003** | arch | S2 | AttackResolved без killed_outright и damage_final | Расширить DTO с defaults |
| **AT-A004** | arch | S2 | attack_bonus как часть params + ModifierBag — двойной канал | docstring c явным разделением ответственности |
| **AT-A005** | arch | S2 | economy_cost через ClassVar+property — мёртвая абстракция | Свести к простому ClassVar |
| **AT-R004** | rules | S2 | self-target не запрещён | Forbidden(NO_VALID_TARGETS) если target_id == actor.id |
| **AT-R005** | rules | S2 | диагональная дистанция не проверена | Тест Square(0,0) → Square(2,2) for melee → OUT_OF_RANGE |
| **AT-G003** | gap | S2 | advantage через ModifierBag не покрыт | Тест с `Modifier(effect=AdvantageEffect, target=ATTACK_ROLL)` |
| **AT-G004** | gap | S2 | FIFO порядок Roll* + Attack* не проверен полностью | Тест: вся последовательность типов captured |
| **AT-G005** | gap | S2 | resistance/vulnerability/immunity цели не покрыты | Тест с `target.resistances={"slashing"}` |
| **AT-G006** | gap | S2 | поведение при мёртвой цели и третьей стороне в participants | Тест coup de grace по 0-HP цели; тест с 3 существами |
| **AT-G007** | gap | S2 | crit + long-range disadvantage не покрыт | Тест с двумя d20=20 на ranged long range |
| **AT-G008** | gap | S2 | test_against_total_cover_forbidden ставит «странную» сцену | Переделать на WALL между, проверить приоритет LoS vs cover |

**Что закрыть до этапа E3 (Move):**

- **AT-R001** — обязательно, это runtime-краш с реальным контентом.
- **AT-A001**, **AT-R002**, **AT-R003**, **AT-G001**, **AT-G002** —
  желательно: они закрывают контракт `AttackAction` и переиспользуются
  в OpportunityAttack (E6).

**Что можно отложить до интеграции с Character/Encounter:** AT-A002,
AT-A003, AT-A004, AT-R004, AT-R005.

**Что — поправки качества тестов:** AT-A005, AT-G003-G008.

---

## 6. Применённые фиксы (2026-05-21)

**S0 — закрыто:**

* **AT-R001** — fix в `AttackAction.execute`: пересборка `DiceExpr` через
  `dataclasses.replace(base, modifier=base.modifier + adj.numeric_bonus)`
  вместо строковой конкатенации, которая ломалась при ненулевом
  numeric_bonus. Покрыто тестом
  `test_execute_magic_weapon_plus_1_damage_does_not_crash`.

**S1 — закрыто:**

* **AT-A001** — `execute` теперь явно бросает `RuntimeError` с
  сообщением «contract violation», если `target_id` отсутствует в
  `participants`. Поведение задокументировано в docstring `execute`.
  Тест: `test_execute_raises_when_target_not_in_participants`.
* **AT-R002** — добавлен тест `test_critical_hit_doubles_extra_dice`:
  natural-20 + extra_dice="1d6" → 2d6 в результирующем броске урона.
* **AT-R003** — добавлен тест `test_half_cover_adds_2_to_effective_ac`
  на LOW_COVER → effective_ac = AC + 2.
* **AT-G001** — добавлен тест `test_concentration_save_dc_propagated_when_hit`:
  target с `concentration = SpellId("bless")` → `AttackResolved.concentration_save_dc == 10`.
* **AT-G002** — добавлены два теста-симулятора контракта:
  `test_execute_does_not_re_validate_after_can_perform` (атака идёт
  «как есть» при появлении WALL между after-can_perform) и
  `test_execute_raises_when_target_not_in_participants`.

**S2 — закрыто полезное:**

* **AT-A004** — расширен docstring `AttackParams` с явным разделением
  ответственности «attack_bonus / damage_expr — статика оружия;
  ситуативные модификаторы — через ModifierApplier».
* **AT-A005** — `AttackAction` метаданные (id, name_key, economy_cost)
  переведены на `ClassVar`-константы; одна понятная индирекция.
* **AT-G004** — `test_full_event_fifo_order_on_hit`: полная цепочка
  типов событий зафиксирована (RollIssued → RollApplied → AttackRolled
  → RollIssued → RollApplied → DamageDealt → AttackResolved).
* **AT-G005** — два теста: `test_target_resistance_halves_damage` и
  `test_target_immunity_zeroes_damage`.

**S2 — отложено (войдёт в дальнейшие этапы):**

* AT-A002 — свести `_BLOCKING_CONDITIONS` к одному `INCAPACITATED`
  после Encounter + инвариант `ConditionService`.
* AT-A003 — добавить `killed_outright`/`damage_final` в `AttackResolved`
  при расширении DamageResult.
* AT-R004 — self-target запрет, добавится при targeting policies.
* AT-R005 — тест на диагональную дистанцию (Square(0,0) → Square(2,2)).
* AT-G003, AT-G006, AT-G007, AT-G008 — добавятся при integration-тестах
  Encounter.

**Итоговые цифры:**

* pytest:   **537 passed** (+9 за фиксы)
* tests/unit/application/actions/test_attack_action.py: **31 passed** (+9)
* ruff:     All checks passed
* mypy:     Success: no issues found in 70 source files
* coverage: **98.18%**

**Реальная находка:** AT-R001 — runtime-краш на первом же магическом
оружии. Не пойман существующими тестами, потому что все они работали
с пустым `ModifierBag`. Поймало именно независимое ревью.

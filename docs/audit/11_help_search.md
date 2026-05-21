# Audit 11: Help / Search (E5)

Независимый ревью кода и тестов этапа E5 — `HelpAction` и `SearchAction`:

- `src/dnd/application/engine/actions/help_search.py`
- `tests/unit/application/actions/test_help_search.py`
- (затронуто) `src/dnd/application/engine/actions/attack.py` — чтение и
  сброс `actor.helped_against` (atk.py:274-276).
- (затронуто) `src/dnd/domain/entities/creature.py:171-179` — поле
  `helped_against: CreatureId | None`.
- (затронуто) `src/dnd/application/dto/engine_event.py:176-197` — события
  `HelpGranted`, `SearchPerformed`.

Источники правды:

- `docs/ACTIONS.md` §2 (Action protocol), §6 (жизненный цикл «без
  двойной валидации»).
- `docs/MODIFIERS.md` §1 / §2.3 (advantage как effect; ModifierTarget
  как семантическая категория; «правило не складывается»).
- «Книга Игрока 2024»:
  - стр. 22 (Help): «within 5 feet of the creature being attacked»,
    «if the target is no longer within 5 feet of you when the attack is
    made, you lose the benefit», вариант для ability check;
  - стр. 22 (Search): Wisdom (Perception) / Intelligence
    (Investigation), DC и эффект — на стороне сюжета.

Дата: 2026-05-21. Ревьюер: внешний.

Запуск: `pytest tests/unit/application/actions/test_help_search.py -v`
— **19 passed** за 0.12s.

---

## 1. Резюме

Контракт `ACTIONS.md §2/§6` соблюдён: `can_perform` без побочных
эффектов, отдельный `can_perform_against` для target-aware проверки,
`execute` один раз тратит экономику и публикует ровно одно
`HelpGranted` / `SearchPerformed`. Событийный DTO правильно frozen,
поля `event_type` объявлены `ClassVar[str]`. Все тесты зелёные.

Главные риски:

- **HS-R001 (S0):** правило PHB-2024 стр. 22 «if the target is no
  longer within 5 feet of you when the attack is made, you lose the
  benefit» — **не реализовано**. Helper, поставивший Help и затем
  отошедший от цели на 30 фут, всё равно даёт союзнику advantage.
  Проверка в `AttackAction.execute` отсутствует — поле
  `helped_against` читается без знания о позиции helper'а.
- **HS-A001 (S1):** Help выражен через ad-hoc поле в `Creature`,
  минуя `ModifierApplier`. Это короткий путь, но он создаёт
  параллельный канал управления advantage — теперь в коде атаки
  одновременно живут `atk_adj.advantage` (из модификаторов) и
  `help_bonus` (из креатуры), а в `RollContext.advantage` они
  объединяются через `or`. Та же двойная-канальная болезнь, что
  AT-A004 для `attack_bonus`. Тех-долг записать явно.
- **HS-A002 (S1):** `AttackAction.execute` напрямую мутирует
  `actor.helped_against = None`. Action не своего хозяина начинает
  редактировать сторонний фрагмент state — это cross-action coupling
  через side-effect. Если в будущем появится второй потребитель
  advantage-«одноразового маркера» (Faerie Fire, Reckless Attack),
  они будут наступать друг другу на ноги.
- **HS-G001 (S1):** нет теста на ability-check вариант Help (книжный
  вариант есть, в коде сознательно отложен); и нет теста на то, что
  «helper отошёл — преимущество не выдаётся» (тест отсутствует,
  потому что и правило не реализовано).

Дальше — поэлементный разбор.

---

## 2. Архитектура — находки

### HS-A001. Help как ad-hoc поле, а не модификатор
**Тип:** architecture / contract
**Серьёзность:** S1
**Где:** `creature.py:171`, `help_search.py:145`, `attack.py:274-276`

`MODIFIERS.md §2.3` явно вводит `AttackRollTarget(weapon_kind=...,
damage_type=...)` как канал «модификатор для атаки». Help — по сути
target-aware временный модификатор: «advantage на атаку, чей `target_id
== X`, длительность = первая атака owner'а, истекает в конце его
следующего хода».

Реализация в E5 пошла коротким путём:

```python
# help_search.py:145
ally.helped_against = params.target_id

# attack.py:274
help_bonus = actor.helped_against == target.id
if help_bonus:
    actor.helped_against = None
```

Это работает для MVP, но создаёт долг:

1. В `AttackAction.execute` появляется **второй источник advantage**
   рядом с `atk_adj.advantage` (из ModifierApplier). Они объединяются
   через `or`, что для одного флага корректно, но семантика «не
   складываем advantage» (`MODIFIERS.md §1, стр. 26: «не складываются»`)
   теперь распределена по двум источникам.
2. Нельзя выразить «два helper'а дали Help» (по правилам — overwrite,
   но в коде это «второй просто записал тот же target_id» — никакого
   диагностического сигнала).
3. Когда в постMVP появится Help-для-ability-check, появится **третье
   поле** в `Creature` (`helped_check_against`?) — или потребуется
   переписать сразу всё через модификатор.

**Рекомендация (S1):** оставить как есть для E5 и зафиксировать в
TODO/ADR: «после E6 рефакторинг Help на one-shot
`Modifier(effect=Advantage, target=AttackRollTarget,
condition=AgainstSpecificTarget(target_id), duration=OneAttackOrEndOfNextTurn)`,
снести поле `helped_against` из `Creature`». Сейчас — добавить
комментарий-маркер в коде и упомянуть в OPEN_QUESTIONS.

### HS-A002. `AttackAction.execute` мутирует чужое поле
**Тип:** architecture / coupling
**Серьёзность:** S1
**Где:** `attack.py:274-276`

```python
help_bonus = actor.helped_against == target.id
if help_bonus:
    actor.helped_against = None
```

`AttackAction` начинает редактировать state, который ему «положил»
другой Action. Это hidden side-effect: при чтении `AttackAction`
читатель не ожидает увидеть запись в `Creature.helped_against`.

Аналогичная пара `combat_stances` рядом (строка 270) тоже читается
из `target`, но **не мутируется** — это хороший пример. Help же —
плохой.

Альтернатива: «расход» one-shot записывает не `AttackAction`, а
`ModifierApplier.collect`, помечая модификатор как `consumed=True`
и удаляя его. Это требует HS-A001.

**Рекомендация (S1):** в текущей реализации **добавить тест-симулятор**
HS-G002 (см. ниже), который зафиксирует: после первой атаки owner'а
по target поле = None. И в комментарии `attack.py:272-277` явно
сказать, что это **временный механизм**, и в постMVP уходит в модификатор.

### HS-A003. `skill_mod: int` в `SearchParams` — параллельный канал к ModifierApplier
**Тип:** architecture / contract
**Серьёзность:** S2
**Где:** `help_search.py:179, 228`

```python
class SearchParams(ActionParams):
    skill_mod: int = Field(ge=-10, le=20)
...
expr = DiceExpr.parse(f"d20{params.skill_mod:+d}")
```

Точно та же ситуация, что аудит #08 описал в AT-A004 для
`attack_bonus`. `skill_mod` — статическая сумма (ability_mod +
proficiency), а ситуативные бонусы (Guidance +1d4, Help-for-check,
Owl-familiar Help, Bless-like) **должны** идти через
`ModifierApplier.collect(AbilityCheckTarget(ability=WIS,
skill="perception"))`.

Сейчас `SearchAction.execute` модификаторы **не собирает вообще** —
бросок идёт «голым»: `DiceRoller.roll(d20+skill_mod, ABILITY_CHECK)`.
Это значит:

- Guidance не сработает,
- Exhaustion (-2 на всех d20 с уровня 1) не сработает,
- любой будущий «помеха на восприятие в шуме» не сработает.

**Рекомендация (S1 в перспективе):** записать как HS-A003 в долг,
дать ссылку на AT-A004 (одна и та же проблема). Минимум — `TODO` в
коде. Для тестов: ситуативные модификаторы у Search пока не
требуются, но при первом же реальном персонаже Guidance отвалится.

### HS-A004. `SearchAction.can_perform` есть, `can_perform_against` нет
**Тип:** architecture / consistency
**Серьёзность:** S2
**Где:** `help_search.py:202-213`

`SearchAction` не имеет `can_perform_against`. По формальному
контракту `ACTIONS.md §6` `execute` может звать UI без
`can_perform_against` — потому что у Search нет «цели». Это OK.

Но: оркестратор/UI должен знать, что Search **не требует** второй
проверки, и в Action-Protocol желательно иметь способ сказать «у
этого action нет target-aware ветки». Сейчас отсутствие метода —
неявный контракт. Если оркестратор слепо вызывает
`getattr(action, "can_perform_against", None)`, проблем нет; если
полагается на наличие — обнаружит только в runtime.

**Рекомендация (S2):** в `ACTIONS.md §2` явно зафиксировать
«action без target-аргумента не определяет `can_perform_against`» —
это уже сделано для DodgeAction/DashAction, но стоит свести в
табличку. Не код-фикс.

### HS-A005. `Encounter` обещан сбрасывать `helped_against` — Encounter ещё нет
**Тип:** architecture / lifecycle
**Серьёзность:** S2
**Где:** `creature.py:176-178`

В docstring `helped_against`:

> Также Encounter сбросит на старте следующего хода owner'а
> (если не использовал).

`Encounter` в кодовой базе **ещё не существует** (`find src -name
'*encounter*'` → пусто). Это значит, если ally не использует помощь
до конца своего хода, поле останется на нём бесконечно (или пока
другой Help его не перезапишет).

Тест на «Help не используется → следующий ход всё равно с advantage»
покажет дефект. Сейчас такого теста нет.

**Рекомендация (S2):** добавить в roadmap-задачу E-Encounter явный
пункт «сбрасывать `helped_against` на старте хода owner'а» (это уже
обещано в docstring, но не закреплено в `ROADMAP.md`).

---

## 3. Правила («Книга Игрока 2024») — находки

### HS-R001. «Helper отошёл — преимущество теряется» не проверяется
**Тип:** rules / missing check
**Серьёзность:** S0
**Где:** `attack.py:272-277`, всё help_search.py

PHB-2024 стр. 22 (Help → Assist an Attack):

> «If the target is no longer within 5 feet of you when the attack is
> made, the ally doesn't gain the benefit.»

В коде реализована только проверка на старте Help'а
(`HelpAction.can_perform_against`, строки 121-124). Но между
`HelpAction.execute` и атакой ally может пройти ход target'а
(target отошёл) и/или helper отбежал. В момент `AttackAction.execute`
позиция helper'а **не проверяется**.

Воспроизведение:

```
T1: Helper(1,1) ставит Help на ally→target. helped_against=target.
T2: Helper(1,1) перемещается в (10,10) (Dash).
T3: Ally атакует target → AttackAction читает helped_against ==
    target.id → advantage. По правилу — НЕ должно быть advantage.
```

Архитектурно правило требует знать `helper_id`. Сейчас в
`helped_against: CreatureId | None` хранится только target — забыли
о helper'е. Чтобы реализовать правило, нужно либо:

- хранить пару `helped_against: tuple[CreatureId, CreatureId] | None`
  (target, helper) и в `AttackAction.execute` проверять
  `battlefield.distance(helper, target) <= 5`;
- или (правильнее) переехать на модификатор с `ModifierCondition`
  («helper в 5 фт от target прямо сейчас»), см. HS-A001.

**Рекомендация (S0):** минимум — расширить поле до `(target,
helper)` и добавить проверку дистанции в начале `AttackAction.execute`.
Тест HS-G003 обязателен.

### HS-R002. Help для ability check не реализован
**Тип:** rules / coverage
**Серьёзность:** S2 (по условию «postMVP не оценивать», но
зафиксировать долг)
**Где:** `help_search.py:71-75`

PHB-2024 стр. 22 разделяет: Help-for-attack и Help-for-ability-check
(«ally has advantage on the next ability check it makes to perform the
task»). Реализация делает только первый вариант. Это **сознательно**
(docstring это говорит), но:

- DTO `HelpGranted` ничего не сообщает, какой вариант — будущий
  Help-for-check заведёт второй тип события или поле `mode`;
- `HelpParams` имеет только `target_id` (creature), а для check
  нужен «task_id» или «activity_kind».

**Рекомендация (S2):** добавить ADR/OPEN_QUESTIONS «Help: только attack
в MVP; для check — после E-Skills, потребует ModifierTarget=AbilityCheck
с одноразовым consume». Не код-фикс на E5.

### HS-R003. Несколько Help-источников: overwrite без сигнала
**Тип:** rules / behaviour
**Серьёзность:** S2
**Где:** `help_search.py:145`

```python
ally.helped_against = params.target_id
```

Если ally уже имеет `helped_against=monsterA`, и второй helper
помогает против `monsterB`, **просто перезаписывается**. По правилам
2024 («Advantage не складывается») второй Help должен либо:

- быть запрещён («ally уже получил Help в этом раунде»);
- быть разрешён, но **не суммироваться** (просто заменить цель —
  это текущее поведение).

PHB-2024 явно не говорит «нельзя получить Help дважды», поэтому
текущий overwrite — допустимая интерпретация. **Но он молчаливый**:
ни warning, ни лог. Сценарий-композитор не узнает.

**Рекомендация (S2):** оставить как есть, но опубликовать через
`HelpGranted` отдельное поле `replaced_previous: bool = False`, или
хотя бы добавить тест-фиксацию «второй Help перезаписывает первый,
поле = новый target».

### HS-R004. Search без модификаторов — Guidance/Exhaustion игнорируются
**Тип:** rules / coverage
**Серьёзность:** S1
**Где:** `help_search.py:226-234`

`SearchAction.execute` не вызывает `ModifierApplier.collect` —
бросок идёт `d20+skill_mod`. PHB-2024 стр. 13 (тесты способностей):
советы, Bless, помеха от Exhaustion, Guidance — все они влияют на
ability check. Сейчас они на Search не действуют.

Это та же тема, что HS-A003, но с другой стороны: HS-A003 говорит
о двойном канале, HS-R004 — о том, что **второй канал вообще не
подключён**.

**Рекомендация (S1):** добавить `ctx.modifier_applier.collect(
owner_id=actor.id, target_kind=ModifierTargetKind.ABILITY_CHECK)` (если
такого target_kind ещё нет — завести), применить `numeric_bonus`,
`extra_dice`, `advantage/disadvantage` к броску. Тест HS-G004
обязателен.

### HS-R005. Search не проверяет состояния, мешающие восприятию
**Тип:** rules / coverage
**Серьёзность:** S2
**Где:** `help_search.py:202-213`

Блокирующие состояния — `INCAPACITATED, STUNNED, PARALYZED,
UNCONSCIOUS` — правильно покрывают «не может действовать». Но
PHB-2024 стр. 367: Blinded → автопровал любого ability check «требующего
зрения». Perception часто требует зрения; Investigation — обычно нет.
Сейчас `SearchAction` не различает.

Это серая зона: «требует ли зрения» определяет нарратив (Perception
on hearing — OK; Perception на след — нужно зрение). Книга не даёт
бинарного правила в MVP-объёме. Но как минимум **Investigation в
темноте без darkvision** должен идти с disadvantage.

**Рекомендация (S2):** не блокировать, но через ModifierApplier
позволить ситуативное правило (часть HS-R004).

### HS-R006. DC Search не задан — корректно по контракту
**Тип:** rules / design
**Серьёзность:** информативно
**Где:** `help_search.py:21, 184`

Search **сознательно** не задаёт DC и «что найдено» — это решает
сценарий-подписчик (`SearchPerformed.total` сравнивается с DC
сценария). Это **корректно** по контракту: action в нашей архитектуре
не знает сюжетных DC. Книга 2024 (стр. 22, «Search»): «The GM decides
what kind of check is needed and the DC, based on what you're trying
to discover.»

Никакого фикса не требуется. Просто фиксируем как явное архитектурное
решение.

---

## 4. Пропущенные тесты

### HS-G001. Нет теста «Help для другого ally не помогает первому»
**Серьёзность:** S2

`test_helped_ally_no_advantage_on_different_target` проверяет, что
Help нацелен на конкретный target. Симметричный сценарий — Help
нацелен на конкретного **ally** — не покрыт. Что если в
`participants` есть два ally, и Help на первого: убедиться, что
второй ally **не** получает advantage на свою атаку.

Сценарий: helper, allyA, allyB, target. Help(allyA→target).
allyB.helped_against == None — проверить.

### HS-G002. Нет теста «one-shot потребляется ТОЛЬКО при атаке именно того ally»
**Серьёзность:** S2

Парный к HS-G001. Если ally получил Help, но **другой** participant
атакует ту же цель — поле `helped_against` ally **не сбрасывается**.
Тест зафиксирует, что AttackAction читает `actor.helped_against`, не
`target.helped_against` или что-то ещё.

Сценарий: Help(ally→target). Helper сам атакует target → ally.helped_against
не меняется.

### HS-G003. Нет теста «helper отошёл от target — преимущество не выдаётся» (HS-R001)
**Серьёзность:** S0

Прямой тест на HS-R001. Поставить Help, переместить helper в (10,10),
ally атакует target → НЕ advantage. Сейчас тест провалится (потому
что код пропустил проверку) — что и нужно зафиксировать.

### HS-G004. Нет теста «Search применяет модификаторы из ModifierApplier» (HS-R004)
**Серьёзность:** S1

ModifierBag с `AdvantageEffect` на `ABILITY_CHECK` → SearchAction
получает advantage. Без этого теста путь модификаторов для skill
checks остаётся ненаблюдаемым.

### HS-G005. Нет теста «HelpAction блокируется condition'ом» (INCAPACITATED и др.)
**Серьёзность:** S2

`test_search_blocked_by_condition` параметризован — для SearchAction.
Для HelpAction аналогичного теста нет. `_ACTION_BLOCKERS` в коде у
Help есть, но без теста регрессия не ловится.

Сценарий: actor.apply_condition(STUNNED) → HelpAction.can_perform →
Forbidden(CONDITION_BLOCKS_ACTION).

### HS-G006. Нет теста на множественный Help (HS-R003)
**Серьёзность:** S2

Help(ally→A); Help(ally→B); проверить, что `ally.helped_against ==
B`. Зафиксировать поведение «overwrite без диагностики».

### HS-G007. Нет теста на ally вне 5 фт от helper (но helper в 5 фт от target)
**Серьёзность:** S2

Книга 2024 стр. 22 говорит **только** про «within 5 feet of the
creature being attacked» (т.е. helper-to-target). Текущая
имплементация это и проверяет. Но в книге **нет требования** «helper
в 5 фт от ally»; стоит зафиксировать тестом, что Help работает,
даже когда ally в 30 фт от helper'а — чтобы не закралось ошибочное
сужение в будущем рефакторинге.

### HS-G008. Нет теста на разные участники в `participants` без пересечения
**Серьёзность:** S2

Что если в `participants` есть существо, **не имеющее** позиции на
battlefield (например, дух-наблюдатель, временно вне поля)? Сейчас
`battlefield.position_of` упадёт с KeyError. Тест — не обязательный
для E5, но как граничный — пригодится.

---

## 5. Сводный TODO

| ID       | Тип        | Серьёзность | Что делать                                                                                                                                              |
|----------|------------|-------------|---------------------------------------------------------------------------------------------------------------------------------------------------------|
| HS-R001  | rules      | **S0**      | Реализовать проверку «helper в 5 фт от target в момент атаки». Расширить поле до `(target, helper)` или унести в модификатор. Покрыть тестом HS-G003.   |
| HS-R004  | rules      | S1          | Подключить `ModifierApplier.collect(ABILITY_CHECK)` в `SearchAction.execute` (advantage/disadvantage/numeric/extra_dice). Тест HS-G004.                  |
| HS-A001  | arch       | S1          | ADR/OPEN_QUESTIONS: «Help как модификатор, после E6». Снести поле `helped_against`. Поставить TODO-маркер в коде attack.py:272.                          |
| HS-A002  | arch       | S1          | До HS-A001 — комментарий в `attack.py:272-277` о временности; тест HS-G002 на корректную one-shot потребление-границу.                                   |
| HS-G001  | test       | S2          | «Help нацелен на конкретного ally — другие ally не получают advantage».                                                                                  |
| HS-G002  | test       | S2          | «one-shot потребляется только при атаке именно того ally».                                                                                               |
| HS-G005  | test       | S2          | Параметризованный тест «HelpAction блокируется condition'ом».                                                                                            |
| HS-A003  | arch       | S2          | TODO/ADR: `skill_mod: int` → канал ModifierApplier (родственно AT-A004).                                                                                 |
| HS-R002  | rules      | S2          | OPEN_QUESTIONS: Help для ability check — после E-Skills.                                                                                                 |
| HS-R003  | rules      | S2          | Решить семантику множественного Help: overwrite + поле `replaced_previous` в `HelpGranted`, или Forbidden. Тест HS-G006.                                 |
| HS-A005  | arch       | S2          | В ROADMAP/E-Encounter: «Encounter сбрасывает helped_against на старте хода owner'а».                                                                     |
| HS-G007  | test       | S2          | Тест «Help работает, даже когда ally в 30 фт от helper'а».                                                                                                |
| HS-A004  | arch       | S2          | В ACTIONS.md §2: явно зафиксировать «action без target-аргумента не имеет can_perform_against».                                                          |
| HS-R005  | rules      | S2          | Через HS-R004: учесть Blinded → disadvantage на Perception со зрением.                                                                                   |
| HS-G008  | test       | S2          | Граничный тест: participant без позиции на battlefield.                                                                                                  |
| HS-R006  | design     | info        | Зафиксировать в DESIGN.md, что DC Search — сценарий, не движок.                                                                                          |

---

Конец отчёта.

---

## Применённые фиксы (2026-05-21)

**S0 — закрыто:**

* **HS-R001** — PHB-2024 стр. 22: «if the target is no longer within
  5 feet of you when the attack is made, you lose the benefit».
  Добавлено поле `Creature.helped_by: CreatureId | None` рядом с
  `helped_against`; `HelpAction.execute` ставит обе поля; в
  `AttackAction.execute` перед использованием advantage проверяется
  `helper_pos.distance_to_feet(target_pos) <= 5`. Both fields one-shot
  сбрасываются после атаки (даже если бонус «потерян»). Три теста:
  * `test_help_advantage_lost_when_helper_moves_away_before_attack`
  * `test_help_advantage_applied_when_helper_still_within_5ft`
  * `test_help_advantage_lost_when_helper_removed_from_battlefield`

**Отложено (S1):**

- **HS-A001** — Help через `Creature.helped_against` минуя
  `ModifierApplier` — двойной канал advantage. Полный фикс требует
  «target-aware» модификаторов в ModifierBag; план — после MODIFIERS.md
  расширения.
- **HS-A002** — side-effect `actor.helped_against = None` в
  `AttackAction.execute`. Архитектурно правильнее очистка через
  Encounter на старте следующего хода ally; одноразовое потребление —
  компромисс MVP.
- **HS-R004** — `SearchAction` не вызывает `ModifierApplier.collect(ABILITY_CHECK)`.
  Будет в той же ветке расширения ModifierApplier на ABILITY_CHECK.

**Цифры:** test_help_search.py: 22 passed (+3); общее 605 passed.

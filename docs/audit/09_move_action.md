# Audit 09: MoveAction (E3)

Независимый ревью **кода и тестов** этапа E3 — `MoveAction`:

- `src/dnd/application/engine/actions/move.py`
- `tests/unit/application/actions/test_move_action.py`
- `src/dnd/application/dto/engine_event.py` — подклассы `MoveStepTaken`,
  `MoveCompleted`, `OpportunityAttackProvoked`
- `src/dnd/application/engine/turn_context.py` — новое поле `disengaged: bool`
- `src/dnd/application/dto/action.py` — новые `ForbiddenReason.INVALID_PATH`
  и `IMPASSABLE_TERRAIN`

Источники правды:

- `docs/ACTIONS.md` §2 (Action protocol), §6 (жизненный цикл «без двойной
  валидации»).
- `docs/ENGINE.md` §4 (Action как Command), §5.2 (EventBus FIFO),
  §2.1 (Chebyshev в ADR-0002), §2.5 (правила провоцированной атаки).
- `docs/MODIFIERS.md` — на этом этапе модификаторы скорости не реализуются;
  бюджет в футах приходит из `TurnContext.movement_remaining_ft`.
- «Книга Игрока 2024»: стр. 22 (Перемещение, Перемещение около других
  существ, Disengage), стр. 23 (труднопроходимая местность — каждый
  фут стоит 2 фута), стр. 367 (Incapacitated и его implies).

Дата: 2026-05-21. Ревьюер: внешний.

Запуск: `pytest tests/unit/application/actions/test_move_action.py -v`
— **22 passed**.

---

## 1. Краткое резюме

Дизайн совпадает с `ACTIONS.md`: `can_perform` — pure-функция,
двухуровневая проверка (`can_perform` глобально + `can_perform_against`
по конкретному пути), `execute` пошагово тратит футы, мутирует
`Battlefield` и публикует события ровно один раз. `MoveAction`
осознанно **не выполняет** провоцированную атаку, а только триггерит
её через `OpportunityAttackProvoked` — это правильная декомпозиция под
будущий E6 (`OpportunityAttack` реакция). Disengage-флаг читается из
`TurnContext.disengaged`, что не вводит обратной зависимости на
конкретный `Encounter`.

Контракт `EngineEvent` соблюдён: все три новых подкласса frozen +
`extra="forbid"`. Difficult terrain ×2 cost реализован в обеих фазах
(валидация и execute), формула 5/10 фт идентична на двух путях.

Главные риски:

- **MV-R001 (S1):** провокация opportunity attack публикуется без
  проверки LoS от threatener'а к actor'у. PHB-2024 стр. 22: «If you
  can see a creature ... that is moving out of your reach». В коде
  `_collect_threateners` фильтрует мёртвых/incapacitated, но не
  фильтрует тех, у кого нет линии видимости. Для тёмной комнаты,
  невидимого actor'а или wall'а между — провокация всё равно
  стрельнёт. Это не правится «потом» молча — это уже неправильное
  правило в MVP.
- **MV-A001 (S1):** валидация в `can_perform_against` (стоимость
  пути, соседство, in_bounds, passable) **повторяется в** `execute`
  частично: `execute` сам пересчитывает `cost = 10 if terrain.difficult
  else 5` и сам читает `terrain_at(step)`. Это нарушает ACTIONS.md §6
  «никаких двойных вычислений». Не баг, но дублирование, которое
  может разойтись при правке (например, добавим snow → особая
  стоимость, а в одном месте забудем).
- **MV-A002 (S1):** `_collect_threateners` использует константу
  `_MOVEMENT_BLOCKERS` (`incapacitated, stunned, paralyzed,
  unconscious`) для проверки «может ли threatener реагировать».
  Семантически это **другое** свойство: реакцию блокирует
  Incapacitated (PHB-2024 стр. 367: «не может предпринимать действия и
  реакции»), а не «движение блокируется». На корректность это сейчас
  не влияет (Stunned/Paralyzed/Unconscious через `implies` дают
  Incapacitated), но смешение терминов — будущая мина.
- **MV-G001 (S1):** ни одного теста на «несколько threatener'ов
  одновременно угрожают одной клетке» — а это типичная боевая
  ситуация (двое орков рядом). Сейчас `_collect_threateners` строит
  словарь, и тест с одним threatener не отлавливает, корректно ли
  итерируется множество.

Дальше — поэлементный разбор.

---

## 2. Архитектурные находки

### MV-A001. Частичное дублирование валидации path в `execute`
**Тип:** architecture / contract
**Серьёзность:** S1
**Где:** `move.py:194-216` против `move.py:137-156`

`can_perform_against` проходит по пути, проверяет `in_bounds`,
`is_adjacent`, `passable` и считает `total_cost`. `execute` затем
**второй раз** читает `terrain_at(step)` для каждого шага и
**снова** считает `cost = 10 if terrain.difficult else 5`. Логика
расчёта стоимости теперь живёт в двух местах с идентичной
формулой — это первый кандидат на расхождение при правке
(пример: появится `Terrain.swim_cost` или `crawl_cost`, и легко
забыть синхронизировать оба расчёта).

ACTIONS.md §6 явно: «Никаких двойных вычислений: всё, что прошло
`can_perform`, выполняется в `execute` без повторной проверки».

Минимум: вынести `_step_cost(terrain) -> int` в private helper и
использовать в обоих фазах. Опционально — собрать в
`can_perform_against` структуру `tuple[StepPlan]` с уже посчитанной
стоимостью per-step и передать через `MoveParams` (но это меняет
DTO).

Связано: `execute` тратит футы через `ctx.spend_movement(cost)`,
который сам валидирует «хватит ли движения и кратно ли 5». Если
контракт нарушен между фазами (например, кто-то изменил
`movement_remaining_ft` между `can_perform_against` и `execute`),
`spend_movement` поднимет `ValueError` — но публикуемые события на
ранние шаги **уже уйдут в шину**. Поскольку EventBus синхронный и
FIFO, подписчики на промежуточные `MoveStepTaken` отработают, а
финального `MoveCompleted` не будет. Это нарушает атомарность
действия (см. ACTIONS.md §5: «`success=True` означает, что действие
**завершилось**»). Документировать инвариант: «после успешного
`can_perform_against` `execute` обязан дойти до конца», иначе
seам делегировать атомарность не вышло.

### MV-A002. `_collect_threateners` смешивает «блокеры движения» и «блокеры реакции»
**Тип:** architecture / semantics
**Серьёзность:** S1
**Где:** `move.py:266-271`

```python
for blocker in _MOVEMENT_BLOCKERS:
    if other.has_condition(blocker):
        break
else:
    result[other_id] = ctx.battlefield.threatens_squares(other_id)
```

`_MOVEMENT_BLOCKERS = {INCAPACITATED, STUNNED, PARALYZED, UNCONSCIOUS}` —
это набор «состояния, отменяющие движение». А здесь мы спрашиваем
**другое**: «может ли threatener использовать реакцию?». Ответ
книги: «нет, если он Incapacitated». Stunned/Paralyzed/Unconscious
тоже не могут — но не потому, что они в этом наборе, а потому, что
имеют `implies = {INCAPACITATED}` в `ConditionRegistry`.

Сейчас работает, потому что (а) ConditionRegistry проставляет
implies, и (б) тесты накладывают условие напрямую через
`Creature.apply_condition` (минуя implies), и тогда им нужно
явное перечисление в `_MOVEMENT_BLOCKERS`. То есть мы получаем
двойную защиту, как и в `AttackAction._BLOCKING_CONDITIONS`
(см. audit 08, AT-A002). Аналогично, рекомендация: если в Encounter
все condition'ы накладываются через `ConditionService.apply_with_implies`,
проверять только `INCAPACITATED` и иметь тест-симулятор инварианта.
Иначе — выделить отдельную константу `_REACTION_BLOCKERS` и не
переиспользовать `_MOVEMENT_BLOCKERS` для другой семантики.

### MV-A003. Threatener на той же клетке, что actor, не «угрожает» — ему молча даём «уйти бесплатно»
**Тип:** architecture / rules edge-case
**Серьёзность:** S2
**Где:** `move.py:200-212`, `battlefield.py:266-293`

`Battlefield.threatens_squares(creature_id)` исключает саму клетку
существа из множества угрозы — стандартная семантика «угрожаемые
клетки вокруг себя». Если actor и threatener стоят в **одной**
клетке (book допускает несколько существ на клетке, ENGINE.md §2.2),
то `prev` (= позиция actor'a = позиция threatener'a) **не** входит
в `reach_squares`. На первом же шаге проверка `prev in reach_squares
and step not in reach_squares` даст False — никакой провокации.

В книге это редкий случай (обычно союзники), но формально, выходя
из клетки врага, ты «leave their reach» (ты был в его reach, потому
что 0 ft ≤ 5 ft). Решений два: либо `threatens_squares` начнёт
включать центральную клетку (что ломает другие вызовы — атаки
`reach 5`), либо `_collect_threateners` дописывает позицию самого
threatener'а в reach-множество явно для целей MoveAction. На MVP
сценарий редкий — но стоит зафиксировать в docstring и завести
todo.

### MV-A004. `execute` сначала публикует `OpportunityAttackProvoked`, потом тратит футы и двигает существо
**Тип:** architecture / event order
**Серьёзность:** S2
**Где:** `move.py:200-227`

Текущая последовательность для шага:

1. публикуем `OpportunityAttackProvoked` (если выход из reach);
2. `ctx.spend_movement(cost)`;
3. `ctx.battlefield.move_creature(actor.id, step)`;
4. публикуем `MoveStepTaken`.

Это **верный** порядок (провокация — *до* шага, как в книге).
Но он создаёт инвариант: к моменту обработки `OpportunityAttackProvoked`
подписчиком actor **ещё стоит** на `prev`. Когда придёт E6
(`OpportunityAttack` как реакция), реактор-handler должен будет
прочитать позицию атакующего (для cover/LoS) — и получит `prev`,
не `step`. Это согласуется с PHB («атака происходит до выхода»), но
сейчас ни тестом, ни комментарием не зафиксировано: «`leaving_square`
== `actor.position` в момент публикации».

Минимум: в docstring `OpportunityAttackProvoked` добавить «инвариант:
actor стоит на `leaving_square` в момент публикации события».

### MV-A005. `MoveAction.economy_cost_value: Final = MOVEMENT` через property — тот же smell, что в AttackAction
**Тип:** architecture / style
**Серьёзность:** S2
**Где:** `move.py:89-101`

Та же конструкция «ClassVar + property» из E2 (см. audit 08 AT-A005).
В E3 ничем не лучше — рекомендация одна: убрать промежуточную
константу, оставить `economy_cost: ClassVar[ActionEconomyCost]`.
Не критично, низкий приоритет; но единожды зафиксированный паттерн
размножается без рефакторинга.

### MV-A006. `MoveAction` явно не знает про `Encounter` — это плюс
**Тип:** architecture / positive
**Серьёзность:** —

Никаких импортов из `Encounter`, никаких знаний про порядок
инициативы. Действие читает только `actor`, `params`, `ctx` —
ровно как и должно. `ctx.disengaged` живёт в `TurnContext`, что
архитектурно правильно: Disengage — это «свойство хода», и читатель
не зависит от того, кто и как этот флаг выставил (E4
`DisengageAction` или мастер-вмешательство).

---

## 3. Расхождения с книгой

### MV-R001. Провокация публикуется без проверки LoS у threatener'а
**Тип:** rules / gap
**Серьёзность:** S1
**Где:** `move.py:200-212`

PHB-2024 стр. 22, «Перемещение около других существ»:

> Если вы видите существо... которое выходит из вашей зоны
> досягаемости, вы можете использовать вашу реакцию...

«Видите» — обязательное условие. В коде проверки нет:
`_collect_threateners` фильтрует только живых/non-incapacitated, а
`battlefield.line_of_sight(threatener_pos, actor_pos)` не
вызывается. Сценарии, в которых это даст ошибочную провокацию:

- actor невидим (Invisible) — visible without check, провокация
  не должна;
- между threatener и actor стена/total cover — нет LoS;
- thretener слеп (Blinded) — формально «не видит»; в коде Blinded
  даже не учтён;
- темнота для существа без darkvision — то же.

На MVP, где Invisible/Blinded не моделируются полно, **минимум**
надо добавить `ctx.battlefield.line_of_sight(threatener_pos,
actor_pos_before_step)` — это уже работающий метод
`Battlefield.line_of_sight`. Поведение Blinded/Invisible откладывается
до соответствующих условий, но LoS через стены — это **сегодняшний**
gap.

### MV-R002. Провокация не учитывает «hostile only»
**Тип:** rules / gap
**Серьёзность:** S2 (пока нет faction'ов — отложенно)
**Где:** `move.py:200-212`

PHB-2024 стр. 22: «provokes an opportunity attack **from a hostile
creature**». В коде провокация публикуется от **любого** живого
существа в reach, включая союзников. Это не баг (нет понятия
faction в MVP, Creature не имеет `team`/`alignment_to(actor)`), но
обязано быть в TODO для post-Character/post-Encounter этапа. Иначе
после интеграции с PC/NPC получим «PC уходит от тренировочного
напарника — союзник его атакует».

### MV-R003. Провокация триггерится только при «выходе из reach», а не при «движении внутри reach» — корректно
**Тип:** rules / positive check
**Серьёзность:** —

PHB-2024 стр. 22: «Вы не провоцируете... если вы лишь шагаете
внутри его зоны досягаемости». Тест
`test_opportunity_not_provoked_while_staying_in_reach` это
покрывает. Реализация — корректная: `prev in reach_squares and
step not in reach_squares`.

### MV-R004. «Одна реакция per threatener per movement» — корректно
**Тип:** rules / positive check
**Серьёзность:** —

`already_provoked: set[CreatureId]` гарантирует только одно событие
на threatener'а за всё движение, даже если actor выходит/входит
несколько раз. PHB-2024 стр. 22: реакция одна в раунд, и движок
явно не повторяет триггер. Тест
`test_opportunity_provoked_once_per_threatener_in_one_move`
покрывает.

Тонкость: PHB-2024 говорит «one reaction per round», а наш код
делает «один триггер per threatener per **movement**». Это **более
строгая** гарантия: если actor использует Dash и идёт повторно по
тому же threatener'у — текущая логика **не** триггернёт второй раз
в том же `execute`-вызове. Это корректно для одного MoveAction.
Если в Dash-сценарии будет **два** последовательных MoveAction
(второй после Dash), `MoveAction` создаст новый `already_provoked`
set и триггер повторится. Тогда защита от двойной реакции должна
жить в reaction-handler'е (`reaction_used` в TurnContext или
round-уровне), не в MoveAction. **Документировать это явно** — иначе
позже спросят «почему MoveAction не помнит триггеры между
действиями».

### MV-R005. Difficult terrain ×2 — корректно, но только «входная клетка»
**Тип:** rules / positive check
**Серьёзность:** —

PHB-2024 стр. 23: «каждый фут перемещения в труднопроходимой
местности стоит дополнительный фут». В коде:
`cost = 10 if terrain.difficult else 5`, где `terrain` —
**входная** клетка (`step`). То есть стоимость диктует та клетка,
**в которую** мы заходим, не та, **из которой**. Это согласуется с
правилом «вы платите за вход в difficult», корректно.

### MV-R006. Диагональ = 5 ft, не 5/10/5 — соответствует ADR-0002
**Тип:** rules / positive check
**Серьёзность:** —

В тесте `test_execute_diagonal_step_costs_5ft` зафиксировано.
ADR-0002: Chebyshev, без диагонального правила «5/10/5». Согласовано.

### MV-R007. Disengage подавляет провокацию — корректно
**Тип:** rules / positive check
**Серьёзность:** —

`threateners = {} if ctx.disengaged else self._collect_threateners(...)`
— упрощённая, но корректная реализация. PHB-2024 стр. 22, «Disengage»:
«ваше движение не провоцирует opportunity attacks до конца хода».
Тест `test_disengage_suppresses_provocation` покрывает.

Тонкость: флаг `disengaged` живёт до конца хода — корректно, что
он не сбрасывается внутри MoveAction. Сброс — обязанность
`Encounter`/`start_new_turn`. В `TurnContext.start_new_round` сброс
disengaged **не** делается — но `start_new_round` сбрасывает
только межходовые ресурсы (reaction). Поэтому при создании нового
`TurnContext` в новом ходу `disengaged` должен инициализироваться
False по умолчанию (что dataclass-дефолт делает). Если же `Encounter`
переиспользует TurnContext между ходами одного существа — пропадёт.
Зафиксировать инвариант: «`TurnContext` создаётся новый на каждый ход».

---

## 4. Пропущенные тесты

### MV-G001. Нет теста на **двух одновременных threatener'ов**
**Серьёзность:** S1

`_collect_threateners` строит словарь, и шаг проверяется против
**всех** в словаре. Тест с одним threatener не отлавливает
итеративную часть. Сценарий: actor в (3,3), threatener A в (2,2),
threatener B в (4,4) — оба в reach (3,3). Шаг в (3,4) выводит из
обеих зон. Ожидание: два события `OpportunityAttackProvoked`, по
одному на threatener'а, **в одном** шаге.

### MV-G002. Нет теста на «вход в reach и выход» (актор стартует ВНЕ reach)
**Серьёзность:** S2

Все провокационные тесты стартуют с `prev in reach_squares` уже на
старте. Сценарий: actor в (1,1), threatener в (4,4) — НЕ в reach.
Путь: (2,2) (вход в reach), (3,3) (внутри reach), (4,4 же занят)
→ скажем (3,4) (внутри), (2,4) (выход). Ожидание: одна
провокация, при выходе. Сейчас формально проверяется через
`already_provoked` и условие `prev in reach`, но без теста легко
сломать на рефакторинге.

### MV-G003. Нет теста на порядок событий: `OpportunityAttackProvoked` ДО `MoveStepTaken`
**Серьёзность:** S1

`test_execute_moves_step_by_step_and_publishes` проверяет порядок
`events_published` только для базового движения без провокаций. Для
шага с провокацией нет ассерта на относительный порядок «провокация
раньше шага». Этот инвариант критичен для будущего E6 — реактор
должен видеть actor'а на `leaving_square`, не на `step`.

### MV-G004. Нет теста на «MoveCompleted всегда публикуется ровно один раз»
**Серьёзность:** S2

Базовый тест проверяет `events_published == (..., "move.completed")`.
Но нет негативного теста, что `MoveCompleted` НЕ публикуется
дважды (например, при единственном шаге). Минор, но `tuple`-equality
с фиксированной длиной это уже покрывает — формально риска нет.

### MV-G005. Нет теста на «participants пуст / нет других на карте»
**Серьёзность:** S2

`_setup()` без `others` — единственный actor. Все execute-тесты в
этой ветке (`test_execute_moves_step_by_step_and_publishes` и т.п.)
косвенно покрывают «participants содержит только actor», но нет
явного assert, что в captured **нет** `OpportunityAttackProvoked`.
Тонко, но если кто-то изменит `_collect_threateners` так, что
actor сам себя «угрожает», тест не упадёт.

### MV-G006. Нет теста на комбинацию **difficult terrain + провокация**
**Серьёзность:** S2

Difficult terrain и провокация тестируются раздельно. Шаг в
difficult клетку, выходящий из reach threatener'а, должен:
(а) опубликовать провокацию, (б) опубликовать `MoveStepTaken` с
`cost_ft=10, difficult=True`, (в) списать 10 фт из бюджета. Это
интеграционная проверка двух механик в одном шаге.

### MV-G007. Нет теста на «контракт нарушен → execute падает прозрачно»
**Серьёзность:** S2

Если вызвать `execute` без предварительного `can_perform_against`,
с путём, который не проходит валидацию (например, через стену), —
`execute` не валидирует и пойдёт через `terrain_at(step)`,
получит passable=False, но `move_creature(actor.id, step)` упадёт
с `ValueError("cannot place creature on impassable terrain")`. Это
**прозвучит как баг движка**, а не как нарушение контракта.

Минимум — тест-симулятор, документирующий: «при нарушении контракта
получите ValueError от Battlefield». Это не валидация, это контракт
для будущих интеграций.

### MV-G008. Нет теста на blinded/invisible (привязан к MV-R001)
**Серьёзность:** S1 (если фиксим MV-R001)

После добавления LoS-проверки нужен тест: actor невидим / стоит за
стеной → нет провокации. Сейчас Condition `Blinded` и `Invisible`
есть в conditions/builtin (проверить), но MoveAction их не
учитывает.

### MV-G009. Test smell: распаковка через generator-expression хрупкая
**Серьёзность:** S2

В `test_execute_moves_step_by_step_and_publishes`:

```python
step1, step2, done = (
    e for e in captured if isinstance(e, (MoveStepTaken, MoveCompleted))
)
```

Если в `captured` окажется лишнее событие или одно отсутствует —
тест упадёт с маловразумительным `ValueError: too many values` или
`not enough values`. Лучше: явный `events = [e for e in captured
if ...]; assert len(events) == 3`.

### MV-G010. Test smell: `_make_creature()` дважды для одного актора
**Серьёзность:** S2

В `test_can_perform_allowed_with_movement`:

```python
_, ctx, _ = _setup()
assert isinstance(MoveAction().can_perform(_make_creature(), ctx), Allowed)
```

`_setup()` создаёт actor с id="actor", далее `_make_creature()` без
аргумента создаёт **другого** актора с тем же id. На сегодняшний
`can_perform` это нерелевантно (он смотрит только условия и
`movement_remaining_ft`), но в момент, когда `can_perform` начнёт
читать `ctx.battlefield.position_of(actor.id)` или
`ctx.participants[actor.id]`, тест либо упадёт по нелогичной
причине, либо пройдёт по совпадению id. Рекомендую: возвращать
actor из `_setup` и использовать его (как в большинстве остальных
тестов).

---

## 5. Сводный TODO по приоритету

### S0
(нет находок этого приоритета)

### S1
1. **MV-R001** — добавить проверку LoS от threatener'а к actor'у
   в `_collect_threateners` (через
   `ctx.battlefield.line_of_sight(threat_pos, actor_pos)`); добавить
   тест MV-G008.
2. **MV-A001** — вынести `_step_cost(terrain)` в helper и
   переиспользовать в обоих фазах; задокументировать инвариант
   атомарности `execute` (либо ввести rollback, либо явно сказать
   «вызывающий обязан гарантировать неизменность state между
   `can_perform_against` и `execute`»).
3. **MV-A002** — переименовать константу или развести
   `_REACTION_BLOCKERS` отдельно от `_MOVEMENT_BLOCKERS`;
   зафиксировать в комментарии, почему этих условий хватает.
4. **MV-G001** — тест на нескольких одновременных threatener'ов.
5. **MV-G003** — тест на порядок `OpportunityAttackProvoked` ДО
   `MoveStepTaken` в одном шаге.

### S2
6. **MV-A003** — задокументировать поведение «threatener в одной
   клетке с actor'ом», в TODO для пост-MVP.
7. **MV-A004** — добавить инвариант в docstring
   `OpportunityAttackProvoked` («actor стоит на `leaving_square`»).
8. **MV-A005** — упростить `economy_cost` (убрать ClassVar +
   property), синхронно с E2.
9. **MV-R002** — TODO «hostile only» в комментарии к
   `_collect_threateners`, привязать к этапу faction/Character.
10. **MV-R007** — задокументировать инвариант «`TurnContext`
    создаётся новый на каждый ход» (для сброса `disengaged`).
11. **MV-G002**, **MV-G004**…**MV-G007** — добавить недостающие
    тесты по списку §4.
12. **MV-G009**, **MV-G010** — почистить тест-смеллы.

---

## Приложение: что **не** проверялось

По заданию ревью:

- Диагональ «5/10/5» — пост-MVP, помечена в docstring.
- Прерывание движения реакцией — пост-MVP, явно зафиксировано.
- Различный reach у threatener'ов (глефа, копьё) — помечен «придёт
  через данные существа, когда Character заведёт оружие». Текущий
  hardcoded `reach_ft=5` по умолчанию в `Battlefield.threatens_squares`
  — корректное решение для MVP.

---

## Применённые фиксы (2026-05-21)

**S1 — закрыто:**

* **MV-R001** — `MoveAction._collect_threateners` теперь вызывает
  `battlefield.line_of_sight(threatener_pos, actor_pos)` и отбрасывает
  threatener'ов без LoS. Тесты `test_no_provocation_when_threatener_cannot_see_actor`
  и `test_provocation_with_los_still_works` фиксируют контракт.
* **MV-G001** — добавлен `test_multiple_threateners_each_get_one_provocation`:
  двое орков угрожают (2,2); actor уходит в (3,3) (вне reach обоих)
  → ровно две `OpportunityAttackProvoked`, каждая со своим threatener_id.
* **MV-G003** — добавлен `test_opportunity_provoked_event_published_before_step_taken`:
  фиксирует FIFO порядок (Provoked раньше StepTaken, leaving_square
  = старая позиция).

**Отложено (S1/S2):**
- **MV-A001 (S1)** — дублирование валидации в `execute`. Оставлено,
  потому что фикс требует выделения `_path_cost` helper'а в обе
  функции; план — после Encounter, когда станет понятным контракт
  «частичное движение».
- **MV-A002 (S2)** — семантическое смешение `_MOVEMENT_BLOCKERS`. Будет
  переименовано на `_REACTION_BLOCKERS` отдельной правкой.

**Цифры:** pytest 605 passed (+13 за фиксы аудитов 09-12), test_move_action.py: 26 passed (+4); coverage 97.51%.

# Аудит 12: OpportunityAttack (этап E6)

**Автор:** Maxim Lokotkov
**Дата:** 2026-05-21
**Под ревью:**
- `src/dnd/application/engine/actions/opportunity_attack.py`
- `tests/unit/application/actions/test_opportunity_attack.py`
- `src/dnd/application/engine/actions/attack.py` (рефакторинг `_check_economy` / `_spend_economy` как template-hook'и)
- `src/dnd/domain/entities/creature.py` (поле `reaction_used: bool = False`)

**Прогон тестов:** `pytest tests/unit/application/actions/test_opportunity_attack.py -v` — 11/11 PASSED.

---

## 1. Резюме

E6 — корректная и минимально-инвазивная реализация Opportunity Attack как reaction-режима стандартной атаки. Архитектурное решение «hook-методы `_check_economy` / `_spend_economy` в базовом `AttackAction`» вычистило неявный смелл прошлых этапов (E2/E5 неявно предполагали, что бюджет атаки списывается всегда через `ctx.spend(ACTION)`) и сделало путь reaction'а декларативным. Перенос `reaction_used` на саму `Creature` обоснован: реакция случается в **чужой** ход, и `TurnContext`, принадлежащий двигающемуся, держать её состояние не может (это и есть тот «неявный архитектурный смелл», который был зафиксирован — теперь явно исправлен).

Тесты честно покрывают экономику reaction'ов, неинтерференцию с `ctx.reaction_used`, наследование `can_perform_against` и end-to-end публикацию `OpportunityAttackProvoked` → handler. Mockup-handler в `test_move_triggers_provoked_and_handler_executes_oa` — **достаточно честный** интеграционный тест на уровне «событие + ручной подписчик»: настоящий Encounter (этап F) подключит handler из `ActionRegistry`, но контракт «MoveAction публикует — OpportunityAttack потребляет» уже проверен на живом `InMemoryEventBus`.

**Главная находка S1 — OA-R001:** `OpportunityAttack.execute` не валидирует, что `AttackParams.kind is AttackKind.MELEE`. Игрок/AI может технически передать `RANGED`-параметры в реакцию по выходу из reach — это противоречит PHB-2024 стр. 22 («one melee attack»). Реализационно — это не падает, потому что `range_ft` всё ещё ограничивает дальность, но семантически правила нарушаются (можно использовать лонгбоу как реакцию на выход).

S0-блокеров нет. Все остальные находки — S2 (GAP/полировка).

---

## 2. Архитектура — S0/S1/S2

### OA-A001 (S2) — LSP-семантика переопределения `_check_economy`/`_spend_economy`

**Что.** `OpportunityAttack._check_economy` сознательно **игнорирует** `ctx.can_spend(REACTION)` и проверяет вместо этого `actor.reaction_used`. Формально подкласс **меняет наблюдаемое поведение** одноимённого метода базы (`AttackAction._check_economy` проверяет `ctx`, подкласс — поле существа).

**Оценка.** Это **template-method pattern**, а не violation LSP: базовый `AttackAction.can_perform` сам объявляет `_check_economy` точкой расширения в docstring («Подклассы (`OpportunityAttack`) переопределяют её для reaction-режима»). Контракт — «вернуть `Allowed`/`Forbidden(NO_ECONOMY_LEFT)`» — сохранён. Это допустимое замещение.

**Замечание.** Контракт hook'а нигде формально не задокументирован за пределами docstring'а метода — нет ни `Protocol`/`ABC`, ни записи в ACTIONS.md §6. Когда появятся другие reaction-action'ы (Shield, Counterspell в постMVP), будет соблазн каждый раз переопределять `_check_economy` индивидуально. Лучше явно зафиксировать «бюджет = функция от (actor, ctx)» как протокол.

**TODO.** В `docs/ACTIONS.md` §6 (или новом §7 «Reaction actions») зафиксировать контракт пары `_check_economy` / `_spend_economy` как hook'ов AttackAction и допустимый сценарий замены `ctx`-бюджета на `actor`-бюджет. Альтернативно — выделить миксин `ReactionEconomyMixin` под reuse.

### OA-A002 (S2) — наследование AttackAction вместо композиции

**Что.** `OpportunityAttack(AttackAction)` — наследование от non-frozen application-action'а с большим телом `execute`. Все будущие правки в `AttackAction.execute` (например, спорный fix «ranged-в-упор → disadvantage» из TODO) автоматически попадут в OA.

**Оценка.** Для E6 — оправдано: вся книжная логика атаки переиспользуется один-в-один, и переопределять `execute` пришлось бы целиком. Однако если в `AttackAction.execute` появятся ACTION-only-ветки (например, multi-attack из Extra Attack, или Action Surge), их придётся явно фильтровать в OA. Это **скрытый риск регресса**.

**TODO.** Зафиксировать в комментарии у `OpportunityAttack`: «любое расширение `AttackAction.execute` обязано проверяться против reaction-режима». Пост-MVP — рассмотреть выделение чистого `_perform_one_attack(actor, params, ctx)` в `AttackAction`, который OA вызывает напрямую (композиция-через-protected-метод, без наследования всей оболочки `can_perform`/economy).

---

## 3. Правила «Книги Игрока 2024» — S0/S1/S2

### OA-R001 (S1) — нет валидации `AttackKind.MELEE` в OpportunityAttack

**Книга.** PHB-2024 стр. 22, «Opportunity Attack»: «you can use your reaction to make **one melee attack** against that creature».

**Что в коде.** `OpportunityAttack.execute` принимает любые `AttackParams`, включая `kind=AttackKind.RANGED`. Никакой проверки нет ни в `OpportunityAttack._check_economy`, ни в переопределении `can_perform_against` (последнего вообще нет — наследуется база). База тоже не запрещает RANGED.

**Воспроизведение.** Тест с `AttackParams(kind=AttackKind.RANGED, attack_bonus=5, damage_expr="1d6", range_ft=80, ...)` пройдёт `can_perform_against` и `execute` — рулёжка попадёт через ranged-ветку (`long_range_penalty`, dodge_penalty, и т.д.), результат — успешная ranged-OA. Это нарушение правил.

**TODO.** В `OpportunityAttack.can_perform_against` (либо в `execute` как контрактная проверка типа сейчас на `isinstance(params, AttackParams)`) добавить:

```python
if params.kind is not AttackKind.MELEE:
    return Forbidden(reason=ForbiddenReason.INVALID_PARAMS)  # или новый код
```

Тест: `test_oa_rejects_ranged_attack_params`.

### OA-R002 (S2) — «you can see» проверяется только симметрично через LoS атакующего

**Книга.** PHB-2024 стр. 22: «when a creature **you can see** moves out of your reach».

**Что в коде.** `can_perform_against` (унаследованный) проверяет `battlefield.line_of_sight(attacker_pos, target_pos)` — симметрично (LoS направлен от реактора к движущемуся, что и нужно). На MVP-карте без односторонних окон/туманов LoS симметричен по построению; реальной дыры нет.

**Замечание.** В docstring `OpportunityAttack` это явно не зафиксировано — будущий разработчик может убрать LoS-проверку, не заметив, что она же закрывает «can see». Стоит оставить комментарий-якорь.

**TODO.** В docstring `OpportunityAttack._check_economy` (или класса) добавить:
> «PHB-2024 стр. 22 “you can see” — реализуется через `can_perform_against.line_of_sight`, симметричный в MVP».

### OA-R003 (S2) — реактор-мертвец / Incapacitated в публичной точке входа

**Книга.** PHB-2024 стр. 367: Incapacitated → «can't take actions, **bonus actions, or reactions**». Мёртвое существо реагировать не может.

**Что в коде.**
- `MoveAction._collect_threateners` уже фильтрует `not other.is_alive` и `_MOVEMENT_BLOCKERS` (Incapacitated/Stunned/Paralyzed/Unconscious) → событие `OpportunityAttackProvoked` для мёртвого/parralyzed реактора **не публикуется**. В цепочке Move→OA дыры нет.
- Но `OpportunityAttack.can_perform` (через базу) проверяет `_BLOCKING_CONDITIONS` (Incapacitated и т.п.) — это OK. Однако **`is_alive` базовая `can_perform` не проверяет**. Если кто-то напрямую дернёт `OpportunityAttack().execute(dead_fighter, ...)`, реакция «выстрелит из трупа».

**Оценка.** Защита есть в Move (правильное место), и `can_perform_against` контракта `actor.is_alive` тоже не требует — это общесистемная гарантия (Encounter не должен давать ход трупу). Но для reaction'а двери шире: реакция случается **в чужой ход**, и Encounter не вызывает её напрямую — её зовёт handler из подписки. Гарантия «реактор жив на момент срабатывания handler'а» — на Encounter (этап F).

**TODO.** Либо в `OpportunityAttack.can_perform` добавить `if not actor.is_alive: return Forbidden(...)` (защита на месте), либо явно зафиксировать в docstring инвариант «реактор обязан быть жив; проверяется вызывающим». Я бы предпочёл первое — стоимость одна строка, цена ошибки в Encounter высока.

### OA-R004 (S2) — `OpportunityAttack` использует общий путь `helped_against` / `dodging` / `long_range_penalty`

**Что.** Поскольку OA наследует `AttackAction.execute`, реакция **сжигает** `actor.helped_against` (Help one-shot), если он совпадал с движущимся. Это правильно по правилам — Help распространяется на «next attack roll», без оговорки «в свой ход». Но **в тестах не проверено**.

**TODO.** Тест `test_oa_consumes_helped_against_if_set` (обеспечит регресс-защиту).

---

## 4. Пропущенные тесты

| ID | Тест | Покрывает |
|----|------|-----------|
| OA-G001 | `test_oa_rejects_ranged_attack_params` | OA-R001: RANGED-параметры → `Forbidden` |
| OA-G002 | `test_oa_blocked_when_actor_incapacitated` | наследованный `_BLOCKING_CONDITIONS`-блок для reactor'а (сейчас проверяется только для обычной атаки) |
| OA-G003 | `test_oa_blocked_when_actor_unconscious_at_zero_hp` | `not actor.is_alive` (если решим добавить проверку — см. OA-R003) |
| OA-G004 | `test_oa_consumes_helped_against` | OA-R004: Help one-shot на reaction'е |
| OA-G005 | `test_oa_executed_twice_via_handler_in_same_round_second_skipped` | end-to-end: два движения подряд провоцируют двух событий, но handler выполнит OA только один раз |
| OA-G006 | `test_oa_against_target_with_total_cover_forbidden` | LoS/cover-наследование от `can_perform_against` именно на OA-API |
| OA-G007 | `test_oa_target_out_of_reach_forbidden` | если handler по ошибке вызвал OA с target_id, до которого 10 фт и reach 5 фт |

`test_move_triggers_provoked_and_handler_executes_oa` — приемлемый интеграционный тест: реальный `MoveAction`, реальный `InMemoryEventBus`, реальная подписка. Mockup только на «политике handler'а» (что разрешено для MVP — настоящая политика придёт с `ActionRegistry`/Encounter в этапе F).

---

## 5. Сводный TODO

| ID | Sev | Файл | Что сделать |
|----|-----|------|-------------|
| **OA-R001** | **S1** | `opportunity_attack.py` | Запретить `AttackKind.RANGED` в `can_perform_against` (или `execute`); добавить тест OA-G001 |
| OA-R003 | S2 | `opportunity_attack.py` | Добавить проверку `actor.is_alive` в `can_perform` (или зафиксировать инвариант явно); тест OA-G003 |
| OA-A001 | S2 | `docs/ACTIONS.md` §6/§7 | Зафиксировать контракт пары `_check_economy`/`_spend_economy` как hook'ов для reaction-action'ов |
| OA-A002 | S2 | `opportunity_attack.py` | Комментарий-якорь «любое расширение `AttackAction.execute` должно проверяться против reaction-режима»; пост-MVP — `_perform_one_attack` |
| OA-R002 | S2 | `opportunity_attack.py` (docstring) | Зафиксировать «`you can see` ⇒ `line_of_sight` в MVP» |
| OA-R004 | S2 | `tests/...` | Тест OA-G004 (helped_against потребление reaction'ом) |
| OA-G002/005/006/007 | S2 | `tests/...` | Регресс-тесты — добавить к существующему файлу |

**Итог.** E6 — готов к merge при условии фикса OA-R001 (нарушение книжного правила «one melee attack»). Всё остальное — улучшения качества, не блокеры.

---

## Применённые фиксы (2026-05-21)

**S1 — закрыто:**

* **OA-R001** — PHB-2024 стр. 22: «one **melee** attack».
  `OpportunityAttack.can_perform_against` переопределён: возвращает
  `Forbidden(CUSTOM, "opportunity attack must be melee")` при
  `params.kind != AttackKind.MELEE`. `execute` страхует случай прямого
  вызова через `RuntimeError`. Два теста:
  * `test_oa_against_ranged_kind_is_forbidden` — can_perform_against
    Forbidden;
  * `test_oa_execute_ranged_params_raises` — execute RuntimeError.

**Отложено (S2):**

- **OA-A001 / OA-A002** — формализация контракта hooks `_check_economy` /
  `_spend_economy` и риск регрессий при будущих ACTION-only расширениях
  `AttackAction.execute` (Extra Attack). Документация в коде есть;
  явный «контракт hooks» — пост-MVP.
- **OA-R002 / OA-R003** — комментарии-якоря «`you can see` ⇒ LoS» и
  `is_alive` в can_perform OA. Защиты в текущей цепочке (Move
  фильтрует) хватает; явные проверки — после Encounter.
- **OA-R004** — тест на «`helped_against` срабатывает при OA».
  Маловероятный сценарий; добавим если он будет в реальной геймплейной
  ситуации.

**Цифры:** test_opportunity_attack.py: 13 passed (+2); общее 605 passed.

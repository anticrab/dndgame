# Аудит 13: Encounter (этап F)

**Автор:** Maxim Lokotkov
**Дата:** 2026-05-22
**Под ревью:**

- `docs/ENCOUNTER.md`
- `src/dnd/application/engine/encounter.py`
- `src/dnd/application/dto/initiative.py`
- `src/dnd/domain/values/faction.py`
- `src/dnd/application/dto/engine_event.py` (новые `InitiativeRolled`, `RoundStarted`/`RoundEnded`, `TurnStarted`/`TurnEnded`, `EncounterEnded`)
- `tests/unit/application/test_encounter.py`

**Прогон тестов:** `pytest tests/unit/application/test_encounter.py -v` — 33/33 PASSED.

**Не оценивалось** (по тех. заданию): death saves, save/restore (SaveRepository), подкрепления, длительности эффектов.

---

## 1. Резюме

Этап F **архитектурно корректен и закрывает MVP-контракт** ENCOUNTER.md §1–8: инициатива, lifecycle, очистка стоек, сброс реакций раз в раунд, условие победы по фракциям, политика реакций. Тесты честно покрывают tie-break (total → d20 → dex → insertion), пропуск мёртвых, событийную последовательность `InitiativeRolled → RoundStarted → TurnStarted → ... → TurnEnded → RoundEnded → RoundStarted(n+1)`, отписку policy после `EncounterEnded`. Семантика EventBus FIFO (ENGINE.md §5.2) уважается: `_unsubscribe_provoked()` отрабатывает корректно даже если вызывается из обработчика — `InMemoryEventBus` откладывает отписку до межсобытийного зазора.

**S0-блокеров нет.** Все находки — S1/S2 (надёжность, контрактная защита, отсутствующие тесты).

**Ключевые S1:**

- **EN-A001 (S1)** — `reaction_policy` вызывается синхронно из `_on_provoked` без защиты от рекурсии и без try/except: если policy сама вызовет `Encounter.start_turn()`/`end_turn()` либо бросит — состояние боя ломается / шина проглатывает исключение и реакция «теряется» молча.
- **EN-A002 (S1)** — `Encounter.start()` не проверяет «обе воюющие стороны живы»: формально допустимо запустить бой, где все MONSTERS уже мертвы. Первый `end_turn` закроет бой, но между `RoundStarted(1)` и `EncounterEnded` подписчики увидят TurnStarted у actor'а несуществующего противника.
- **EN-A003 (S1)** — `participants` сохраняется по ссылке (комментарий явно допускает добавление подкреплений), но `initiative_order` фиксирован при `start()`, а `_check_end_condition` смотрит на актуальный dict. В результате добавление живого союзника в `PARTY` после `start()` блокирует `EncounterEnded`, не давая ему ход. Поведение нигде не покрыто тестом.
- **EN-A004 (S1)** — `helped_against` / `helped_by` НЕ сбрасываются на старте хода owner'а, хотя docstring `Creature.helped_against` явно ожидает этого от Encounter («Encounter сбросит на старте следующего хода owner'а»). Контракт документации расходится с реализацией.
- **EN-R001 (S1)** — `movement_remaining_ft = actor.speed_ft` напрямую, без учёта condition-overrides. PHB-2024 стр. 22 / стр. 367 (Paralyzed/Stunned/Unconscious) требует speed=0. На MVP это «известно отложенное», но в `start_turn` нет даже хука для этого (например, `actor.effective_speed_ft`), — будущее исправление потребует менять Encounter.

---

## 2. Архитектура — S0/S1/S2

### EN-A001 (S1) — нет защиты `reaction_policy` от рекурсии и исключений

**Что.**

```python
def _on_provoked(self, event: OpportunityAttackProvoked) -> None:
    if self._state.concluded:
        return
    self._reaction_policy(event, self)
```

Policy получает `self` (Encounter) и может теоретически вызвать `start_turn()` / `end_turn()` / повторно подписаться / бросить исключение. Защиты нет:

1. **Рекурсия через lifecycle.** Если policy ошибочно дёрнет `encounter.start_turn()`, индекс хода сместится, `current_turn_index` укажет не на того actor'а, и продолжение боя из «верхнего» цикла приведёт к расхождению.
2. **Рекурсия через events.** Policy выполняет OA → атака публикует свои события (`AttackRolled`, `DamageDealt`) → если урон валит цель, валидно бы было закрыть бой ровно здесь. Сейчас `_check_end_condition` вызывается **только из `end_turn`**, то есть до конца хода атакующего бой остаётся «формально активным», и любая новая провокация в тот же хвост дисптача всё ещё будет роутиться в policy. На MVP **не катастрофа** (есть `concluded`-guard), но контракт не задокументирован.
3. **Исключение в policy.** `InMemoryEventBus._dispatch_one` ловит исключения в подписчиках (§5.2 п.4) — `_on_provoked` это просто один из подписчиков. Поэтому исключение policy будет молча проглочено, а **реакция считается несделанной** (атрибут `b.reaction_used` останется как было). Это противоречит ожиданию вызывающего «policy либо отреагировала, либо нет — но я узнаю, если что-то сломалось».

**TODO.**

- В docstring `ReactionPolicy` зафиксировать контракт: «policy НЕ должна вызывать lifecycle-методы Encounter; разрешено только читать состояние и исполнять action-объекты». Лучше — Protocol с `__call__` и комментарием.
- Обернуть вызов policy в `try/except` с явным логированием и тегом события (например, `tags=("reaction_policy_error",)`) — иначе диагностика «почему враг не сделал OA» = невозможна.
- Тест `test_reaction_policy_exception_is_logged_and_does_not_break_encounter`.

### EN-A002 (S1) — `start()` не проверяет, что бой осмыслен

**Что.** В `start()` нет вызова `_check_end_condition` после публикации `RoundStarted(1)`. Если на момент `start()` у одной из воюющих фракций все participants мертвы (например, после off-screen урона), `InitiativeRolled` и `RoundStarted(1)` опубликуются, и только при первом `end_turn` бой закроется. UI / лог увидят «нулевой» бой с пустыми ходами.

**Оценка.** Не S0, потому что состояние остаётся консистентным и бой всё-таки кончится. Но событийная картина грязная, и для подкреплений / снапшотов это создаст ложные транзакции.

**TODO.**

- В `start()` после `_begin_round(1)` вызвать `_check_end_condition()`; если бой завершён — `EncounterEnded` с `round_number=1` и `survivors`. Тест `test_start_ends_immediately_if_one_side_already_wiped`.

### EN-A003 (S1) — подкрепления влияют на `is_concluded`, но не ходят

**Что.** Конструктор сознательно держит `_participants` по ссылке («вызывающий может добавлять participants по ходу боя»). При этом:

- `initiative_order` строится один раз в `start()` и больше не меняется;
- `_check_end_condition` итерирует **актуальный** `_participants` (`is_alive`-фильтр) — то есть новый PARTY-pet, добавленный в раунде 2, сразу учитывается как «живой со стороны PARTY»;
- `_begin_round` тоже итерирует актуальный dict — новый pet получит `reaction_used=False` корректно;
- но в `initiative_order` его нет — он **не ходит**.

Результат: можно «затащить» в бой призывного компаньона, который заблокирует `EncounterEnded`, но сам бездействует.

**TODO.**

- Либо запретить мутации (`MappingProxyType` или копия в `__init__`), и сделать явный API `add_participant(creature, faction, initiative=...)` (пост-F4).
- Либо явно задокументировать в ENCOUNTER.md §1, что подкрепления-в-`_participants` участвуют в `is_concluded`, но не в `initiative_order`, и завести задачу F5 «reinforcements proper». Сейчас комментарий в коде есть, но в документе — нет.
- Тест `test_participant_added_after_start_blocks_end_condition_but_does_not_act` (фиксирует текущее поведение, чтобы оно не «отвалилось» молча).

### EN-A004 (S1) — Encounter не сбрасывает Help-якорь

**Что.** `Creature.helped_against` имеет docstring:

> Также Encounter сбросит на старте следующего хода owner'а (если не использовал).

В `start_turn` сбрасываются только `combat_stances`. `helped_against` и парный `helped_by` (см. аудит 11 HS-R001) — нет. Помощь будет «висеть» до следующей атаки или до конца боя.

**Оценка.** Контракт документации расходится с кодом. Это S1 (правило книги — Help длится «until the start of your next turn or until you have advantaged an attack»).

**TODO.**

- В `start_turn` после очистки `combat_stances`:
  ```python
  if actor.helped_against is not None:
      # сбрасываем парную ссылку у ally
      ally = self._participants.get(actor.helped_against)  # это TARGET, не ally — см. ниже
      ...
      actor.helped_against = None
  ```
  Поле семантически «кому я помогаю» хранится у helper'а, и парное `helped_by` — у ally. Корректная очистка по PHB-2024 стр. 22 — на старте хода **helper'а**: если ally к этому моменту не использовал помощь, аннулировать её у обоих.
- Альтернатива (проще): в `start_turn(helper)` обнулить `helper.helped_against` и пройтись по `_participants` сбросив `helped_by == helper.id`. Дешевле выделить helper-метод `_clear_pending_help(helper)`.
- Тест `test_start_turn_clears_owner_help_grant`.

### EN-A005 (S2) — TurnContext.disengaged дублирует CombatStance.DISENGAGED

**Что.** `TurnContext.disengaged: bool` и `Creature.combat_stances` содержит строку `"disengaged"`. На старте хода `start_turn` очищает stance, но создаёт новый ctx с `disengaged=False` (по умолчанию). Дальше `DisengageAction` должен поставить **оба** поля? В коде E4 — ставит только ctx. То есть `combat_stances` после Disengage НЕ содержит `"disengaged"` — а Encounter всё равно его «чистит» (no-op). Двойная правда без синхронизации.

**Оценка.** Архитектурный смелл, не баг. Stance-маркер в `combat_stances` нужен для **межходовой** видимости (другие existo читают, что цель в Dodge для применения disadvantage). Disengage наоборот — флаг текущего хода. Перепутана семантика.

**TODO.**

- Решить, где «правда» по Disengage: либо stance (читается из существа), либо ctx (читается только в текущем ходу). В TARGETING/MOVE сейчас Disengage влияет внутри хода — значит ctx. Тогда из `_STANCES_CLEARED_ON_TURN_START` строку `"disengaged"` надо убрать (она и так никогда не выставляется в combat_stances), либо обновить DisengageAction, чтобы он писал в обе.
- Пометить в ENCOUNTER.md §3.1 точно, что Disengage — ctx-only.

### EN-A006 (S2) — отписка `_unsubscribe_provoked` не идемпотентна снаружи

**Что.** Если вызывающий **переиспользует** Encounter после `EncounterEnded` (например, в тесте `apply_restart`), подписка пересоздана не будет. Сейчас `start()` нельзя вызвать второй раз — `EncounterAlreadyStartedError`. Этот случай корректно закрыт. Просто стоит зафиксировать в docstring: «Encounter — single-shot; для нового боя — новый объект».

**TODO.**

- В docstring класса `Encounter` добавить строку «single-shot». Сейчас это неявно следует из `start()` guard.

### EN-A007 (S2) — `_check_end_condition` строит лишние списки

**Что.** На каждом `end_turn` (в бою это десятки вызовов) собирается полная карта `alive_by_faction` и `survivors`. На MVP-размерах (≤10 participants) — pure-cosmetic.

**TODO.** Не трогать на MVP. Если профайл покажет проблему — посчитать early-exit «есть >1 не-NEUTRAL живых фракций → return False».

---

## 3. Правила «Книга Игрока 2024» — S0/S1/S2

### EN-R001 (S1) — movement_remaining_ft не уважает condition-overrides

**Книга.** PHB-2024 стр. 367: Paralyzed, Stunned, Unconscious, Petrified, Restrained, Grappled — все накладывают `speed = 0` или ограничивают перемещение. Также Prone оставляет speed, но удваивает стоимость движения.

**Что в коде.**

```python
movement_remaining_ft=actor.speed_ft,
```

— берётся **базовая** скорость существа без оглядки на `actor.conditions`. ConditionRegistry уже знает про Paralyzed/Stunned/Unconscious (см. `builtin.py`), но `provides_modifiers` для них не публикует `MOVEMENT_SPEED`-override. Encounter, в свою очередь, никак не запрашивает «эффективную» скорость.

**Воспроизведение.** Тест: наложить `paralyzed` через `condition_service.apply` (или прямо `actor.apply_condition(PARALYZED)`), потом `start_turn` — `ctx.movement_remaining_ft == actor.speed_ft` (30), хотя по правилам должно быть 0. MoveAction съест 30 футов без сопротивления.

**Оценка.** **Известный отложенный** дефект: Modifier-инфраструктура условий ещё не покрывает `speed`. Но в Encounter нет даже placeholder'а под это, и комментарий «учтём в Modifier-этапе» отсутствует. С точки зрения этапа F — S1 (правило прямо нарушается).

**TODO.**

- В `start_turn` заменить:
  ```python
  movement_remaining_ft=self._effective_speed_ft(actor),
  ```
  где `_effective_speed_ft` пока возвращает `actor.speed_ft`, но имеет TODO-комментарий со ссылкой на условия `INCAPACITATED`/`PARALYZED`/`STUNNED`/`UNCONSCIOUS`/`RESTRAINED`/`GRAPPLED` и на `ModifierTargetKind.MOVEMENT_SPEED` (когда появится).
- Минимально достаточный fix-сейчас: проверить `actor.has_condition(INCAPACITATED)` и обнулить скорость, либо `actor.is_at_zero_hp` (уже выставляет `skipped=True`, но ctx всё равно отдаёт speed).
- Тест `test_paralyzed_actor_has_zero_movement_in_turn_context` — после интеграции в ConditionService.

### EN-R002 (S2) — tie-break фиксирует политику, которой нет в PHB

**Книга.** PHB-2024 стр. 22 (Инициатива): «If a tie occurs, the GM decides the order among tied GM-controlled creatures, and the players decide the order among themselves». То есть **формально книга отдаёт tie-break DM'у**.

**Что в коде.** Жёсткая политика: total → d20_raw → dex_score → insertion_order. Это разумный детерминированный fallback для отсутствия DM, но книга его не предписывает.

**Оценка.** Уже зафиксировано в задании («книга оставляет DM'у — мы фиксируем total→d20→dex→insertion»). S2: достаточно явного комментария в ENCOUNTER.md §2 «MVP-конвенция, отличается от книги по букве».

**TODO.**

- В ENCOUNTER.md §2 добавить строку: «Книга оставляет tie-break DM'у; в MVP без live-DM мы используем детерминированную политику total→d20→dex→insertion. Это документировано как наша конвенция, не как правило книги».

### EN-R003 (S1) — `d20_raw` fallback to 0 ломает tie-break при экзотических роллерах

**Что.**

```python
d20_raw = result.d20_raw if result.d20_raw is not None else 0
```

`d20_raw is None` для **не-d20**-бросков (DiceRoller возвращает None, когда выражение не `d20+mod`). Для `RollPurpose.INITIATIVE` сейчас всегда `d20+dex_mod`, так что None быть не должно. Но если завтра кто-то добавит «инициатива на k% + DEX» (мод, кастом), tie-break начнёт сваливать всех в 0 и ломаться невидимо.

**Оценка.** S2. Безопаснее упасть assertEqual'ом: «инициатива обязана быть d20-броском».

**TODO.**

- Заменить fallback на:
  ```python
  assert result.d20_raw is not None, "INITIATIVE must be d20-based"
  d20_raw = result.d20_raw
  ```
  Или конкретное исключение `RuntimeError("INITIATIVE roll missing d20_raw")`.

### EN-R004 (S1) — reaction обновляется на `_begin_round`, но не для существ, попавших в бой после start

**Что.** `_begin_round` итерирует `_participants.values()` (актуальный dict), значит новый pet получит `reaction_used=False`. **Это правильно.** Но если pet добавлен **в середине** раунда (не на _begin_round), его `reaction_used` остаётся тем, чем был на момент добавления. Если pet сделал OA в раунде N, а в раунде N+1 (когда `_begin_round` ещё не вызывался — он же в середине раунда) его атакуют — реакция не сбросится до конца текущего раунда. На MVP — без подкреплений неактуально.

**Оценка.** Зависит от EN-A003. S2.

**TODO.** Решается тем же фиксом, что EN-A003 (явный `add_participant` со сбросом reaction_used).

### EN-R005 (S2) — `EncounterEnded.winners: str | None` вместо `Faction | None`

**Что.** Поле объявлено как `str | None`, заполняется `winners.value`. Это даёт pydantic-сериализацию, но теряет тип на стороне подписчиков: они должны делать `Faction(event.winners)` для match'а. ENCOUNTER.md §5 явно показывает `winners: Faction | None`.

**Оценка.** S2, документ расходится с кодом. Pydantic поддерживает enum-поля; явный StrEnum сериализуется как строка автоматически, без потери типа.

**TODO.**

- Заменить тип поля на `Faction | None`:
  ```python
  winners: Faction | None
  ```
  ENCOUNTER.md §5 уже правильный; синхронизировать код. Сериализация остаётся как строка (StrEnum). Тест `test_encounter_ends_when_one_faction_wiped` достаёт `.value` — поменять на `is`.

### EN-R006 (S2) — Massive damage / death saves отложены (явно)

**Книга.** PHB-2024 стр. 27 — Massive damage. В коде `take_damage` уже возвращает `killed_outright`, но Encounter этот флаг не читает — для NPC «0 HP = is_alive False» и так работает. Для PC death saves отложены до Character (ENCOUNTER.md §3.4). **OK для MVP, явно зафиксировано.**

**Оценка.** S2 — нота, не баг. ENCOUNTER.md §3.4 это покрывает.

**TODO.** Нет действий, отметка для трекинга.

---

## 4. Пропущенные тесты (S2 «G»)

- **EN-G001** — два полных раунда подряд: проверить, что `RoundEnded`/`RoundStarted` идут парами в правильном порядке для раундов 1→2→3 (сейчас `test_new_round_resets_reaction_used` доходит до раунда 3, но не валидирует последовательность событий целиком). Цель: `[RoundStarted(1), TurnStarted(a,1), TurnEnded(a,1), TurnStarted(b,1), TurnEnded(b,1), RoundEnded(1), RoundStarted(2), ...]`.

- **EN-G002** — `start()` при «уже-выкошенной» стороне (EN-A002): все MONSTERS мертвы до start. Ожидаемо после фикса: `EncounterEnded` сразу после `RoundStarted(1)`, без `TurnStarted`.

- **EN-G003** — добавление participant в `_participants` после `start()` (EN-A003): фиксирует, что новый участник не получает хода, но влияет на `is_concluded`. Документирует поведение.

- **EN-G004** — `start_turn` для actor'а, упавшего в 0 HP во время чужого хода: уже есть `test_start_turn_skipped_for_zero_hp_actor`, но **нет** теста на «вызывающий забыл `end_turn` после skipped TurnStarted». Сейчас вызов `start_turn` второй раз без `end_turn` НЕ падает — он построит новый ctx для того же actor'а, опубликует второй `TurnStarted`, и фактически потеряет первый. Это потенциальный smell — `start_turn` неидемпотентен и не защищён от двойного вызова.

- **EN-G005** — `reaction_policy` бросает исключение: проверка, что бой продолжается, но событие об ошибке (или хотя бы лог) фиксируется. Связан с EN-A001.

- **EN-G006** — `helped_against` сбрасывается на старте хода owner'а (после фикса EN-A004).

- **EN-G007** — `RoundEnded` публикуется **ровно один раз** на каждый wrap; косвенно покрыто, но прямой ассерт `Counter(types)["RoundEnded"] == 2 после двух раундов` отсутствует.

- **EN-G008** — `EncounterEnded` публикуется ровно один раз и состояние `concluded=True` идемпотентно к повторному вызову `_check_end_condition` (защита на случай рефакторинга, который кто-то сделает).

- **EN-G009** — после Paralyzed/Unconscious `ctx.movement_remaining_ft == 0` (после фикса EN-R001).

- **EN-G010** — `start_turn` дважды подряд без `end_turn`: фиксирует либо ошибку (предпочтительно), либо явно текущее «no-op replace». Сейчас — silently replace.

---

## 5. Сводный TODO по приоритету

### P1 — обязательны до закрытия этапа F (S1)

- **EN-A001** — задокументировать контракт `ReactionPolicy` (не вызывать lifecycle), обернуть вызов в `try/except` с логированием.
- **EN-A002** — `_check_end_condition()` в `start()` после `_begin_round(1)`.
- **EN-A004** — сброс `helped_against` / `helped_by` в `start_turn` (синхронизация с docstring `Creature`).
- **EN-R001** — placeholder `_effective_speed_ft(actor)` в `start_turn` + TODO-якорь на интеграцию с условиями.

### P2 — желательны (S1/S2 на стыке)

- **EN-A003** — явный API `add_participant(...)` или копия `_participants` в `__init__`; фиксация в ENCOUNTER.md §1.
- **EN-A005** — выровнять Disengage: `ctx.disengaged` vs `combat_stances` (одно место правды).
- **EN-R005** — `EncounterEnded.winners: Faction | None` (синхронизация с ENCOUNTER.md §5).
- **EN-R003** — fallback `d20_raw=0` → строгая проверка `is not None`.

### P3 — косметика и трекинг (S2)

- **EN-A006** — docstring «Encounter — single-shot».
- **EN-A007** — early-exit в `_check_end_condition` (после нагрузочных профайлов, не сейчас).
- **EN-R002** — комментарий в ENCOUNTER.md §2 про DM-tie-break vs нашу детерминированную политику.
- **EN-R006** — отметка «Massive damage / death saves — Character этап» уже есть, не трогать.

### G — добавить тесты

- EN-G001 … EN-G010 (см. §4). Минимально-обязательные после P1: G002, G005, G006, G009 — они проверяют именно P1-фиксы.

---

## Приложение А — заметки по EventBus / FIFO

ENGINE.md §5.2 (FIFO, отложенные подписки) уважается:

- `_unsubscribe_provoked()` из `_check_end_condition` вызывается из обработчика `_on_provoked` либо напрямую из `end_turn`. В первом случае `InMemoryEventBus` откладывает unsubscribe до межсобытийной паузы (`_pending_subscription_ops`) — правильно. Во втором — синхронно, тоже правильно.
- `_on_provoked` сам по себе — подписчик, и его исключение перехватывается шиной (`_dispatch_one` → log.exception). Это и есть «риск EN-A001»: ошибка policy замаскирована шиной.
- Порядок публикаций в `start()`: `InitiativeRolled` → `RoundStarted(1)`. Это правильный порядок (события идут в очередь и диспатчатся последовательно). `TurnStarted` публикуется только при явном `start_turn` — соответствует §3 ENCOUNTER.md.

## Приложение Б — контракт `TurnContext` vs ACTIONS.md §3

`Encounter.start_turn` создаёт `TurnContext` со всеми полями из ACTIONS.md §3:

- `actor_id` ✓
- зависимости (`battlefield`/`dice_roller`/...) ✓
- `movement_remaining_ft=actor.speed_ft` — **частично** (см. EN-R001).
- `round_number`, `turn_number_in_round` ✓
- экономика (`action_used` и т.п.) — по умолчанию False, корректно для нового хода.
- `participants` ✓ (по ссылке — связано с EN-A003).
- `reaction_used` — **в ctx по умолчанию False**, но действующее состояние реакции хранится в `Creature.reaction_used` (см. аудит 12 OA-A001). Дублирование не вредит — Action'ы читают `actor.reaction_used`, не `ctx.reaction_used`.

Контракт соблюдён.

---

## Применённые фиксы (2026-05-22)

**S1 — закрыто:**

* **EN-A001** — `_on_provoked` обёрнут в `try/except` с `_log.exception`.
  Docstring зафиксировал контракт ReactionPolicy («не вызывать
  lifecycle-методы Encounter; разрешено только читать state и исполнять
  Action'ы»). Тест `test_reaction_policy_exception_does_not_break_encounter`.
* **EN-A002** — после `_begin_round(1)` в `start()` вызывается
  `_check_end_condition()`; если бой осмыслен только формально (одна
  сторона мертва до начала) — `EncounterEnded` публикуется сразу.
  Тест `test_start_ends_immediately_if_one_side_already_wiped`.
* **EN-A003** — конструктор делает `dict(participants)` / `dict(factions)`
  (неглубокая копия), убирая фичу «подкрепления по ссылке». В docstring
  явно сказано: добавление participants после `start()` в MVP не
  поддерживается; будущий API `add_participant(...)` — пост-F4.
* **EN-A004** — `start_turn(actor)` вызывает `_clear_pending_help(actor)`,
  который пробегается по participants и сбрасывает `helped_against`/
  `helped_by` у всех ally, чей `helped_by == actor.id`. Соответствует
  PHB-2024 стр. 22 «until the start of your next turn».
  Тест `test_start_turn_clears_pending_help_grants`.
* **EN-R001** — `_effective_speed_ft(creature)`: возвращает 0 при
  Incapacitated/Paralyzed/Stunned/Unconscious и при `is_at_zero_hp`.
  TODO в docstring на будущую интеграцию с ModifierApplier через
  ModifierTargetKind.SPEED. Параметризованный тест
  `test_paralyzed_actor_has_zero_movement` × 4 condition.

**S2 — закрыто:**

* **EN-R003** — fallback `d20_raw or 0` заменён на явный
  `RuntimeError("INITIATIVE roll must be d20-based")`.
* **EN-R005** — `EncounterEnded.winners: Faction | None` (вместо
  `str | None`). Pydantic StrEnum сериализуется как строка
  автоматически. Тест `test_encounter_ends_when_one_faction_wiped`
  обновлён на `winners is Faction.PARTY`.
* **EN-A006** — docstring Encounter дополнен пометкой «single-shot».

**Отложено (по плану):**

* **EN-A005** — Disengage `ctx.disengaged` vs `combat_stances`
  consistency. Не критично для MVP; оба пути сейчас не пересекаются
  семантически (ctx-only для решения о провокации, stance — для лога).
* **EN-A007** — early-exit в `_check_end_condition`. Только после
  профилировки.
* **EN-R002** — комментарий в ENCOUNTER.md §2 про DM-tie-break.
  Применю отдельной правкой в документации.
* **EN-G001, G007, G008, G010** — желательные G-тесты на FIFO
  последовательность и идемпотентность. Добавим в следующих циклах.

**Цифры:**

* pytest:   646 passed (+8 за фиксы)
* test_encounter.py: 41 passed (+8)
* ruff:     All checks passed
* mypy:     Success: no issues found in 76 source files
* coverage: 97.48%

**Ключевая находка (P1):** EN-A001 — без try/except любая ошибка
политики молча проглатывалась шиной, и реакция «терялась» без следов;
это превращало диагностику AI/handler-багов в кошмар. Чистое
архитектурное прикрытие, не book-rule, но без него отладка боя
дорогая.

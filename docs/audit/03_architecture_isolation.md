# Audit 03: архитектурная изоляция

Контекст. Аудит выполнен на коммите состояния `src/dnd/`, в котором реально
существуют только три «живых» модуля: `domain/values/ability.py`,
`domain/values/dice.py`, `application/ports/rng.py`,
`infrastructure/rng/{real_rng,scripted_rng}.py` и заглушка
`interfaces/cli/app.py`. Остальная часть дерева — пустые `__init__.py`.
Поэтому проверка инвариантов разделена на две части: (а) кода, который
уже есть и должен соблюдать инварианты прямо сейчас; (б) документации,
которая описывает, как инварианты будут соблюдаться в коде, появляющемся
далее. Любая «дыра в дизайне» в документе — это будущая дыра в коде,
поэтому оценивается одинаково строго.

---

## Резюме

- Нарушений направления зависимостей: **1** (S1).
- Нарушений multi-actor инвариантов: **0 в коде**, **2 пробела в дизайне** (S2).
- Нарушений локализационного инварианта: **1** (S1).
- Прочих рисков изоляции (encapsulation, тестируемость, composition root,
  жизненный цикл реестров, конфиг): **8** (S1/S2).

Итого 12 находок: 0 S0, 4 S1, 8 S2.

> Шкала: S0 — блокер; S1 — ломающее, чинить до следующего вертикального
> среза; S2 — улучшение, можно отложить, но решение должно быть
> зафиксировано.

---

## Найденные проблемы

### A-001. `domain` импортирует из `application` (порт RNG)

**Тип:** dependency direction.
**Серьёзность:** S1.
**Где:** `src/dnd/domain/values/dice.py:33`:

```python
from dnd.application.ports.rng import RNG
```

И ровно та же зависимость — в подписи метода `DiceExpr.roll(self, rng: RNG, ...)`.

**Суть.** Декларация в `ARCHITECTURE.md` §0:
«Направление зависимостей: `interfaces → application → domain ← infrastructure`».
Доменный модуль `dice.py` импортирует тип из `application/ports/`. Это
прямое нарушение направления. Чисто гексагональная архитектура помещает
**входящие порты** (driver) в `application`, а **исходящие** (driven) —
в `domain`, чтобы domain не зависел от application. RNG — исходящий порт
(driven side: правила «дёргают наружу» за случайностью), значит его
правильное место — `domain/`.

Это не «теоретическая придирка»: уже сейчас тесты `test_dice.py`
импортируют `ScriptedRNG` из `infrastructure`, но также вынуждены тянуть
`application/ports/rng.py` через транзитивный импорт `dice.py` — и в
будущем любая попытка раздвинуть `domain` и `application` (например,
вынести `domain` в отдельный пакет/инсталляцию) сломается.

**Рекомендация (рекомендованный путь — №1).**
1. **Перенести `rng.py` в `domain/ports/rng.py`.** Это согласуется с
   гексагональной нотацией: driven-port — в domain, driver-port
   (`UserInterface`, репозитории) — в application. Так домен остаётся
   автономным.
2. Альтернатива (если хочется сохранить все порты в одной директории):
   объявить **локальный `Protocol`** в `domain/values/dice.py`:
   ```python
   class _RngLike(Protocol):
       def roll(self, sides: int) -> int: ...
   ```
   и не импортировать `application.ports.rng.RNG`. Тогда RNG-порт в
   `application` остаётся «централизованным реестром портов», но
   `domain` не зависит от него. Хуже первого варианта, потому что
   множит протоколы.
3. Худший вариант — «зафиксировать как сознательное послабление». Тогда
   нужно: (а) явно прописать это в `ARCHITECTURE.md` §0, (б) обновить
   `ADR/0001`, (в) гарантировать, что `application/ports/` физически
   не зависит ни от чего, кроме stdlib (сейчас выполняется).
   Этот вариант ломает «чистоту схемы», но текущая структура
   `application/ports/__init__.py` действительно ничего не импортирует.

Выбор должен быть зафиксирован отдельным ADR (например, `ADR-0003 — Где
живут порты`). До этого код реально нарушает заявленную стрелку.

---

### A-002. Локализация утекает в `domain`: `Ability.label_ru`

**Тип:** invariant violation (i18n).
**Серьёзность:** S1.
**Где:** `src/dnd/domain/values/ability.py:18-29`:

```python
class Ability(StrEnum):
    ...
    @property
    def label_ru(self) -> str:
        return _RU_LABELS[self]

_RU_LABELS = {
    Ability.STR: "Сила",
    ...
}
```

И затем используется в исключении (`ability.py:54`): `f"{self.ability.label_ru}: ..."`.

**Суть.** В `I18N.md` §1 чётко зафиксировано: «UI-строки … `src/dnd/i18n/locales/...`»,
«Технические идентификаторы (`goblin`, `attack`, `cure_wounds`) — **нет** [не локализуем]»,
а также `ARCHITECTURE.md` §0: «`domain` не знает ни про SQLite, ни про CLI, ни
про YAML, ни про **i18n**». Базовый язык UI — английский
(`I18N.md` §1). Метод `label_ru` нарушает три правила сразу:

1. Жёстко зашит **только русский**, при том что базовая локаль —
   английская.
2. Содержит UI-строку **в domain** — это i18n-знание.
3. Сообщение об ошибке (`ValueError`) на русском, тогда как
   `I18N.md` §1 явно говорит: «Лог технических ошибок и трейсбеки —
   английский».

**Рекомендация.**
- Из `Ability` выпилить `label_ru` (и `_RU_LABELS`). Идентификатор
  `Ability.STR` — это и есть техническое имя, его в UI оборачивать
  через `_("Strength")`/ключи локализации в interfaces-слое.
- `__post_init__` в `AbilityScore` — заменить русский текст на
  английский: `f"{self.ability}: {self.score} is out of range 1..30"`.
  (Тексты исключений не локализуются; они в логах для разработчика.)
- Если очень нужно человекочитаемое имя — добавить метод `label(translator)`
  на уровне `interfaces`/`application`, который **получает** translator
  как параметр и резолвит ключ `f"ability.{ability.value}.label"`.

Без этой правки в `domain` появится прецедент «локализовать прямо здесь»,
и потом такие же `name_ru`/`description_ru` начнут расползаться по
`Monster`/`Spell`/`Item`.

---

### A-003. `infrastructure/rng/scripted_rng.py` несёт русскоязычные строки исключений

**Тип:** invariant violation (i18n, мягкая).
**Серьёзность:** S2.
**Где:**
- `infrastructure/rng/scripted_rng.py:22` — `"ScriptedRNG: брошены все запланированные кости"`.
- `infrastructure/rng/scripted_rng.py:27` — `f"ScriptedRNG: значение {value} вне диапазона 1..{sides}"`.
- `infrastructure/rng/real_rng.py:18` — `f"число граней должно быть ≥ 1, получено {sides}"`.
- `domain/values/dice.py:80–95` — `"число костей должно быть ≥ 1"`, `"keep={...} вне диапазона ..."` и т.п.

**Суть.** Это `ValueError`/`IndexError` для разработчика, не для игрока,
но `I18N.md` §1 классифицирует все технические сообщения об ошибках как
**английские** (см. таблицу: «Лог технических ошибок и трейсбеки — нет
[не локализуем], английский»). Сейчас они русские. Не критично, но
противоречит явно зафиксированному правилу.

**Рекомендация.** Перевести все `raise ValueError/RuntimeError/IndexError`-сообщения
в коде (`domain`, `application`, `infrastructure`) на английский. Это
дешёво и снимает категориальное «русско-английское» смешение.
Альтернатива — явно отредактировать `I18N.md` §1: «сообщения исключений
домена пишутся на русском как часть учебного материала». Один из двух
вариантов нужно зафиксировать.

---

### A-004. `application/ports/rng.py` корректен как протокол, но **методы без тела**

**Тип:** соблюдение Protocol-контракта.
**Серьёзность:** S2.
**Где:** `application/ports/rng.py:18–24`:

```python
@runtime_checkable
class RNG(Protocol):
    def roll(self, sides: int) -> int:
        """..."""

    def random(self) -> float:
        """..."""
```

Тела методов — только docstring. С точки зрения PEP 544 это валидно
(тело `Protocol`-метода никогда не вызывается). Но если кто-то по
ошибке вызовет `RNG.roll(x)` на самом `Protocol`-классе (минуя реализацию)
— вернётся `None`, что замаскирует баг. Также `runtime_checkable` без
заявленных абстрактных методов даёт «слабую» проверку — `isinstance(obj, RNG)`
вернёт True для любого объекта с двумя названиями.

**Рекомендация.** Можно оставить как есть — это микро-замечание. Если
хочется усилить — тело каждого метода поменять на `raise NotImplementedError`
(но тогда теряется `@runtime_checkable`-семантика). Решение остаётся за
архитектором; зафиксировать выбор в комментарии у `RNG`.

---

### A-005. Нет порта `EventBus` / `ContentRepository` / `SaveRepository` / `UserInterface` ни в коде, ни в виде placeholder

**Тип:** missing port.
**Серьёзность:** S2.
**Где:** `application/ports/` содержит только `rng.py` и `__init__.py`. Все остальные
порты, заявленные в `ARCHITECTURE.md` §3 и `ENGINE.md` §1.2, отсутствуют
даже как пустые stub-Protocol'ы.

**Суть.** Сами по себе пустые файлы не нужны; но в roadmap'е (`ROADMAP.md` §9)
multi-actor-инварианты сформулированы императивно: «EventBus — единственный
канал событий», «RNG и DiceRoller — за портами», «UI и БД — за портами».
Когда появится первая реализация, нужно гарантировать, что её делают **через
порт**, а не «срежу прямо в инфраструктуру». Сейчас никто на это не натолкнётся —
дисциплину поддерживает только дисциплина.

**Рекомендация.** При создании первого же модуля, которому нужен новый
порт (`EventBus`, `ContentRepository`, ...), **сначала** создаётся
протокол в `application/ports/` (или `domain/ports/`, см. A-001), и только
потом — реализация. Это можно зафиксировать pre-commit-хуком: «в
infrastructure нельзя создать модуль с именем `*_repository.py`, если в
`application/ports/` нет соответствующего протокола». Сейчас этого
правила нет; нужно поставить.

---

### A-006. Composition root не описан и не реализован

**Тип:** missing infrastructure for invariants.
**Серьёзность:** S1.
**Где:** `interfaces/cli/app.py` (текущий стаб) и `ARCHITECTURE.md` §4
(«DI — простой: руками собрать в `main`»), §7 («`compose_root() → GameEngine, UI`»).

**Суть.** `ARCHITECTURE.md` ссылается на функцию `compose_root()`, которой нет
в коде, и её расположение не указано. В §4 сказано «точка композиции —
`interfaces/cli/app.py`», но в §7 в псевдокоде вызывается
`compose_root()` отдельной функцией. Между этими двумя пунктами есть
расхождение: либо это inline-сборка в `main`, либо отдельный модуль.

**Риски расхождения.**
1. Если композиция останется в `app.py` рядом с typer-командами —
   typer (interfaces) и сборка зависимостей (composition root) смешаются.
   Это утечёт `typer.Context` в место, где собираются доменные сервисы.
2. Тесты не смогут вызвать `compose_root` независимо от typer — придётся
   дублировать DI в `conftest.py`.

**Рекомендация.** Завести модуль `interfaces/cli/composition.py` (или
`application/composition.py`, но тогда interfaces не должен в нём
рулить) с одной функцией:

```python
def compose_root(
    *,
    workdir: Path | None = None,
    rng: RNG | None = None,
    ui: UserInterface | None = None,
) -> GameEngine: ...
```

Все опциональные параметры — точки переопределения для тестов и
будущего LiveDiceRoller/LiveGameMaster. Тогда e2e-тест может собрать
движок с `ScriptedRNG` и `RecordingUI` одной строкой.

Также нужно явно прописать в `ARCHITECTURE.md` §4: «composition root
живёт в `interfaces/cli/composition.py`; `app.py` — только typer-обвязка,
ничего не собирает».

---

### A-007. Реестры плагинов: жизненный цикл и валидация контента не описаны

**Тип:** encapsulation leak (риск глобального состояния).
**Серьёзность:** S1.
**Где:** `ARCHITECTURE.md` §1 (таблица паттернов) — `FeatureRegistry`,
`ConditionRegistry`, `ActionRegistry`, `MonsterAIRegistry`, плюс
`ROADMAP.md` §5: «Реестры (...): YAML ссылается на имя плагина».

**Суть.** Нигде не сказано: (а) реестр — это **глобальный модуль-уровневый
объект**, наполняемый декораторами при импорте, или **экземпляр**, создаваемый
в `compose_root`? (б) кто его создаёт? (в) что происходит, если YAML
ссылается на плагин, которого нет в реестре, — `KeyError` в рантайме или
проверка на загрузке?

Если выберут «глобальный декоратор» — мы получим скрытое глобальное
состояние и порядок-импортов-зависимую инициализацию (классический
антипаттерн питон-плагинов: тесту нужен класс — приходится дёргать
`import dnd.domain.actions.attack`, чтобы декоратор сработал). Это
сразу несовместимо с заявленным DI «руками собрать в main».

**Рекомендация.**
1. Реестр — **экземпляр**, создаётся в `compose_root`. Регистрация —
   явная (через seeder-функцию `register_default_actions(registry)`),
   а не через побочный эффект импорта.
2. На стороне `ContentService` — валидация ссылок YAML → реестр при
   загрузке контента, до старта игры. Ошибка — внятный список «эти
   YAML-сущности ссылаются на плагин X, которого нет в реестре».
3. Зафиксировать в `ARCHITECTURE.md` §1 в строке «Plugin / Registry» —
   именно эту модель.

---

### A-008. Конфигурация: нет порта `ConfigService` или эквивалента

**Тип:** missing port.
**Серьёзность:** S2.
**Где:** `ARCHITECTURE.md` §9, `OPEN_QUESTIONS.md` Q11.

**Суть.** Решено: конфиг в TOML, через `platformdirs`, флаг `--workdir`.
Но не сказано: **кто** его читает, **где** валидируется (`pydantic`-схема?),
**откуда** к нему доступ. Если правила домена вдруг зависят от config
(скажем, `default_distance_metric: chebyshev | one_two_one` — оно уже
описано в `ENGINE.md` §2.1) — domain не должен лезть напрямую в файл, а
должен получать его через значение из `compose_root`.

**Рекомендация.**
1. Завести `application/services/config_service.py` (или просто
   pydantic-`AppConfig` + factory в composition root): валидация TOML,
   defaults, перекрытие env/CLI-флагами.
2. При первом запуске без конфига — генерация дефолтного файла **в
   composition root**, не в домене.
3. Domain получает только итоговые значения через явные параметры,
   не через «знание о существовании AppConfig».

---

### A-009. `apply_master_intent` — пробел в дизайне: где живут pydantic-DTO и каков жизненный цикл `pending_advantage_flags`

**Тип:** invariant violation (multi-actor, дизайн).
**Серьёзность:** S2.
**Где:** `ENGINE.md` §6 + `MASTER.md` §8 + `ROADMAP.md` §9.

**Суть.** Инварианты multi-actor (ROADMAP §9) прописаны как императив:
«раздельные типы PlayerCommand и MasterIntent; `apply_master_intent`
существует». Где **физически** живут DTO — указано в `ARCHITECTURE.md`
дереве (`application/dto/master_intent.py`). Но:

1. `ENGINE.md` §6.2 говорит: «Очередь модификаторов:
   `pending_advantage_flags: dict[CreatureId, list[Mod]]`, первый же бросок
   цели применяет и съедает флаг». Где живёт эта очередь? Это **состояние
   движка** (GameState.master_pending_mods) или **состояние Creature**?
   От ответа зависит сериализуемость и доступ из master_ops.
2. `MASTER.md` §8 требует, чтобы поля сейва `master_pin_hash`,
   `master_mode`, `master_transparency` уже **сейчас** были в схеме.
   Где конкретно? `GameState`? `SaveMeta`? Это разные сущности —
   `GameState` (тело BLOB) или `saves`-таблица (метаданные).

**Рекомендация.**
- Зафиксировать в `ENGINE.md`: `pending_advantage_flags` — поле
  `GameState`, не `Creature` (чтобы не размазывать «временную»
  master-инъекцию по сущностям). Сериализуется как часть сейва.
- Зафиксировать в `MASTER.md` §8: `master_pin_hash` — поле
  `SaveMeta` (это «политика сейва», читается до загрузки BLOB);
  `master_mode`, `master_transparency` — поле `GameState`
  (зависят от партии).

---

### A-010. RollIssued/RollApplied: непонятно, где появляется `roll_id`

**Тип:** invariant violation (multi-actor, дизайн).
**Серьёзность:** S2.
**Где:** `ENGINE.md` §6.2: «каждый бросок сначала записывается как
`RollIssued(roll_id, dice, raw, modifiers)`, отдельно — как
`RollApplied(roll_id, outcome)`».

**Суть.** Сейчас `DiceExpr.roll(rng, ...)` возвращает `RollResult` и не
выпускает события. Чтобы инвариант выполнился, должен быть слой
`DiceRoller`, который **публикует** в `EventBus` `RollIssued`, потом
получает результат и публикует `RollApplied`. Это означает, что
`domain/rules/*` **не могут** вызывать `DiceExpr.roll` напрямую — иначе
событие не выпустится. Все правила должны идти через `DiceRoller`. Это
не противоречит `ENGINE.md` §7 («Все броски проходят через `DiceRoller`,
не напрямую через `RNG`»), но **сильно влияет на сигнатуру**
правил: `attack_roll(attacker, target, roller, ...)` вместо
`attack_roll(attacker, target, rng, ...)`.

**Рекомендация.** В `ENGINE.md` §7 явно прописать: «`domain/rules/`
получают `DiceRoller`, а не `RNG`. `RNG` остаётся только как зависимость
`ComputerDiceRoller`. Прямой вызов `DiceExpr.roll(rng)` остаётся
доступным **только** в коде, где нет требований к выпуску событий
(например, генерация stats при создании персонажа, бросок инициативы
вне боя)». Иначе появится «двойной API»: одни правила используют RNG,
другие — DiceRoller, и инвариант «все броски выпускают события» будет
систематически нарушаться.

---

### A-011. `Battlefield` — entity, но в `values/` упомянут `Square`. Чёткости границы values↔entities не хватает

**Тип:** encapsulation, разметка.
**Серьёзность:** S2.
**Где:** `ARCHITECTURE.md` §2 — `domain/entities/battlefield.py` и
`domain/values/square.py`.

**Суть.** Текущее разделение корректно: `Square` (иммутабельные
координаты) — value; `Battlefield` (изменяемая карта с террейном,
освещением, занятостью) — entity. Что нужно зафиксировать дополнительно:

1. `Battlefield` — изменяемое состояние или **тоже иммутабельное** с
   возвратом нового объекта (как `AbilityScore.adjusted`)? Это не
   решено, и решение влияет на ось «движок ↔ history/replay» (с
   иммутабельностью replay тривиален).
2. `Character` — extension `Creature` или композиция? Сейчас в
   `ARCHITECTURE.md` написано «entities: `Creature`, `Character`, `Monster`».
   Если это **наследование**, нужен ADR, обосновывающий это (LSP-риски,
   методы только-для-PC). Если **композиция** (`Character` имеет поле
   `creature: Creature`), это плюс к плагинности.

**Рекомендация.** Завести ADR-0003 (или -0004 после A-001) на тему
«Mutable vs Immutable Battlefield; Character как extension Creature».
Без этого ADR код может пойти двумя разными путями, и поправить
будет дорого.

---

### A-012. Тестовая инфраструктура: `InMemoryContentRepository` и `RecordingUI` упомянуты, но не размещены

**Тип:** тестируемость / отсутствие плана.
**Серьёзность:** S2.
**Где:** `ARCHITECTURE.md` §10 + `ROADMAP.md` §12.

**Суть.** Эти моки нужны для e2e-тестов сценария. В дереве каталогов
их нет. Конвенция: где они должны лежать?

- `InMemoryContentRepository` — это **продакшен-альтернатива**
  `SqliteContentRepository` (нужна не только в тестах, но и для CLI-режима
  «без БД»), значит в `infrastructure/content/in_memory_repository.py`.
- `RecordingUI` — это **тестовый дабл**, значит в
  `tests/_doubles/recording_ui.py` или `tests/conftest_helpers/`.

**Рекомендация.** Прописать в `ARCHITECTURE.md` §10:
- `infrastructure/content/in_memory_repository.py` — для тестов и
  CLI-демо без БД.
- `tests/_doubles/` — для всех ручных моков (RecordingUI,
  StubMonsterAI, FakeEventBus).
- `ScriptedRNG` — уже в `infrastructure/rng/`, потому что он полезен
  и за пределами тестов (например, replay по сохранённому seed).

---

## Карта реальных зависимостей (по импортам существующего кода)

```
domain/values/ability.py
  ↳ stdlib (dataclasses, enum)                                   OK
  ↳ ничего больше                                                OK
  ↳ НО внутри: метод label_ru и русские ValueError-строки        A-002, A-003

domain/values/dice.py
  ↳ stdlib (re, dataclasses, typing)                             OK
  ↳ application.ports.rng                                        ← A-001 (S1)
  ↳ ничего больше                                                OK
  ↳ НО внутри: русские ValueError-строки                         A-003

application/ports/rng.py
  ↳ stdlib (typing only: Protocol, runtime_checkable)            OK
  ↳ ничего больше                                                OK

infrastructure/rng/real_rng.py
  ↳ stdlib (random)                                              OK
  ↳ application.ports.rng                                        OK (правильное направление)

infrastructure/rng/scripted_rng.py
  ↳ stdlib (collections, collections.abc)                        OK
  ↳ application.ports.rng                                        OK
  ↳ НО внутри: русские IndexError/ValueError-строки              A-003

interfaces/cli/app.py
  ↳ typer (внешняя)                                              OK
  ↳ dnd (для __version__)                                        OK
  ↳ ничего из application/infrastructure                         OK (пока — это стаб)
  ↳ НО composition root не описан/не создан                      A-006

interfaces/cli/__main__.py
  ↳ dnd.interfaces.cli.app                                       OK
```

Резюме карты:
- **Не нарушено:** `application/` → ничего из `infrastructure/interfaces`.
  `infrastructure/` → ничего из `interfaces`. `interfaces/cli/app.py` →
  ничего из `domain/infrastructure` (но и DI там пока нет).
- **Нарушено:** `domain.values.dice` → `application.ports.rng`. См. A-001.
- **Не проверяемо:** `application/` → `domain/` (приложение ещё не
  написано). По описанию в `ARCHITECTURE.md` это допустимое направление
  (`application` зависит от `domain`).

---

## Принципиальные решения, требующие подтверждения

Эти решения нельзя оставить «как-нибудь потом» — без них дальше код
вырастет в противоречивых направлениях.

1. **Где живут порты.** `application/ports/` или `domain/ports/`?
   Сейчас выбран первый вариант, но он создаёт цикл «domain → application»
   через RNG (A-001). Решение должно быть оформлено как ADR-0003.

2. **Когда переводить тексты исключений на английский** (A-002, A-003).
   Или фиксируем «исключения domain — русские, остальное — английские»,
   или унифицируем всё на английский.

3. **Композиция зависимостей: один модуль или inline в `app.py`** (A-006).
   От этого зависит, как тесты будут поднимать движок.

4. **Регистры плагинов: глобальные декораторы или явные экземпляры** (A-007).
   От этого зависит порядок-импортов-зависимость (типичный антипаттерн
   плагин-систем на питоне).

5. **`DiceRoller` обязательно везде** (A-010). Все правила домена
   получают `DiceRoller`, а не `RNG`. Иначе инвариант
   «RollIssued/RollApplied» нарушается.

6. **Mutable vs Immutable Battlefield; Character как extension Creature**
   (A-011). От этого зависит сложность replay и сериализации.

7. **Где лежит `InMemoryContentRepository` и `RecordingUI`** (A-012).
   В infrastructure или в `tests/_doubles/`.

---

## Сводный TODO

1. **(S1) A-001:** Перенести `application/ports/rng.py` → `domain/ports/rng.py`
   (или принять формальное послабление в ADR). Обновить импорт в
   `domain/values/dice.py` и в обеих RNG-реализациях.
2. **(S1) A-002:** Удалить `Ability.label_ru` и `_RU_LABELS` из
   `domain/values/ability.py`. Все человекочитаемые имена — через
   translator в interfaces-слое.
3. **(S1) A-006:** Создать `interfaces/cli/composition.py` с функцией
   `compose_root(*, workdir, rng, ui) → GameEngine`. Зафиксировать в
   `ARCHITECTURE.md` §4.
4. **(S1) A-007:** Документировать в `ARCHITECTURE.md` §1, что реестры —
   экземпляры, регистрация явная, валидация при загрузке контента.
5. **(S2) A-003:** Перевести `raise ValueError/IndexError`-сообщения на
   английский (или зафиксировать обратное в `I18N.md`).
6. **(S2) A-004:** Решить судьбу `runtime_checkable` у `RNG`. Один из
   двух вариантов оформить комментарием в `application/ports/rng.py`.
7. **(S2) A-005:** При создании первого нового модуля
   `infrastructure/*` — сначала добавить соответствующий порт.
   Подумать о pre-commit-проверке.
8. **(S2) A-008:** Завести `AppConfig` (pydantic) + factory в
   composition root. Прописать в `ARCHITECTURE.md` §9.
9. **(S2) A-009, A-010, A-011:** Свести в один ADR-0003/-0004
   (или несколько): расположение портов; модель `DiceRoller` как
   единственного пути для всех бросков, выпускающих события;
   mutable vs immutable Battlefield; Character как extension Creature.
10. **(S2) A-012:** Зафиксировать местонахождение
    `InMemoryContentRepository` и `RecordingUI` (предложение:
    `infrastructure/content/in_memory_repository.py` и
    `tests/_doubles/recording_ui.py`).

---

## Замечания, на которые НЕ найдено нарушений

Это полезно зафиксировать, чтобы не возвращаться повторно:

- В `domain` **нет** прямых импортов pydantic, sqlite3, textual, typer,
  PyYAML, rich, platformdirs. Проверено grep'ом по всему дереву `src/dnd/domain/`
  и `src/dnd/application/`. Это очень хороший знак.
- В `application/ports/rng.py` **нет** утечки реализации в порт: только
  `Protocol`, без зависимостей.
- `dataclass(frozen=True, slots=True)` корректно применён к value-объектам
  (`DiceExpr`, `RollResult`, `AbilityScore`, `AbilityScores`) — иммутабельность
  на уровне Python соблюдена.
- `AbilityScore.adjusted` возвращает новый объект — паттерн value-object
  выполнен.
- `RealRNG` инкапсулирует `random.Random` через композицию (не наследование),
  что даёт чистое поведение seed-ования. Никакого global `random.seed`.
- `ScriptedRNG` корректно бросает `IndexError`, если кости кончились —
  это правильное поведение для теста (баг проявляется немедленно).
- В `interfaces/cli/app.py` пока нет ни единой ссылки на `application`/
  `domain`/`infrastructure` — это OK для стаба, но станет проблемой, как
  только появится бизнес-логика (см. A-006).
- Отсутствие циклов между подпакетами `domain/` (values/entities/rules/...)
  пока невозможно нарушить — там пусто. Когда наполнится, нужно следить.

---

## Финал

Архитектурный фундамент крепкий: документация подробная, направления
зависимостей прописаны, инварианты multi-actor зафиксированы как
требования. Реальный код пока маленький, но **одно прямое нарушение
направления** уже есть (`domain → application` через RNG-порт), и одно
**нарушение i18n-инварианта** (`label_ru` в domain). Оба чинятся за
полчаса, но без правки сейчас они создадут шаблон «так можно», по
которому пойдут все следующие модули. Это самый высокий приоритет.

Остальные находки — про дизайн-пробелы (composition root, DiceRoller
как единственный путь броска, реестры, конфигурация, разметка
mutable/immutable), которые надо решить **до** написания следующего
вертикального среза (§2 ROADMAP: GameEngine + Battlefield), потому что
именно §2 наступит на каждую из этих ям.

# Audit 02: интерфейсы и контракты

Документ — независимый ревью полноты, согласованности и разграничения
ответственности портов, DTO и сопутствующих контрактов проекта
`bmstu/dndgame`. Источники: `docs/ARCHITECTURE.md`, `docs/ENGINE.md`,
`docs/UI.md`, `docs/MASTER.md`, `docs/I18N.md`, `docs/DESIGN.md`,
`docs/ROADMAP.md` и фактические файлы реализаций в
`src/dnd/application/ports/` и `src/dnd/infrastructure/rng/`.

## Резюме

- Найдено пробелов в портах: **6** (Clock, ConfigService, LogWriter,
  Translator, ReactionRegistry, явный реестр всех плагин-регистров).
- Несоответствий сигнатур: **5** (UserInterface в UI.md vs ARCHITECTURE.md;
  MonsterAI vs TurnIntentProvider; DiceRoller между ENGINE.md и
  ARCHITECTURE.md; LocStr.resolve реализация vs декларация в I18N.md;
  TurnIntent/StepResult неявно определены).
- Дублирующих DTO: **3** (`EngineStateView` ≈ `BattleView` ≈
  `CombatStateView`; `prompt` vs `prompt_key`; `Modifier` встречается в
  двух смыслах — value-object бонуса и master-команда).
- Нарушений ISP: **2** (`UserInterface` — 7 разнородных методов;
  `ContentRepository` — 11 методов под разные сущности).
- Рекомендованных дополнительных портов: **5** (`Clock`,
  `ConfigService`, `LogWriter`, `Translator` как порт,
  `TurnIntentProvider`).

S0 (поломает реализацию): **5**.
S1 (желательно зафиксировать до кода): **9**.
S2 (стилистика/именование): **6**.

---

## Найденные проблемы

### I-001. `TurnIntentProvider` упомянут, но не вынесен в `ports/`

**Тип:** missing port
**Серьёзность:** S0
**Где:** `docs/ENGINE.md` §1.3 декларирует
```python
class TurnIntentProvider(Protocol):
    def request_intent(self, ctx: TurnContext) -> TurnIntent: ...
```
`docs/ARCHITECTURE.md` §3 перечисляет порты (`ContentRepository`,
`SaveRepository`, `UserInterface`, `RNG`, `EventBus`, `MonsterAI`), но
`TurnIntentProvider` не упомянут. В §2 структуры каталогов в
`application/ports/` его файла тоже нет.

**Суть:** ENGINE.md явно сообщает, что движок «спрашивает у провайдера
интентов», а ARCHITECTURE.md этого порта не объявляет. И PC, и NPC по
ENGINE.md «реализованы через» этот провайдер — но в ARCHITECTURE.md PC
ходит через `UserInterface.request_turn_intent`, а NPC — через
`MonsterAI.pick_intent` (разные имена методов). Это не один и тот же
порт под разными названиями — это две параллельные иерархии без
общего интерфейса. Движок при этом «выбирает провайдера по
controller_id» (ENGINE.md §8) — без интерфейса это невозможно красиво
закодить.

**Рекомендация:** добавить `application/ports/turn_intent_provider.py`
с единым контрактом:
```python
class TurnIntentProvider(Protocol):
    def request_intent(self, ctx: TurnContext) -> TurnIntent: ...
```
`UserInterface` и `MonsterAI` адаптируются к нему (адаптер `UITurnIntentProvider`
и `MonsterAITurnIntentProvider`). Имена методов `request_turn_intent`
(UI) и `pick_intent` (AI) — переименовать или явно объявить адаптеры.

---

### I-002. `MonsterAI.pick_intent` vs `UserInterface.request_turn_intent` — разные сигнатуры одной семантики

**Тип:** inconsistent signature
**Серьёзность:** S1
**Где:** `docs/ARCHITECTURE.md` §3.3 и §3.5:
```python
UserInterface.request_turn_intent(self, ctx: TurnContext) -> TurnIntent
MonsterAI.pick_intent(self, actor: Creature, ctx: TurnContext) -> TurnIntent
```

**Суть:** одна и та же семантика «выбрать интент на ход существа» —
два разных имени (`request_turn_intent` / `pick_intent`) и разный
набор параметров (UI получает только `ctx`, AI получает ещё и
`actor`). При наличии `TurnIntentProvider` (см. I-001) эта разница не
обоснована: `actor` логично положить внутрь `TurnContext`.

**Рекомендация:** унифицировать. `TurnContext` должен содержать `actor:
CreatureId` (или `actor_ref`). Метод — `request_intent(ctx)` в обеих
реализациях. UI- и AI-провайдеры — адаптеры.

---

### I-003. `DiceRoller` — расплывчатые границы со `DiceExpr.roll()`

**Тип:** unclear boundary
**Серьёзность:** S0
**Где:** `docs/ENGINE.md` §7 объявляет:
```python
class DiceRoller(Protocol):
    def roll(self, expr: DiceExpr, ctx: RollContext) -> RollResult: ...
```
А `src/dnd/domain/values/dice.py:108` уже имеет:
```python
def roll(self, rng: RNG, *, advantage=False, disadvantage=False, crit=False) -> RollResult: ...
```

**Суть:** два разных контракта возвращают разные `RollResult`. Доменный
`RollResult` (dice.py:176) — value-object со `kept/dropped/total`.
ENGINE.md ожидает, что `DiceRoller` дополнительно публикует `RollIssued`
+ `RollApplied` события, а возвращаемый `RollResult` должен иметь
`roll_id` (упоминается в `MasterIntent.reroll(roll_id)`). У текущего
доменного `RollResult` поля `roll_id` нет.

Дальше: `DiceExpr.roll(rng, advantage=...)` дублирует то, что должен
делать `DiceRoller` через `RollContext.advantage`. Если правила вызывают
`DiceExpr.roll()` напрямую — мастер не сможет вмешаться (нет
`RollIssued`). Если через `DiceRoller` — `DiceExpr.roll()` становится
private helper-ом.

**Рекомендация:**
1. Зафиксировать: правила домена **никогда** не вызывают
   `DiceExpr.roll()` напрямую. Только через `DiceRoller`.
2. `DiceExpr.roll()` переименовать в `_mechanical_roll()` или сделать
   internal-методом, дернуть DI-предупреждение.
3. Добавить в `RollResult` поле `roll_id: UUID` (или иметь отдельный
   DTO `EngineRollResult { roll_id, raw_result: RollResult, ctx,
   issued_at }`).
4. Явно описать: `DiceRoller` живёт в
   `application/engine/dice_roller.py` (это и записано в ARCHITECTURE
   §2). Это не доменный объект, а application-слой.

---

### I-004. `UserInterface` — нарушение ISP, разные сигнатуры между UI.md и ARCHITECTURE.md

**Тип:** ISP violation + inconsistent signature
**Серьёзность:** S0
**Где:**
- `docs/ARCHITECTURE.md` §3.3:
  ```python
  request_choice(self, prompt_key: str, options: list[Choice]) -> Choice
  request_confirm(self, prompt_key: str) -> bool
  ```
- `docs/UI.md` §10:
  ```python
  request_choice(self, prompt: str, options: list[Choice]) -> Choice
  request_confirm(self, prompt: str) -> bool
  ```

**Суть:**
а) Поле названо то `prompt_key` (i18n-ключ), то `prompt` (готовая
строка). Это **поломает** реализацию: при `prompt` — UI выводит как
есть, при `prompt_key` — пропускает через `Translator`. Согласно
I18N.md §3 правило 1 — никаких готовых строк, только ключи. То есть
правильный вариант — `prompt_key`.

б) Один интерфейс совмещает push-вывод (`on_event`, `show_text`,
`show_view`) и pull-запросы (`request_*`). Сам ARCHITECTURE.md §8
признаёт «если начнёт распухать — разделим (InputPort, OutputPort)».
7 методов разных семантик — уже распухло.

**Рекомендация:**
1. Зафиксировать в обоих документах единственное имя поля —
   **`prompt_key`** (+ `**vars` для подстановки).
2. Разбить на 3 порта:
   - `OutputPort`: `on_event`, `show_text`, `show_view`.
   - `InputPort`: `request_turn_intent`, `request_choice`,
     `request_target`, `request_confirm`.
   - (опц.) `ViewPort` отдельно от `OutputPort`, если рендер
     отделится от event-push.

   Реальная `TextualUserInterface` / `CliUserInterface` реализует все
   три. Но движок зависит от каждого узко.

---

### I-005. `Protocol` vs `ABC` — единого стиля не зафиксировано

**Тип:** inconsistent signature (style)
**Серьёзность:** S1
**Где:** `docs/ARCHITECTURE.md` §3 — все порты `Protocol`. `DESIGN.md`
§11: «Везде, где "реализуют интерфейс", — это **abstract base class**
в `domain`».

**Суть:** прямое противоречие. ARCHITECTURE.md выбирает structural
typing (`Protocol`), DESIGN.md говорит — nominal typing (`ABC`).
Реализованный `RNG` (`src/dnd/application/ports/rng.py:14`) —
`Protocol` с `@runtime_checkable`. То есть фактически выбран
`Protocol`, но DESIGN.md ещё не обновлён.

**Рекомендация:** зафиксировать единый стиль (**`Protocol`** + опционально
`@runtime_checkable` для тестов через `isinstance`). Обновить DESIGN.md
§11 (изменить «abstract base class» → «Protocol-интерфейс»). Это S1,
но если оставить — будут смешанные реализации.

---

### I-006. Отсутствует порт `Clock`

**Тип:** missing port
**Серьёзность:** S1
**Где:** в `MASTER.md` §4: «Лог содержит запись: кто, когда, что,
зачем». В `UI.md` §7.3: «t: timestamp». В DESIGN.md §12: сейв включает
`created_at`. В `ENGINE.md` §5: GameLog — append-only с метками.

**Суть:** все эти timestamps кто-то должен породить. Прямой вызов
`datetime.now()` в правилах = недетерминизм в тестах. RNG спрятан за
портом — а время нет. Этот же `Clock` нужен для:
- идемпотентных тестов реплея;
- определения «long rest 8 часов» при автоматическом таймскипе;
- master-операции `narrate(..., timestamp)` для аудит-лога.

**Рекомендация:** добавить
```python
class Clock(Protocol):
    def now(self) -> datetime: ...
```
Реализации: `SystemClock` (продукт), `FrozenClock(start, tick=timedelta)`
(тесты). Поместить в `application/ports/clock.py`.

---

### I-007. Отсутствует порт `ConfigService`

**Тип:** missing port
**Серьёзность:** S1
**Где:** `ARCHITECTURE.md` §4 п.1: «читает конфиг (`platformdirs` или
`--workdir`)»; §9: «Конфигурация — TOML-файл в
`~/.config/dnd/config.toml`». `I18N.md` §9 описывает `config.toml`. Но
ни одного порта `Config*` в списке нет — ни в коде, ни в декларации.

**Суть:** в текущем виде `interfaces/cli/app.py:compose_root()` читает
TOML напрямую, передаёт `lang/theme/db_path` дальше. Application-слой
этого знать не должен; сервисы (`SaveService`, `Translator`) хотят
знать «где база», «какая локаль». Без порта эти параметры — россыпь
аргументов. С портом — единый `ConfigService.get_str('i18n.lang')` или
`get_paths()`.

**Рекомендация:** добавить
```python
class ConfigService(Protocol):
    def get_str(self, key: str, default: str | None = None) -> str: ...
    def get_int(self, key: str, default: int | None = None) -> int: ...
    def get_path(self, key: str) -> Path: ...
    def section(self, name: str) -> Mapping[str, Any]: ...
```
Реализации: `TomlConfigService` (продукт), `DictConfigService` (тесты).
Опционально — горячая перезагрузка (но это пост-MVP).

---

### I-008. Отсутствует порт `LogWriter` (или `JournalLogPort`)

**Тип:** missing port
**Серьёзность:** S1
**Где:** `ENGINE.md` §5: «Каждое событие пишется в `GameLog`
(append-only)». В §1.1 — «публикует события в EventBus — на них
реагируют сценарий, UI, **журнал**, будущий live-мастер». Журнал — кто
этот «журнал»? В коде сейчас нет ни порта `LogWriter`, ни сервиса
`GameLogWriter`, ни в ARCHITECTURE-каталогах.

**Суть:** два разных лога:
1. **Технический лог** (`logging`-модуль Python) — пишет ошибки,
   трейсбеки. По I18N.md §1: только английский. Структурный.
2. **GameLog** — поток событий движка для сейва, replay-а и
   аудита-мастера. Это **доменное** понятие — список pydantic-DTO.

Сейчас они смешаны в `infrastructure/logging/`. Технический логгер — да,
инфраструктура. GameLog — нет: это **append-only поток в GameState**,
им владеет сейв.

**Рекомендация:** разделить:
- `infrastructure/logging/` — обёртка над stdlib `logging`. Не порт, а
  библиотечный модуль.
- `application/engine/game_log.py` — модуль с `GameLog`-моделью
  (pydantic). Записывается через подписку на `EventBus`. Не порт.
- Если нужен порт «куда писать структурный лог» (stdout/файл/JSONL) —
  отдельный `LogWriter(Protocol)` с `write(event: LogRecord)`. Этот
  порт **опционален** для MVP, но полезен для аудита мастер-операций.

---

### I-009. `Translator` живёт как глобальный экземпляр, а не как порт

**Тип:** unclear boundary
**Серьёзность:** S1
**Где:** `I18N.md` §2.3:
```python
i18n = Translator(lang=config.lang, base_dir=Path(...))
_ = i18n.gettext
```

**Суть:** Translator — класс с конкретной реализацией (Babel+gettext) и
с глобальным `_ = i18n.gettext`. По DIP application-слой не должен
знать про Babel. UI вызывает `_("New game")` — это инфраструктурная
зависимость, прокинутая через module-level singleton. В тестах
переопределить — только через monkeypatch.

Дополнительно: `LocStr.resolve(lang: str) -> str` (I18N.md §4.1)
использует `getattr(self, lang, None)` — это значит, что добавление
третьего языка требует добавления нового поля в pydantic-модель, а не
произвольную пару. Декларируется «третий язык — одна строка в YAML»,
а реально — миграция схемы.

**Рекомендация:**
1. Объявить порт:
   ```python
   class Translator(Protocol):
       def gettext(self, key: str, /, **vars: Any) -> str: ...
       def ngettext(self, sg: str, pl: str, n: int, /, **vars: Any) -> str: ...
   ```
   Реализация `BabelTranslator` живёт в `infrastructure/i18n/`. UI и
   сервисы получают `Translator` через DI.
2. `LocStr` пересмотреть: вместо `en: str | None, ru: str | None` —
   `translations: dict[str, str]` (где ключ — BCP-47-локаль) + метод
   `resolve(lang)`. Расширяемо без изменения схемы.

---

### I-010. ContentRepository: «реестры плагинов» путаются с «данными»

**Тип:** unclear boundary
**Серьёзность:** S0
**Где:** `ARCHITECTURE.md` §1 паттернов: «Plugin / Registry:
`FeatureRegistry`, `ConditionRegistry`, `ActionRegistry`,
`MonsterAIRegistry`». §3.1: `ContentRepository.get_species/get_class/...`.

**Суть:** концептуально это два разных мира:
- **`ContentRepository`** — достаёт **данные** (`Species`,
  `CharacterClass`, `Monster`, `Item`) из SQLite. Это
  Repository-pattern, чистый.
- **`FeatureRegistry` / `ConditionRegistry` / `ActionRegistry`** —
  достаёт **классы-плагины** (Python-классы), зарегистрированные
  декоратором `@register("rage")`. Это не данные, а код.

Сейчас граница не описана. Что произойдёт, если у Species есть
`features: [darkvision, fey_ancestry]`? `darkvision` — это:
- (а) запись в `content/core/features/*.yaml` (данные → ContentRepository),
- (б) Python-класс с поведением (плагин → FeatureRegistry),
- (в) оба?

Без явного контракта — будет путаница. DESIGN.md §11 заявляет «YAML +
опц. плагин», но в коде это не описано.

**Рекомендация:**
1. Зафиксировать: данные `Feature/Condition/Action` хранятся в
   ContentRepository, **поведение** (Python-классы) — в Registry.
2. Связь — по `id`: YAML говорит `feature_id: darkvision`,
   `FeatureRegistry.get("darkvision")` возвращает класс с
   `on_apply/on_remove/...`.
3. Регистры — **не порты**, а module-level dict-объекты в `domain/`.
   Они не пересекают границу application↔infrastructure.
4. Если когда-то понадобится «плагины из паков» — будет
   `PluginLoader(Protocol)` (отдельный порт). Сейчас — module-level.

---

### I-011. `ContentRepository` — too fat (нарушение ISP)

**Тип:** ISP violation
**Серьёзность:** S2
**Где:** `ARCHITECTURE.md` §3.1 — 11 методов: `get_species`,
`list_species`, `get_class`, `list_classes`, `get_background`,
`get_item`, `get_spell`, `get_monster`, `get_scenario`, `get_sprite`,
`get_table`.

**Суть:** в одном «боге» собраны 7 разнородных сущностей. Сервис
создания персонажа использует {species, classes, backgrounds, items},
сервис боя — {monsters, items, spells}, сценарий — {scenarios,
tables}. Любой из них тащит знание о всех остальных.

**Рекомендация:** МVP — оставить как есть (учебный проект, один
backend SQLite). После MVP — расщепить:
- `SpeciesRepository`, `ClassRepository`, `BackgroundRepository`
- `ItemRepository`, `SpellRepository`, `MonsterRepository`
- `ScenarioRepository`, `SpriteRepository`, `TableRepository`

И `ContentRepository` остаётся **фасад-агрегатор** (composite) для
удобства composition root.

---

### I-012. `EngineStateView` vs `BattleView` vs `CombatStateView` — дублирование

**Тип:** duplicate DTO
**Серьёзность:** S1
**Где:**
- `docs/ENGINE.md` §1.2: `state() -> EngineStateView`.
- `docs/UI.md` §10: «`AnyView` — union DTO (`CharacterSheetView`,
  `BattleView`, …)».
- `docs/UI.md` §6: экран `Combat` — рисует «CombatStateView» (никогда
  не объявлен явно как тип).
- ARCHITECTURE.md перечисляет в §5 только `*View` без конкретики.

**Суть:** три имени для одного и того же ландшафта.
- `EngineStateView` — снапшот всего движка (режим + актуальная View).
- `BattleView` — конкретный view-state экрана боя.
- `CombatStateView` — встречается в тексте без определения.

Скорее всего, `BattleView` == `CombatStateView`, и `EngineStateView` —
их обёртка с режимом. Но это надо зафиксировать.

**Рекомендация:**
1. Принять каноническое имя:
   ```python
   class EngineStateView(BaseModel):
       mode: Literal["EXPLORATION", "COMBAT", "MENU", ...]
       view: BattleView | ExplorationView | CharacterSheetView | ...
   ```
2. `CombatStateView` — выкинуть как термин. Только `BattleView`.
3. Перечислить все View-типы в одном месте (например
   `application/dto/views.py` — уже заявлен).

---

### I-013. `Modifier` — двойной смысл

**Тип:** duplicate DTO / naming clash
**Серьёзность:** S1
**Где:**
- `ARCHITECTURE.md` §1 структуры: `domain/values/Modifier` — value-object
  бонуса (+2 к КД, проф. бонус).
- `MASTER.md` §3.6 — `class Modifier(BaseModel)` для мастер-операции
  «фамильный кинжал отца».

**Суть:** два разных понятия в одном имени. Доменный `Modifier` —
короткоживущий числовой бонус. Master-`Modifier` — долгоживущий
именованный эффект на сущность с `expires`, `reason`. Это разные DTO
с разной семантикой; одинаковое имя приведёт к путанице в импортах.

**Рекомендация:**
- Доменный — оставить `Modifier` (или переименовать в `BonusModifier`).
- Master-овский — переименовать в `MasterModifier` или `EffectSpec`.
- В коде явно: `from dnd.application.dto.master_intent import MasterModifier`.

---

### I-014. `MasterIntent.kind` — закрытое перечисление с `Literal[...]`

**Тип:** unclear boundary / extensibility
**Серьёзность:** S1
**Где:** `ENGINE.md` §6.1:
```python
class MasterIntent(BaseModel):
    kind: Literal["reroll", "set_roll", "set_hp", ...18 значений...]
```
В MASTER.md §3 перечислено ~25 операций (от `revive` до `narrate`),
а в ENGINE.md только 18.

**Суть:**
1. Списки в ENGINE.md и MASTER.md **не совпадают**: ENGINE.md не
   содержит `revive`, `extra_turn`, `change_terrain`, `set_light`,
   `give_xp`, `set_npc_disposition`, `apply_modifier`,
   `switch_npc_mode` и др.
2. `Literal[...]` — закрытая система. Хочешь добавить «дать
   героическое вдохновение» — правишь enum + диспетчер + тесты.
   Плагин-мастер-операции невозможны.
3. `payload: dict` сводит на нет преимущество pydantic-типизации:
   payload каждой команды — свой; общий `dict` теряет схему.

**Рекомендация:**
- Заменить `Literal + dict` на **discriminated union**:
  ```python
  class RerollIntent(BaseModel):
      kind: Literal["reroll"] = "reroll"
      roll_id: UUID
      reason: str
      issued_by: PlayerId

  class SetHpIntent(BaseModel):
      kind: Literal["set_hp"] = "set_hp"
      creature_id: CreatureId
      value: int
      reason: str
      issued_by: PlayerId

  MasterIntent = Annotated[
      RerollIntent | SetHpIntent | ... ,
      Field(discriminator="kind"),
  ]
  ```
  Pydantic v2 это умеет; типизация в IDE/mypy — полная; добавление
  новой команды — новый класс + добавление в union.
- Привести списки операций в ENGINE.md и MASTER.md к единому
  перечислению (источник истины — MASTER.md §3, ENGINE.md только
  ссылается).

---

### I-015. `apply_master_intent` есть, но «портов не вводим» — что значит?

**Тип:** unclear boundary
**Серьёзность:** S2
**Где:** `ROADMAP.md` §9: «Сейчас порт `GameMasterPort` не вводим».
`ENGINE.md` §6.4: «не вводим сейчас портов GameMaster, MasterUI,
Transport». Но `apply_master_intent` уже на `GameEngine`, и
`master_ops.py` уже есть.

**Суть:** противоречия нет, но формулировка вводит в заблуждение.
`apply_master_intent` — это **метод** движка, а не порт. «Порт мастера»
был бы `GameMasterPort` с обратным направлением: движок дёргает
`GameMasterPort.decide_what_to_do_next()`. Этого нет — и не нужно для
MVP. То есть «не вводим порт» — да, не вводим **обратного** канала
«запрос к человеку-мастеру». А `MasterIntent` как DTO и метод его
применения — есть.

**Рекомендация:** уточнить терминологию в `ROADMAP.md` §9 и `MASTER.md`
§7:
> «Не вводим **GameMasterPort** (обратный канал «движок → живой
> мастер»). DTO `MasterIntent` и метод `GameEngine.apply_master_intent`
> уже существуют — это прямой канал «команда сверху → движок», он не
> является портом».

---

### I-016. EventBus — синхронность и реентерабельность не описаны

**Тип:** unclear boundary
**Серьёзность:** S0
**Где:** `ARCHITECTURE.md` §3.4: «`EventBus` — синхронная in-memory
publish/subscribe». `ENGINE.md` §5: «`EventBus` — синхронный, in-memory».
Никаких слов про:
- что произойдёт, если внутри handler-а кто-то ещё `publish()`-нёт;
- сохраняется ли порядок «событие A → handler → событие A.subB»;
- разрешено ли отписаться внутри handler-а;
- кидает ли handler исключение — оно тормозит остальных подписчиков?

**Суть:** при сценарии «`AttackHit` → handler `ConditionApplied` → handler
`MonsterDowned`» порядок критичен. UI-handler может на `MonsterDowned`
повесить анимацию, которая отстанет. Без явного контракта это
implementation-defined.

**Рекомендация:** добавить в `ENGINE.md` §5 (или в новый `EVENTS.md`):
1. **Контракт порядка:** очередь FIFO. `publish()` внутри handler-а
   ставит событие в **хвост** текущей очереди (а не выполняет
   рекурсивно). Это даёт детерминированный обход «волнами».
2. **Подписки:** менять список подписчиков во время `dispatch()`
   запрещено (или применяются с следующей публикации; явный выбор).
3. **Исключения handler-а:** ловятся, логируются как `ERROR`, не
   тормозят остальных подписчиков. Только сама `EventBus.publish()`
   ничего не raise-ит.
4. Прописать порт `EventBus`:
   ```python
   class EventBus(Protocol):
       def publish(self, event: EngineEvent) -> None: ...
       def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> Unsubscribe: ...
   ```

---

### I-017. `RollContext` — поля не зафиксированы

**Тип:** unclear DTO
**Серьёзность:** S1
**Где:** `ENGINE.md` §7: «`RollContext` несёт смысл броска (attack,
damage, save), участников (attacker/target), флаги (advantage,
disadvantage, crit)». Не объявлен ни в коде, ни в DTO-разделе.

**Суть:** для статистики (UI.md §7.3) нужны поля:
`context_kind: attack|damage|save|ability_check|initiative`, `actor`,
`raw`, `modifier`, `total`, `advantage`, `disadvantage`, `crit`,
`dice`, `count`. Плюс для мастер-перебросов нужен `roll_id: UUID`.

Если `RollContext` — input в `DiceRoller.roll()`, то поля
`raw/modifier/total/roll_id` — это уже output (`RollResult`). Нужно
ясное разделение.

**Рекомендация:** явно объявить два DTO:
```python
class RollContext(BaseModel):
    purpose: Literal["attack", "damage", "save", "ability_check",
                     "initiative", "hit_dice", "loot", "stats_gen", "other"]
    actor_id: CreatureId | None = None
    target_id: CreatureId | None = None
    advantage: bool = False
    disadvantage: bool = False
    crit: bool = False
    tags: list[str] = []        # для master_intervention и аудита

class EngineRollResult(BaseModel):
    roll_id: UUID
    expr: str                   # сериализованное DiceExpr
    raw: tuple[int, ...]
    kept: tuple[int, ...]
    modifier: int
    total: int
    advantage: bool
    disadvantage: bool
    crit: bool
    context: RollContext
```
Положить в `application/dto/rolls.py`. `RollIssued`/`RollApplied`
события несут эти DTO.

---

### I-018. `Envelope` упомянут, но не описан

**Тип:** unclear DTO
**Серьёзность:** S2
**Где:** `ARCHITECTURE.md` §5: «`Envelope` — обёртка `{type, payload,
version, ts}` для будущего транспорта».

**Суть:** упоминается одной строкой, не сказано:
- кто его создаёт (UI? движок? транспортный адаптер?);
- что такое `version` (сейв-версия? схема DTO? протокол?);
- зачем `ts` (см. также I-006: без `Clock`-порта — недетерминированно).

**Рекомендация:** в MVP — не нужен. Удалить упоминание из
ARCHITECTURE.md, добавить в `ROADMAP.md` §10 (сетевой режим) как
«при сетевой реализации добавится `Envelope`-DTO».

Если оставлять как «задел» — сразу зафиксировать схему:
```python
class Envelope(BaseModel):
    type: str          # FQN DTO для маршалинга
    payload: dict      # сериализованный DTO
    version: str       # схема: "engine-1.0"
    ts: datetime
    correlation_id: UUID | None = None
```

---

### I-019. `SpriteRegistry` — нужен ли как отдельный порт?

**Тип:** missing port (low priority)
**Серьёзность:** S2
**Где:** `UI.md` §4 описывает спрайты в `content/sprites/*.yaml`. В
`ContentRepository.get_sprite(id)` — да, в списке. Не выделен отдельно.

**Суть:** спрайты используются только UI-слоем. Если их класть в
`ContentRepository`, то UI зависит от Repository — нормально, ведь UI
дёргает Repository через сервис. Но семантически спрайт — это «UI-asset»,
не «game data». Если завтра захочется грузить спрайты из отдельной
папки `themes/` (например, для theme-pack-а) — выделение пригодится.

**Рекомендация:** в MVP — оставить как метод `ContentRepository`.
После MVP — выделить `SpriteRepository`. Никакого `SpriteRegistry`
(это не плагины-классы) не нужно.

---

### I-020. `Reaction` и `ReactionRegistry` — упомянуты, но не в портах

**Тип:** missing registry (and clarity)
**Серьёзность:** S2
**Где:** `DESIGN.md` §11: «`ReactionRegistry`». `ENGINE.md` §4:
«Реакции — отдельный реестр». `ARCHITECTURE.md` §1 паттернов
перечисляет `FeatureRegistry, ConditionRegistry, ActionRegistry,
MonsterAIRegistry` — но **не** `ReactionRegistry`.

**Суть:** Reaction (Opportunity Attack, Shield-spell-реакция) — отдельный
тип Command-объекта. Без `ReactionRegistry` непонятно, куда его
регистрировать. Возможные решения:
1. Объединить с `ActionRegistry` — у Action есть флаг `kind:
   action | bonus | reaction`.
2. Отдельный `ReactionRegistry`.

**Рекомендация:** объединить с `ActionRegistry`. У `Action` есть поле
`category: Literal["action", "bonus", "reaction"]`. Один реестр,
фильтры по категории. Удалить упоминание `ReactionRegistry` из
DESIGN.md.

---

### I-021. `NPCController` — DTO или entity?

**Тип:** unclear boundary
**Серьёзность:** S2
**Где:** `MASTER.md` §6:
```python
@dataclass
class NPCController:
    npc_id: CreatureId
    mode: Literal["ai", "manual", "scripted"]
    ai_strategy: str | None
```
Это `@dataclass`, не `BaseModel`. Все остальные DTO — pydantic.

**Суть:** несогласованность. Если `NPCController` пересекает границу
(в сейве), должен быть pydantic. Если это in-memory структура движка —
ок, dataclass. Не зафиксировано.

**Рекомендация:** определить:
- если NPCController сохраняется в сейв (да — режим NPC должен
  переживать перезагрузку) → `BaseModel`.
- положить в `application/dto/master_intent.py` или
  `application/dto/npc.py`.

---

### I-022. `req.md` «через Repository» — не до конца отражено

**Тип:** missing port
**Серьёзность:** S1
**Где:** `req.md` (упоминается, файл не читал; есть ссылка в
`ROADMAP.md:15`, `DESIGN.md` §15 — последняя строка таблицы:
«Repository — *Repository поверх SQLite»). `ARCHITECTURE.md` декларирует
`ContentRepository` и `SaveRepository`.

**Суть:** учебная цель — показать паттерн Repository. Сейчас явно
объявлены **2** репозитория. Из `DESIGN.md` §13 «MVP» и общего объёма
правил вероятно нужны (но явно не названы):
- `CharacterRepository` — список созданных персонажей вне партии («Create
  character» в главном меню — куда сохраняется?).
- Возможно `PartyRepository` — но это можно подмешать в
  `SaveRepository`.

**Рекомендация:** явно перечислить **обязательные** репозитории по
req.md в `ARCHITECTURE.md` §3:
- `ContentRepository` — данные правил (раса/класс/монстр/...) →
  SQLite seeded из YAML.
- `SaveRepository` — сейвы (JSON BLOB) → SQLite.
- `CharacterRepository` — отдельные персонажи, созданные через
  «Create character» в меню (вне сессии). → SQLite.

Если архитектор считает, что `CharacterRepository` подмешивается в
`SaveRepository` (черновики персонажей == «пустые сейвы») — это
тоже ок, но надо явно записать.

---

## Карта портов (рекомендуемое финальное состояние)

| Port | Where | Methods | Implementations planned | Status |
|---|---|---|---|---|
| `RNG` | `application/ports/rng.py` | `roll(sides)`, `random()` | `RealRNG`, `ScriptedRNG` | реализован |
| `DiceRoller` | `application/engine/dice_roller.py` (порт+impl в одном слое) | `roll(expr, ctx) -> EngineRollResult` | `ComputerDiceRoller`, `LiveDiceRoller`(пост-MVP) | план |
| `EventBus` | `application/ports/event_bus.py` | `publish(e)`, `subscribe(type, handler) -> Unsubscribe` | `InMemoryEventBus` | план |
| `ContentRepository` | `application/ports/content_repository.py` | `get_species`, `list_species`, `get_class`, `list_classes`, `get_background`, `get_item`, `get_spell`, `get_monster`, `get_scenario`, `get_sprite`, `get_table` | `SqliteContentRepository`, `InMemoryContentRepository` | план |
| `SaveRepository` | `application/ports/save_repository.py` | `list_saves`, `save`, `load`, `delete`, `saves_for_scenario` | `SqliteSaveRepository`, `InMemorySaveRepository` | план |
| `CharacterRepository` | `application/ports/character_repository.py` | `list`, `save`, `load`, `delete` | `SqliteCharacterRepository` | план |
| `MonsterAI` | `application/ports/monster_ai.py` | `pick_intent(actor, ctx) -> TurnIntent` | `default_brawler`, `skirmisher`, … | план |
| `TurnIntentProvider` | `application/ports/turn_intent_provider.py` | `request_intent(ctx) -> TurnIntent` | `UITurnIntentProvider`, `MonsterAITurnIntentProvider` | план |
| `OutputPort` (раскол `UserInterface`) | `application/ports/output.py` | `on_event`, `show_text`, `show_view` | `TextualOutput`, `CliOutput`, `RecordingOutput` | план |
| `InputPort` | `application/ports/input.py` | `request_turn_intent`, `request_choice`, `request_target`, `request_confirm` | `TextualInput`, `CliInput`, `ScriptedInput` | план |
| `Translator` | `application/ports/translator.py` | `gettext(key, **vars)`, `ngettext(sg, pl, n, **vars)` | `BabelTranslator`, `DictTranslator` (тест) | план |
| `Clock` | `application/ports/clock.py` | `now() -> datetime` | `SystemClock`, `FrozenClock` | план |
| `ConfigService` | `application/ports/config_service.py` | `get_str`, `get_int`, `get_path`, `section` | `TomlConfigService`, `DictConfigService` | план |
| `LogWriter` *(опц.)* | `application/ports/log_writer.py` | `write(record)` | `StdoutLogWriter`, `JsonlLogWriter` | пост-MVP |

**Не порты (module-level реестры в `domain/`):**
- `FeatureRegistry`, `ConditionRegistry`, `ActionRegistry` (включая
  Reactions), `MonsterAIRegistry`.

---

## Карта DTO (рекомендуемое финальное состояние)

| DTO | Кто отправляет | Кто принимает | Поля (ключевые) | Где определён |
|---|---|---|---|---|
| `PlayerCommand` | UI / тест | `GameEngine.step()` | `kind`, `payload` (discriminated union) | `application/dto/player_command.py` |
| `MasterIntent` | тесты / future MasterUI | `GameEngine.apply_master_intent()` | discriminated union `RerollIntent\|SetHpIntent\|...` | `application/dto/master_intent.py` |
| `EngineEvent` | `GameEngine`/правила | `EventBus`/UI | `kind`, `payload`, `tags: list[str]`, `ts: datetime` | `application/dto/engine_event.py` |
| `StepResult` | `GameEngine.step` | UI | `events: list[EngineEvent]`, `pending_requests: list[Request]`, `mode: Mode` | `application/dto/step_result.py` |
| `EngineStateView` | `GameEngine.state()` | UI | `mode`, `view: BattleView \| ExplorationView \| ...` | `application/dto/views.py` |
| `BattleView` | движок | UI | состояние боя для рендера | `application/dto/views.py` |
| `ExplorationView` | движок | UI | текущая локация для рендера | `application/dto/views.py` |
| `CharacterSheetView` | движок | UI | лист персонажа | `application/dto/views.py` |
| `TurnContext` | движок | `TurnIntentProvider` | `actor_id`, `mode`, `available_actions`, `enemies_visible`, `round`, `time_left_ms` | `application/dto/turn.py` |
| `TurnIntent` | provider | движок | `kind` (move/attack/cast/...), `target`, `params` | `application/dto/turn.py` |
| `Choice` | движок | UI | `id`, `label_key`, `description_key`, `disabled_reason_key?` | `application/dto/choice.py` |
| `TargetContext` | движок | UI | `valid_squares`, `valid_creatures`, `purpose` | `application/dto/target.py` |
| `Target` | UI | движок | `kind: square\|creature\|area`, `ref` | `application/dto/target.py` |
| `Availability` | `Action.can_perform` | сервисы | `available: bool`, `reason_key?` | `application/dto/availability.py` |
| `Outcome` | `Action.execute` | движок | `events: list[EngineEvent]`, `state_delta` | `application/dto/outcome.py` |
| `RollContext` | правила | `DiceRoller` | `purpose`, `actor_id?`, `target_id?`, `advantage`, `disadvantage`, `crit`, `tags` | `application/dto/rolls.py` |
| `EngineRollResult` | `DiceRoller` | правила, EventBus | `roll_id: UUID`, `raw`, `kept`, `modifier`, `total`, `context` | `application/dto/rolls.py` |
| `RollIssued` (event) | `DiceRoller` | EventBus | `roll_id`, `expr`, `raw`, `modifier`, `context` | `application/dto/engine_event.py` |
| `RollApplied` (event) | правила | EventBus | `roll_id`, `final_total`, `outcome` | `application/dto/engine_event.py` |
| `MasterModifier` | мастер | движок | `target_kind`, `target_id`, `effect`, `expires`, `reason` | `application/dto/master_intent.py` |
| `GameSnapshot` | `GameEngine.snapshot()` | `SaveRepository.save()` | `state`, `log: list[EngineEvent]`, `version` | `application/dto/snapshot.py` |
| `Party` | UI | `GameEngine.new_session` | `characters: list[Character]`, `master_pin_hash?` | `application/dto/party.py` |
| `SessionId` | `GameEngine` | UI | UUID-обёртка | `application/dto/ids.py` |
| `SaveMeta` | `SaveRepository` | UI | `id`, `name`, `created_at`, `scenario_id`, `scenario_version` | `application/dto/save_meta.py` |
| `NPCController` | мастер/сейв | движок | `npc_id`, `mode`, `ai_strategy?` | `application/dto/npc.py` |
| `LocStr` | контент | весь стек | `translations: dict[str, str]`, `resolve(lang)` | `domain/values/loc_str.py` |
| `CheckResult` | `domain.rules.ability_check` | сервисы | `success: bool`, `dc`, `roll: EngineRollResult` | `application/dto/check.py` |
| `NarrationHint` | сценарий | UI | `text_key`, `audience?` | `application/dto/narration.py` |

**Удалить как дубликаты:**
- `CombatStateView` (== `BattleView`).
- `Modifier` в master-смысле (заменить на `MasterModifier`).
- `Envelope` из MVP-словаря (вернуть только при сетевой реализации).

---

## Сводный TODO

В порядке убывания приоритета:

1. **(S0, I-004)** Разобрать `UserInterface` → `OutputPort` + `InputPort`.
   Зафиксировать `prompt_key` (не `prompt`). Привести UI.md §10 и
   ARCHITECTURE.md §3.3 к единой формулировке.
2. **(S0, I-003)** Зафиксировать границу `DiceRoller` ↔ `DiceExpr.roll()`.
   Все правила домена работают через `DiceRoller`. Добавить
   `EngineRollResult` с `roll_id: UUID`. `DiceExpr.roll()` →
   internal/test-only helper.
3. **(S0, I-001)** Добавить порт `TurnIntentProvider` в
   `application/ports/`. Адаптеры от `UserInterface` и `MonsterAI`.
4. **(S0, I-010)** В ARCHITECTURE.md §1 и DESIGN.md §11 разграничить
   `ContentRepository` (данные) и `*Registry` (плагины-классы). Записать,
   что регистры — не порты, а module-level dict в `domain/`.
5. **(S0, I-016)** Зафиксировать семантику `EventBus` (FIFO, отложенные
   публикации в handler-ах, поведение при исключениях, ре-подписка).
6. **(S1, I-014)** Перевести `MasterIntent` с `Literal+dict` на
   pydantic discriminated union. Привести список kind-ов в ENGINE.md и
   MASTER.md к одному источнику истины.
7. **(S1, I-009)** Объявить `Translator` как порт. Уйти от глобального
   `_`. `LocStr` — переехать на `translations: dict[str, str]`.
8. **(S1, I-005)** Зафиксировать `Protocol` как единый стиль (обновить
   DESIGN.md §11).
9. **(S1, I-006/I-007/I-008)** Добавить порты `Clock`, `ConfigService`.
   Разделить технический `logging` и `GameLog`-как-доменную-модель.
10. **(S1, I-012)** Унифицировать иерархию View. Удалить
    `CombatStateView` как термин. Объявить `EngineStateView` как обёртку.
11. **(S1, I-013)** Переименовать master-`Modifier` → `MasterModifier`.
12. **(S1, I-017)** Объявить `RollContext` и `EngineRollResult` как
    pydantic-DTO. Положить в `application/dto/rolls.py`.
13. **(S1, I-022)** Явно перечислить обязательные репозитории по req.md
    в ARCHITECTURE.md (`Content`, `Save`, `Character`).
14. **(S1, I-002)** Унифицировать `pick_intent` и `request_turn_intent`
    через общий `TurnIntentProvider.request_intent`.
15. **(S2, I-011)** После MVP — расщепить `ContentRepository` на
    7 узких. До MVP — оставить.
16. **(S2, I-015)** В `ROADMAP.md` §9 и `MASTER.md` §7 уточнить, что
    «не вводим порт» относится к `GameMasterPort` (обратный канал), а
    `apply_master_intent` — метод движка, не порт.
17. **(S2, I-018)** Удалить `Envelope` из MVP-словаря или зафиксировать
    его схему полностью.
18. **(S2, I-019)** `SpriteRepository` — выделить только после MVP.
19. **(S2, I-020)** Удалить упоминание `ReactionRegistry`. Reactions —
    в `ActionRegistry` с полем `category`.
20. **(S2, I-021)** `NPCController` — перевести на `BaseModel`, если он
    в сейве.

# X0 — время и сессия: дизайн

> Единый источник игрового времени (`GameClock` в раундах) + `GameSession` над
> `Encounter`, чтобы эффекты истекали **по времени** (а не только по триггерам) и
> время/эффекты переживали границу бой↔исследование. Гасит долг T2 (концентрация
> без временно́го потолка, длительности заклинаний). Фундамент для единого слоя
> эффектов и используемых предметов (U), исследования мира (X).

## 1. Контекст и решения (зафиксированы с пользователем)

Текущее состояние (исследовано):
- `Encounter` считает `round_number`, шлёт `RoundStarted/RoundEnded/TurnStarted/
  TurnEnded/EncounterEnded`.
- `OngoingEffectTracker` снимает эффекты **только по триггерам** (DamageDealt →
  `ends_on_damage`; TurnEnded → `repeat_save`; ConcentrationBroken).
- `Spell` **без** поля длительности; `GameClock`/`GameSession` нет.

Решения:
- **Полный `GameClock` + `GameSession` сразу** (не боевая заглушка) — баффы
  завязываются на время с самого начала.
- Канон времени — **раунд** (PHB-2024: 1 раунд = 6 c; 1 мин = 10 раундов; 1 ч =
  600 раундов).
- Длительность **дополняет** существующие триггеры, не заменяет их.
- Backward-compat: `Spell.duration` по умолчанию `INSTANT`; существующий контент
  и тесты не ломаются.
- Свет (LIGHT) и кросс-локационные действия исследования — **не** в X0 (задел X,
  см. memory `project_light_vision_deferred`). X0 даёт только модель времени и
  оболочку сессии.
- Режим исполнения (inline/subagent) — спрошу перед стартом плана.

## 2. `Duration` — значение игрового времени (domain)

`domain/values/duration.py`, frozen dataclass. Канон — раунд.

```python
class DurationUnit(StrEnum):
    INSTANT = "instant"            # мгновенно (урон, лечение)
    ROUNDS = "rounds"
    MINUTES = "minutes"
    HOURS = "hours"
    CONCENTRATION = "concentration"  # пока держится концентрация (+ потолок)
    UNTIL_ENCOUNTER_END = "until_encounter_end"
    PERMANENT = "permanent"        # до явного снятия

@dataclass(frozen=True, slots=True)
class Duration:
    unit: DurationUnit
    amount: int = 0  # для ROUNDS/MINUTES/HOURS; для CONCENTRATION — потолок (мин)

    ROUNDS_PER_MINUTE: ClassVar[int] = 10
    ROUNDS_PER_HOUR: ClassVar[int] = 600

    def to_rounds(self) -> int | None:
        """Длительность в раундах. None — «без счётного предела»
        (PERMANENT / UNTIL_ENCOUNTER_END / CONCENTRATION без потолка)."""
```

- Хелперы-конструкторы: `Duration.instant()`, `Duration.rounds(n)`,
  `Duration.minutes(n)`, `Duration.hours(n)`, `Duration.concentration(cap_min=0)`.
- `CONCENTRATION` с `amount>0` → потолок в минутах (например, 10 мин = 100
  раундов); `amount=0` → без потолка (только срыв концентрации).
- Валидация: для ROUNDS/MINUTES/HOURS `amount > 0`.

## 3. `GameClock` — часы в раундах (domain entity)

`domain/entities/game_clock.py`, mutable.

```python
class GameClock:
    now_round: int  # монотонно неубывающий, старт 0
    def advance(self, rounds: int) -> None: ...      # rounds >= 0
    def advance_minutes(self, n: int) -> None: ...    # n * 10
    def advance_hours(self, n: int) -> None: ...      # n * 600
    def expires_at(self, duration: Duration) -> int | None:
        """now_round + duration.to_rounds(); None если предел не счётный."""
```

- Бой двигает часы на границе раунда (см. §5: `Encounter`/`GameSession` зовут
  `advance(1)` на `RoundEnded`). Исследование (X) двигает по стоимости действий.
- Чистая сущность, без зависимостей от application.

## 4. Истечение эффектов по часам

### 4.1 Состояния (`OngoingEffectTracker`)

- `OngoingConditionEffect` получает поле `expires_at_round: int | None`.
- При `ConditionApplied` трекер вычисляет `expires_at_round` из переданной
  длительности и текущего `clock.now_round` (через clock-aware tracker).
- На сдвиге часов (новое событие `TimeAdvanced(now_round)` ИЛИ подписка на
  `RoundEnded` + чтение clock) трекер снимает все эффекты с
  `expires_at_round is not None and expires_at_round <= now`, публикует
  `ConditionRemoved(reason="duration")`.
- Существующие триггеры (`ends_on_damage`/`repeat_save`/`concentration_broken`)
  работают как раньше; длительность — дополнительный путь снятия.

Для передачи длительности до трекера: событие `ConditionApplied` получает поле
`duration_rounds: int | None = None` (вычисленное источником) ИЛИ трекер сам
считает по `clock` + `Duration` из эффекта. Решение: **источник кладёт
`expires_at_round` напрямую** в `ConditionApplied` (вычислив через `clock`),
трекер только сравнивает — так трекер не обязан знать про `Duration`. Поле:
`ConditionApplied.expires_at_round: int | None = None`.

### 4.2 Баффы-модификаторы (concentration / item / spell)

Баффы кладутся в `modifier_applier` под `source_id`. Чтобы истекали по времени —
завести лёгкий реестр сроков: `source_id → expires_at_round` (в clock-aware
трекере или отдельном `ModifierExpiryTracker`). На сдвиге часов истёкшие
`source_id` снимаются через `modifier_applier.remove_by_source(source_id)` +
событие. Концентрация: дополнительно к срыву получает потолок (если задан).

## 5. `Spell.duration` + ретрофит контента

- `Spell` получает `duration: Duration = Duration.instant()`.
- `BuffSpellHandler`/`ControlSpellHandler` вычисляют `expires_at_round =
  clock.expires_at(spell.duration)` и кладут его в `ConditionApplied` /
  реестр сроков баффов.
- `spells.yaml`: добавить `duration` (формат `{unit: minutes, amount: 1}` или
  `{unit: concentration, amount: 1}` — amount=потолок в минутах). Контент по PHB:
  Bless — `concentration(cap_min=1)`; Shield of Faith — `concentration(cap_min=10)`;
  Hold Person — `concentration(cap_min=1)`; урон/лечение — `instant`.
- Парсинг `Duration` в `SpellRepository`.

## 6. `GameSession` над `Encounter` (application)

`application/engine/game_session.py`.

```python
class GameSession:
    party: dict[CreatureId, Creature]
    clock: GameClock
    event_bus: EventBus
    # общий clock-aware OngoingEffectTracker + реестр сроков баффов
    def begin_encounter(self, enemies, battlefield, ...) -> Encounter: ...
    # по EncounterEnded: часы и активные эффекты сохраняются в сессии
```

- Сессия держит партию, часы, шину и общий трекер эффектов (живущий ПОВЕРХ боёв).
- `Encounter` создаётся из сессии (партия + враги локации); на `RoundEnded`
  сессия (или Encounter через clock-ссылку) двигает `clock.advance(1)`.
- По `EncounterEnded` — управление назад в сессию; часы и не-боевые эффекты
  (длительные баффы) переживают границу.
- **Ограничение X0:** режима исследования ещё нет, поэтому сессия пока оборачивает
  один бой + часы. Полный цикл бой↔исследование — на X. Это сознательно (см. §1).

## 7. Проводка (composition / GameRunner)

- `GameClock` создаётся в сессии; `OngoingEffectTracker` получает ссылку на clock
  (clock-aware конструктор).
- `Encounter`/`GameRunner` двигают clock на границе раунда (подписка на
  `RoundEnded` в сессии/трекере).
- `composition.py`: `build_*` собирают `GameSession` (clock + tracker + bus);
  старые `build_*_dependencies` для одиночных боёв сохраняются (clock по
  умолчанию свой).

## 8. Расширяемость / инварианты

1. domain не импортирует application; `Duration`/`GameClock` — в domain.
2. Длительность — данные (`Duration`); трекер сравнивает `expires_at_round`, не
   зная про единицы времени.
3. Триггеры и длительность независимы и комбинируются (Hold Person: срыв
   концентрации ИЛИ повторный спасбросок ИЛИ потолок времени — что раньше).
4. Backward-compat: `Spell.duration=INSTANT` по умолчанию; `expires_at_round=None`
   = «не истекает по времени» (старое поведение).
5. Часы монотонны; `advance` только вперёд (rounds >= 0).
6. Канон — раунд; минуты/часы конвертируются в раунды в одном месте (`Duration`).

## 9. Декомпозиция (план)

- **X0-1** `Duration` + `DurationUnit` + конверсии (`to_rounds`) + конструкторы +
  тесты (включая CONCENTRATION-потолок, INSTANT→0, бесконечные→None).
- **X0-2** `GameClock` (`now_round`, `advance/advance_minutes/advance_hours`,
  `expires_at`) + тесты (монотонность, конверсии).
- **X0-3** clock-aware `OngoingEffectTracker`: поле `expires_at_round` в
  `OngoingConditionEffect` + `ConditionApplied.expires_at_round`; снятие истёкших
  состояний на сдвиге часов (`RoundEnded`→`clock.advance(1)`→проверка) +
  `ConditionRemoved(reason="duration")`; тесты.
- **X0-4** истечение баффов-модификаторов по `source_id`+`expires_at_round`
  (реестр сроков; снятие через `remove_by_source`) + тесты.
- **X0-5** `Spell.duration` + парсинг YAML + хендлеры кладут `expires_at_round`;
  контент длительностей (Bless/Hold Person/Shield of Faith/урон) + обновить
  тесты заклинаний.
- **X0-6** `GameSession` над `Encounter` (clock+tracker+party; clock.advance на
  RoundEnded; эффекты переживают EncounterEnded) + проводка composition/GameRunner.
- **X0-7** доки (`docs/TIME.md` + ENCOUNTER/SPELLS/ROADMAP) + аудит-смок (бафф
  истекает по времени; концентрация — по потолку; регрессия зелёная).

## 10. Отложено (X / далее)

- Кросс-локационное время (действия исследования двигают часы): переход/обыск/
  отдых — этап X (clock уже поддержит).
- Полноценный цикл бой↔исследование в `GameSession` (сейчас — оболочка вокруг
  боя).
- Единый слой эффектов (slotless-резолв) и используемые предметы (U) — следующий
  спек после X0 (memory `project_unified_effects`).
- Свет/видимость — X (memory `project_light_vision_deferred`).

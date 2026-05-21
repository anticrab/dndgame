# AI — поведенческие паттерны NPC

В автоматическом режиме движок принимает решения за NPC. Чтобы враги
не выглядели одинаково — паттерны поведения **конфигурируются**: орк
тупо бьёт ближайшего, гоблин-шаман держит дистанцию и лечит союзников,
волк-разведчик убегает на низком HP и зовёт подкрепление.

Этот документ — спецификация системы поведения. Реализация — в фазе
после `Encounter` и `Action`.

---

## 1. Контракт

```python
class MonsterAI(Protocol):
    """Стратегия выбора интента на ход NPC."""

    def pick_intent(self, ctx: TurnContext) -> TurnIntent: ...

    def should_react(self, trigger: ReactionTrigger, ctx: ReactionContext) -> bool:
        """Вызывается при триггере, на который у NPC есть реакция.
        Возвращает True/False. Опционально может выбрать конкретную
        реакцию через возврат не bool, а ReactionChoice (см. §6)."""
```

Реализации лежат в `infrastructure/ai/` и регистрируются в
`MonsterAIRegistry` в composition root. Один профиль — один класс.

---

## 2. Базовые профили (MVP)

### 2.1 `Brawler` — тупой ближний

Самый частый. Орк, обычный гоблин, волк, скелет-воин.

**Логика хода:**
1. Найти **ближайшую** видимую враждебную цель.
2. Если в досягаемости рукопашки — атаковать (с приоритетом
   наибольшего ожидаемого урона: сильнейшее оружие, использует
   Multiattack).
3. Иначе — переместиться к цели максимально (полный Dash, если
   расстояние > скорость).

**Параметры YAML:**
```yaml
ai_profile: brawler
ai_params:
  prefer_strongest_weapon: true   # по умолчанию true
  prefer_target: closest          # closest | weakest | nearest_pc
```

### 2.2 `Skirmisher` — расчётливый

Гнолл-разведчик, плут-NPC. Выбирает **слабую** цель, использует
тактику: засаду, отход, фланкинг.

**Логика хода:**
1. Найти **самую слабую** видимую цель (минимум `hp/max_hp`).
2. Если у плута/гнолла есть **Скрытая атака** и условия выполнены —
   атаковать.
3. Если HP <50% и есть путь к укрытию — Disengage + Move в LowCover.
4. Иначе — обычная атака.

**Параметры:**
```yaml
ai_profile: skirmisher
ai_params:
  retreat_threshold: 0.5
  prefer_cover: true
```

### 2.3 `Ranged` — стрелок

Гоблин-лучник. Старается держать **оптимальную** дистанцию.

**Логика хода:**
1. Если враг в пределах рукопашной (5 фут) — `Disengage` + переместиться
   на дальность 30+ фут.
2. Иначе — стрелять в наименее защищённую видимую цель (минимальный КД,
   с учётом cover).

**Параметры:**
```yaml
ai_profile: ranged
ai_params:
  ideal_distance_ft: 60
  min_distance_ft: 30
```

### 2.4 `Caster` — заклинатель

Гоблин-шаман, маг-NPC. Приоритизирует заклинания над оружием.

**Логика хода:**
1. Оценить ожидаемый эффект **каждого** доступного заклинания (урон,
   спасбросок, контроль). Простая формула:
   `score = expected_damage_after_save * affected_enemies − heal_value_of_allies`.
2. Если score > порога — кастовать; иначе обычная атака посохом.
3. Концентрация: если уже под концентрацией — не пытаться кастовать
   ещё одно concentration-заклинание.

**Параметры:**
```yaml
ai_profile: caster
ai_params:
  spell_priority:
    - inflict_wounds        # самые сильные сначала
    - cure_wounds           # если союзник на грани
    - mage_armor
  fallback_attack: staff
```

### 2.5 `Support` — целитель

Лечит союзников, иногда баффает. Жрец-NPC, светлый дракон.

**Логика хода:**
1. Если **есть** союзник с HP < 50% в дальности лечения → лечить
   слабейшего.
2. Если **все** союзники >75% → бафф (если есть) или базовая атака.
3. Если на грани смерти сам — лечить себя.

### 2.6 `Coward` — трус

Гоблин-мародёр без подкрепления. Убегает на низком HP.

**Логика хода:**
1. Если HP < `flee_threshold` (по умолчанию 25%) — `Dash` к ближайшему
   выходу карты.
2. Если на пути враги — `Disengage`.
3. Иначе ведёт себя как `Brawler`.

При выходе с карты — `MonsterAI.fled = True`; encounter теряет
участника (как «сбежал»).

---

## 3. Композитные профили

Часто NPC ведёт себя по-разному в разные фазы боя. Поддерживаем через
**обёрточные** AI:

### 3.1 `PhaseSwitching`

```yaml
ai_profile: phase_switching
ai_params:
  phases:
    - { while: "hp_ratio > 0.5", profile: caster, params: {...} }
    - { while: "hp_ratio <= 0.5", profile: brawler, params: {...} }
```

Полезно для боссов: пока на полном HP — кастует Inflict Wounds; на
малых HP — впадает в ярость и бьёт оружием.

### 3.2 `FleeBelow`

Обёртка над любым профилем: если HP < threshold — переключиться на
`Coward`.

```yaml
ai_profile: flee_below
ai_params:
  base: brawler
  flee_threshold: 0.15
```

### 3.3 `PackHunter`

Координация группы: NPC учитывает позиции **союзников** в выборе цели.
Например, фокусят жертву, которую уже бьёт другой.

---

## 4. Кастомные профили — расширяемость

Для уникальных NPC (например, гоблин-шаман в финале демо) можно
писать собственный класс:

```python
# infrastructure/ai/hollow_oak_shaman.py
class HollowOakShamanAI(MonsterAI):
    """Уникальное поведение шамана: завершает ритуал на 3-м ходу,
    если игроки не прервали."""

    def pick_intent(self, ctx: TurnContext) -> TurnIntent: ...
    def should_react(self, trigger, ctx) -> bool: ...
```

Регистрация в composition root:

```python
ai_registry.register("hollow_oak_shaman", HollowOakShamanAI)
```

В YAML монстра:
```yaml
ai_profile: hollow_oak_shaman
```

Это закрытое решение из `OPEN_QUESTIONS.md` Q23 — явная регистрация.

---

## 5. Контекст принятия решений

`TurnContext` (передаваемый в `pick_intent`) содержит:

```python
class TurnContext(BaseModel):
    actor_id: CreatureId
    actor_view: CreatureView          # хиты, состояния, ресурсы
    battlefield: BattlefieldView      # карта, освещение
    visible_creatures: list[CreatureView]  # всё, что видит actor
    allies: list[CreatureId]
    enemies: list[CreatureId]
    available_actions: list[ActionRef]
    turn_budget: TurnBudget
    round_number: int
    encounter_round_phase: str        # "start" / "mid" / "ending"
```

AI **читает** этот контекст и **возвращает** `TurnIntent`:

```python
class TurnIntent(BaseModel):
    movement: list[Square] = []       # путь
    action: ActionInvocation | None = None
    bonus_action: ActionInvocation | None = None
    end_turn: bool = True             # если AI решил «дальше нечего делать»
```

`ActionInvocation` — `{action_id, target: Target, params: dict}`.

AI **не имеет** прямого доступа к состоянию (тех. секретам других PC).
Только то, что actor может видеть.

---

## 6. Реакции NPC

Когда происходит триггер реакции (PC уходит из досягаемости, кто-то
атакует союзника NPC), движок вызывает `should_react(trigger, ctx)`.

`ReactionTrigger` — discriminated union (`MovingOutOfReach`,
`AllyDamaged`, `EnemyCastsSpell` и т.п.).

`ReactionContext` — урезанный TurnContext: actor + trigger.source +
видимые участники.

NPC может вернуть:
* `False` — отказаться;
* `True` — использовать дефолтную реакцию (обычно provoked attack);
* `ReactionChoice(action_id="shield", target=...)` — конкретный выбор.

В MVP — только provoked attack для всех NPC по умолчанию.

---

## 7. Логирование и аудит

Все решения AI логируются в `GameLog` через события:

* `AIDecisionMade(actor, intent, reasoning: str)` — `reasoning` —
  человеко-читаемое объяснение в одну строку: «closest enemy Aelar at
  5ft, multi-attack with scimitar».
* Это видно мастеру в его логе; обычные игроки **не** видят (если
  `master_transparency = hidden`).

Это даёт нам два преимущества:
* мастер может «развернуть» AI и понять, почему орк побежал, а не
  атаковал;
* при отладке странного поведения — трассировка решений в одном месте.

---

## 8. Конфигурация порогов как данных

Все «магические» пороги (`flee_threshold`, `ideal_distance`) — в YAML
монстра. Это:
* даёт мастеру тюнить контент без правки кода;
* делает поведение **воспроизводимым** (тот же YAML → то же поведение);
* поддерживает A/B-тестирование баланса.

Пороги, не указанные в YAML — берут из дефолтов профиля. Дефолты —
конкретные числа в Python-классе профиля, **не** «магические литералы»
по коду.

---

## 9. Тесты

* Юнит на каждый профиль: построить минимальный TurnContext с
  predefined ситуацией, проверить, что pick_intent возвращает
  ожидаемый интент.
* Параметризованный тест: для `Brawler` × 5 разных сценариев
  (один враг, два врага, враг недоступен, низкое HP, союзник
  блокирует) — ожидаемое действие.
* Интеграционный: encounter demo-сценария (gobsil 1) с
  ScriptedRNG — после хода Brawler-гоблина PC получил атаку и урон.
* Property-based: для любых валидных хитов/позиций — AI **не
  падает** и возвращает валидный TurnIntent (никаких NPE).

---

## 10. Что отложено

* **Машинное обучение / нейроагенты** — нет, и не планируется. Это
  учебная игра, прозрачность решений важнее «реалистичности».
* **Pathfinding с препятствиями-союзниками** — A* учитывает только
  террейн и враждебных. Сквозь дружественных можно ходить (книга это
  разрешает; и упрощает алгоритм).
* **Long-term memory** AI (помнит, что игрок применил Hide вчера) —
  пост-MVP. AI принимает решения только по текущему `TurnContext`.
* **Координированные тактики** (засада группы из 5 гоблинов) —
  частично через `PackHunter`, но без сложного планирования.

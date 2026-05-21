# TARGETING — выбор цели для действий и заклинаний

В D&D у каждого действия и заклинания есть **тип цели**: одно существо,
точка на земле, область, сам наносящий, все существа в зоне и т.п.
От этого зависит и логика проверки («можно ли так применить?»), и UI
(«куда наводить курсор?»). Этот документ описывает общий контракт.

---

## 1. Иерархия `Target`

Все цели — discriminated union на pydantic v2:

```python
TargetKind = Literal[
    "creature",      # одно существо по id
    "square",        # одна клетка по координатам
    "area",          # область, заданная формой
    "self",          # сам действующий
    "all_in_range",  # все существа в зоне с фильтром
    "multi",         # явный список нескольких целей
]
```

```python
class CreatureTarget(BaseModel):
    kind: Literal["creature"] = "creature"
    creature_id: CreatureId

class SquareTarget(BaseModel):
    kind: Literal["square"] = "square"
    square: Square

class AreaTarget(BaseModel):
    kind: Literal["area"] = "area"
    origin: Square
    shape: AreaShape          # см. §2

class SelfTarget(BaseModel):
    kind: Literal["self"] = "self"

class AllInRangeTarget(BaseModel):
    kind: Literal["all_in_range"] = "all_in_range"
    origin: Square
    range_ft: int
    filter: TargetFilter      # см. §3

class MultiTarget(BaseModel):
    kind: Literal["multi"] = "multi"
    targets: list[Target]     # рекурсия через TypeAdapter

Target = Annotated[
    CreatureTarget | SquareTarget | AreaTarget |
    SelfTarget | AllInRangeTarget | MultiTarget,
    Field(discriminator="kind"),
]
```

Живёт в `application/dto/target.py`.

---

## 2. Формы областей (`AreaShape`)

Книга 2024 формализует пять форм:

```python
class AreaShape(BaseModel):
    kind: Literal["sphere", "cone", "cube", "cylinder", "line"]
    size_ft: int               # радиус / длина / сторона
    width_ft: int = 5          # для line — ширина
    facing: Direction | None = None   # для cone и line — направление
```

* **Sphere** (`origin` — центр; задевает всё в радиусе `size_ft`).
  Огненный шар: `radius=20`.
* **Cube** (`origin` — угол или центр; в книге — угол ближайший к
  атакующему). Громовая волна Mistral: `size=15`.
* **Cone** (`origin` — точка, исходящая из заклинателя; раскрытие на
  60°). Дыхание дракона.
* **Cylinder** (`origin` — центр основания, бесконечно вверх в рамках
  правил). Спасение от падения, заклинание Wall of Stone.
* **Line** (`origin` — точка истока; `size` — длина, `width` — ширина).
  Молния: `100×5`.

Преобразование формы в **множество клеток** — метод
`AreaShape.squares(origin: Square) -> set[Square]`. Реализуется в
`domain/values/area.py` (новый VO). Sphere/Cube на квадратной сетке
аппроксимируются как `chebyshev_disk(radius_in_squares)`.

---

## 3. Фильтр целей (`TargetFilter`)

Для `AllInRangeTarget` и для валидации `CreatureTarget`:

```python
class TargetFilter(BaseModel):
    include_self: bool = False
    include_allies: bool = True
    include_enemies: bool = True
    include_objects: bool = False
    creature_kinds: frozenset[str] | None = None  # "humanoid", "undead", ...
    max_size: CreatureSize | None = None
    requires_los: bool = True
    requires_visible: bool = True            # ≠ los — учитывает obscurement
```

Это даёт нам декларативно описывать вещи вроде:
* «Воскрешение зомби» — `creature_kinds={"undead"}`, `include_self=False`.
* «Heroism» — `include_self=True, include_allies=True, include_enemies=False`.
* «Командная атака» — `include_enemies=True`, дальность 30 фт.

---

## 4. Контракт действия

```python
class Action(Protocol):
    id: str
    name_key: str
    category: Literal["action", "bonus", "reaction"]

    target_spec: TargetSpec
    """Что принимает действие как цель: типы Target, дальность, фильтр."""

    repeats: int = 1
    """Сколько раз повторяется за одно использование (Multiattack)."""

    def can_perform(self, actor: Creature, ctx: TurnContext) -> Availability: ...

    def execute(
        self, actor: Creature, target: Target, ctx: TurnContext,
    ) -> ActionOutcome: ...
```

```python
class TargetSpec(BaseModel):
    accepts: frozenset[TargetKind]
    max_range_ft: int = 5
    filter: TargetFilter | None = None
    area_shape: AreaShape | None = None     # обязателен, если accepts area
    requires_concentration: bool = False
```

Действие декларирует, что оно принимает; UI и движок **знают**, что
спрашивать у игрока.

---

## 5. UI: запрос цели

`UserInterface.request_target(ctx: TargetContext) -> Target`

`TargetContext` несёт:
* `target_spec: TargetSpec` — что валидно;
* `valid_squares: set[Square]` — UI подсвечивает их (рассчитано
  движком: дистанция + LoS + фильтры);
* `valid_creatures: list[CreatureId]` — циклирование по Tab;
* `preview: TargetPreview | None` — что произойдёт, если выбрать эту
  цель (например, ожидаемый урон); UI обновляет по мере наведения курсора.

Игрок:
1. Сначала выбирает **действие** из меню (A — атака, S — заклинание).
2. Если у действия `target_spec.accepts == {"self"}` — Target
   возвращается сразу.
3. Иначе UI входит в режим «выбора цели»: курсор по клеткам, Tab
   циклирует валидные. Enter — подтвердить, Esc — отменить.
4. Для `area` — UI рисует **область применения** (диск/конус/линию) от
   позиции курсора.

Книга 2024 «Социальное взаимодействие»: команды-аналоги и для
исследования (например, действие Влияние тоже требует выбора цели —
NPC).

---

## 6. Анимация и логирование «куда попало»

Архитектор отметил: «когда видно, куда всё попало, было бы очень
классно».

Реализация:

* `Action.execute` возвращает `ActionOutcome.events: list[EngineEvent]`.
* Каждое попадание/промах/спасбросок — отдельное событие, которое UI
  визуализирует:
  * клетки, попавшие под AoE, мигают `effect-fg` 200мс;
  * прошедшие спасбросок (половина урона) — другой оттенок;
  * полностью провалившие — самый яркий;
  * критические попадания — красная вспышка.
* Лог боя (правая панель) — текстовое перечисление: «Огненный шар:
  Гоблин-1 — 15 урона, Гоблин-2 — 7 урона (спасбросок), стена — без
  эффекта».

`BattleView` (DTO для UI) включает поле `last_action_visualization:
ActionVisualization | None`, которое держится **2 секунды** (или до
следующего действия). После этого визуализация сбрасывается, но
данные есть в логе.

---

## 7. Тесты

* Юнит на `AreaShape.squares` по каждой форме (sphere/cube/cone/cylinder/line).
* Юнит на `TargetFilter.matches(creature, ctx)` (включает/исключает
  правильно).
* Property-based: для каждого Target в любом валидном `TargetContext`
  `Action.can_perform == True`.
* Интеграционный: Огненный шар (3-й уровень) в коридоре с PC и тремя
  гоблинами — попадает в 3 цели, не попадает в стену, лог содержит
  3 события урона.
* Свойство-тест: для любой формы — все клетки в `shape.squares(origin)`
  находятся на Chebyshev-расстоянии ≤ `size_ft / 5` от origin.

---

## 8. Что отложено

* **Цели, требующие выбора по очереди** (например, заклинание Tasha's
  Hideous Laughter — выбор после провала спасброска). Реализуем по факту.
* **Целеуказание для реакций** — обычно «триггер сам подсказывает цель»
  (provoked attack — тот, кто уходит). Если появится сложный случай —
  расширим.
* **Цели-объекты** (двери, сундуки, статуи) — поддержано через
  `SquareTarget` + проверка наличия объекта на клетке. Полноценный
  `ObjectTarget` — пост-MVP.
* **Множественные таргеты ОДНОГО действия** (Magic Missile — три удара
  в разные цели) — поддержано через `MultiTarget(targets=[...])`. UI
  спрашивает по очереди.

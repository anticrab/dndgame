# Этап L: Inline UX + Ability Framework + Viewport — Design

**Дата:** 2026-05-23
**Автор:** Maxim Lokotkov (github.com/anticrab)
**Статус:** черновик на ревью

---

## 1. Контекст и мотивация

После этапа K (богатые карты + 5×3 sprite-renderer) реальный playtest выявил:

1. **Модальные picker'ы убивают context** — при `m` (move) открывается отдельный экран MovePicker, скрывая карту. То же с TargetPicker. Игрок теряет ориентацию: «где я был? где враг?».
2. **5×3 default-zoom съедает viewport** — на 14×10 карте получается ~70×30 ячеек терминала, и тактическая обзорность хуже чем при 1×1. Sprites красивые, но они нужны для **атмосферы**, а не для **тактики**.
3. **Жёсткие хоткеи `a/d/h/g`** не расширяемы — для будущих заклинаний/cunning actions/feats нужна data-driven система с переназначаемыми клавишами.
4. **Карта может не помещаться** — на 50×50 локации (которые мы хотим в будущем) MapWidget просто переполняется. Нужен viewport с camera.

Этап L — UX-фундамент для последующих L+1 (заклинания), L+2 (открытый мир, переходы между локациями), L+3 (mouse + LocationArt).

## 2. Скоп

**Включено в L (этот спек):**

- **L1: Inline mode + 1×1 default + viewport**
  - Mode-state machine: `NORMAL | MOVE | TARGET`
  - Inline cursor на основной карте (move/target — без модальных окон)
  - Path preview для move (с цветом по бюджету движения)
  - Tab-cycle для выбора цели
  - Возврат default zoom = `small` (1×1)
  - Viewport с camera + auto-follow PC + manual pan
- **L2: Ability framework**
  - `Ability` dataclass + `AbilityRegistry`
  - Перенос существующих действий (Attack/Dodge/Dash/Disengage/Help/Search/Interact/Break) в Abilities
  - `Creature.abilities` + `Creature.keybindings` (переопределения)
  - Динамический action-bar в BattleScreen

**Отложено в L3 (отдельный спек после L1+L2):**

- LocationArtWidget (5×3 спрайты вокруг PC)
- Mouse-поддержка (click/scroll/hover)

**За скопом этапа L (в принципе):**

- Spells / spell slots / casting — отдельный этап M (после L2 framework готов).
- World map / location graph / переходы между локациями — отдельный этап N.

## 3. Целевые сценарии (acceptance)

1. **Inline move:** игрок в режиме боя нажимает `m`, видит курсор на своей клетке, стрелками двигает курсор, под путём рисуется preview `····` (зелёный если в бюджете, красный если превышен). Enter — двинулся, Esc — отменил. Карта не пропадала ни на секунду.
2. **Inline target:** игрок нажимает `a`, ближайший достижимый враг подсвечивается, в STATUS-панели появляется его HP/AC/distance. Tab переходит к следующему, Enter — атака.
3. **1×1 + viewport:** на карте 30×30 PC находится в центре viewport (auto-follow). При движении PC к краю карта прокручивается. PgUp/PgDn/Shift+стрелки — ручной pan.
4. **Ability rebind:** игрок может в конфиге (или, позже, UI-настройках) указать `keybindings.weapon_attack: "z"` — и `z` вместо `a` будет атакой.
5. **Action bar:** внизу экрана показаны доступные ability'и с их хоткеями вида `[a] Attack  [d] Dodge  [h] Dash  [g] Disengage`. Этот список собирается динамически из `actor.abilities`.

## 4. Архитектура

### 4.1 Layer ownership

```
domain/values/ability.py        Ability dataclass, AbilityId, EconomyCost
domain/entities/creature.py     +abilities: tuple[AbilityId,...]
                                +keybindings: dict[str, AbilityId]
application/abilities/registry.py   AbilityRegistry singleton, register_default()
interfaces/tui/screens/battle.py    BattleScreen + BattleMode state machine
interfaces/tui/screens/battle_modes/
   normal_mode.py               keypress→ability lookup, переходы в move/target
   move_mode.py                 курсор + path preview, Enter/Esc
   target_mode.py               Tab-cycle, выбор цели
interfaces/tui/widgets/map_widget.py
   +cursor, +highlights, +path_preview, +camera, +viewport_w/h
   +pan(), +center_on(), +visible_rect()
interfaces/tui/widgets/action_bar_widget.py  (новый) — динамический action-bar
```

**Что удаляется:**
- `interfaces/tui/screens/move_picker.py` (модал)
- `interfaces/tui/screens/target_picker.py` (модал)

(их функциональность переезжает в `battle_modes/*`)

### 4.2 BattleMode — state machine

```python
class BattleMode(Enum):
    NORMAL = "normal"
    MOVE = "move"
    TARGET = "target"
```

Transition table:
- `NORMAL → MOVE`: нажат hotkey ability'и с `requires_path=True` (Move/Dash используют общий вход)
- `NORMAL → TARGET`: нажат hotkey ability'и с `requires_target=True` (Attack/Help)
- `MOVE → NORMAL`: Enter (confirm), Esc (cancel)
- `TARGET → NORMAL`: Enter (confirm), Esc (cancel)

Каждый mode — отдельный модуль с pattern:
```python
class ModeHandler(Protocol):
    def on_enter(self, screen: BattleScreen) -> None: ...
    def on_key(self, screen: BattleScreen, key: str) -> bool: ...  # True если съел
    def on_exit(self, screen: BattleScreen) -> None: ...
    def overlay_data(self) -> tuple[Square | None, dict[Square, str], list[Square]]:
        """(cursor, highlights, path_preview) — для MapWidget."""
```

BattleScreen хранит `_mode_handler: ModeHandler` и делегирует keypress'ы ему.
Если handler вернул False — попытаться обработать как ability hotkey (только в NORMAL mode).

### 4.3 Ability framework

```python
# domain/values/ability.py
@dataclass(frozen=True)
class Ability:
    id: AbilityId              # str, "weapon_attack"
    name: str                  # "Attack"
    icon: str                  # 1 символ "a" (для action bar)
    default_hotkey: str        # "a"
    economy_cost: ActionEconomyCost
    requires_target: bool      # → mode TARGET
    requires_path: bool        # → mode MOVE
    intent_factory: Callable[..., PlayerIntent]  # см. 4.3.1
```

#### 4.3.1 Intent factory

Сигнатура зависит от того, что нужно собрать:
- `requires_target` → factory(actor, target_id) → AttackIntent
- `requires_path` → factory(actor, dest_square) → MoveIntent
- ни то, ни другое (Dodge, Dash, End) → factory(actor) → DodgeIntent

Технически — три аннотированных Protocol'а:

```python
class _NoParamFactory(Protocol):
    def __call__(self, actor: Creature) -> PlayerIntent: ...
class _TargetFactory(Protocol):
    def __call__(self, actor: Creature, target_id: CreatureId) -> PlayerIntent: ...
class _PathFactory(Protocol):
    def __call__(self, actor: Creature, path: list[Square]) -> PlayerIntent: ...

intent_factory: _NoParamFactory | _TargetFactory | _PathFactory
```

BattleScreen выбирает factory по `requires_target`/`requires_path` (один из трёх взаимоисключающих режимов). Mypy проверяет каждый call-site через явный narrow по флагам. Декларативно: одна ability — одна сигнатура factory.

#### 4.3.2 Registry

```python
# application/abilities/registry.py
class AbilityRegistry:
    def register(self, ability: Ability) -> None
    def get(self, id_: AbilityId) -> Ability
    def all(self) -> Iterator[Ability]

def register_default_abilities(registry: AbilityRegistry) -> None:
    """Регистрирует 8 встроенных: weapon_attack, dodge, dash, disengage,
    help, search, interact, break_object."""
```

В `composition.py` registry создаётся один раз и шарится через DI.

#### 4.3.3 Creature

```python
class Creature(BaseModel):
    ...
    abilities: tuple[AbilityId, ...] = (...)  # default — все 8 базовых
    keybindings: Mapping[str, AbilityId] = {}  # переопределения
```

Default (если `abilities` не указан) — 8 базовых для humanoid'а. Monster может иметь только подмножество (goblin без `help`/`search`).

#### 4.3.4 Action-bar построение

```python
def build_keymap(actor: Creature, registry: AbilityRegistry) -> dict[str, Ability]:
    keymap: dict[str, Ability] = {}
    for aid in actor.abilities:
        ability = registry.get(aid)
        key = actor.keybindings.get(aid, ability.default_hotkey)
        keymap[key] = ability  # override OK
    return keymap
```

BattleScreen вызывает это на каждом `TurnStarted(PC)` и обновляет ActionBarWidget.

### 4.4 Viewport

```python
class MapWidget(Static):
    camera: Square = Square(0, 0)   # top-left visible
    viewport_w: int = 80            # вычисляется через self.size.width
    viewport_h: int = 24
    follow_target: CreatureId | None = None
    safe_zone: int = 3              # ячеек от края — триггер auto-scroll

    def visible_rect(self) -> tuple[int, int, int, int]:
        """(x0, y0, x1, y1) видимой части в координатах битфилда."""

    def pan(self, dx: int, dy: int) -> None:
        """Сместить камеру (clamp к границам)."""

    def center_on(self, sq: Square) -> None:
        """Центрировать viewport на клетке."""

    def auto_follow(self, battlefield: Battlefield) -> None:
        """Если follow_target вышел за safe_zone — pan чтобы вернуть."""
```

Render-loop клипует к viewport rect: вместо `for y in range(height)` — `for y in range(y0, y1)`.

### 4.5 Path preview

В MOVE mode handler вычисляет path от позиции PC до cursor через `MoveAction.find_path()` (уже существует в `application/actions/move.py`). Сохраняет `list[Square]` и стоимость в футах. Передаёт в MapWidget как `path_preview` + цвет:
- `green` если `cost <= movement_remaining`
- `yellow` если `cost <= movement + dash_bonus`
- `red` если превышает

В MapWidget render — поверх terrain отрисовывает `·` на каждой клетке пути (для small zoom), окрашенным.

### 4.6 Highlights (для TARGET mode)

`highlights: dict[Square, str]` — клетка → CSS-style. В TARGET mode handler выставляет:
- На клетке выбранной цели — `reverse bold` (выделено).
- На клетках других достижимых целей — `bold` (доступно для выбора).

MapWidget применяет highlights поверх обычного render.

## 5. Data flow (последовательность для MOVE)

```
1. Игрок жмёт `m` в NORMAL mode.
2. NormalModeHandler.on_key("m"):
   - lookup keymap → Ability "move" с requires_path=True
   - проверка can_perform(actor, ctx) → если Forbidden, log и return
   - screen.enter_mode(MOVE)
3. MoveModeHandler.on_enter:
   - cursor = actor.position
   - compute initial path (пусто)
4. Игрок жмёт arrow:
   - MoveModeHandler.on_key("up"):
     - cursor = (cursor.x, cursor.y - 1)
     - path = MoveAction.find_path(actor.position, cursor, ctx)
     - cost = sum of square costs along path
     - screen.refresh_map(cursor, path_preview=path)
5. Игрок жмёт Enter:
   - MoveModeHandler.on_key("enter"):
     - intent = MoveIntent(actor.id, path)
     - screen.submit_intent(intent)
     - screen.enter_mode(NORMAL)
6. GameRunner processes intent → MoveAction.perform → events
7. EventRenderer обновляет MapWidget после TurnEvents
```

## 6. Tests

### 6.1 Unit

- `tests/unit/abilities/test_ability_dataclass.py` — frozen, валидация полей
- `tests/unit/abilities/test_registry.py` — register/get/all, дубликаты
- `tests/unit/abilities/test_default_registration.py` — все 8 базовых
- `tests/unit/tui/test_keymap_build.py` — build_keymap с overrides
- `tests/unit/tui/test_viewport.py` — camera clamp, pan, center_on, visible_rect
- `tests/unit/tui/test_map_render_viewport.py` — клиппинг render к viewport rect
- `tests/unit/tui/test_map_render_path_preview.py` — `·` на клетках пути с цветом
- `tests/unit/tui/test_map_render_highlights.py` — highlights поверх

### 6.2 Integration (Pilot)

- `tests/integration/tui/test_inline_move_mode.py`:
  - `m` → mode=MOVE, cursor виден
  - arrow → cursor двигается, path preview обновляется
  - Enter (в бюджете) → move выполнен, mode=NORMAL
  - Esc → mode=NORMAL без действия
  - Enter (превышен бюджет) → no-op, log сообщение
- `tests/integration/tui/test_inline_target_mode.py`:
  - `a` → mode=TARGET, ближайший враг подсвечен
  - Tab → следующий враг
  - Enter → AttackIntent
  - Esc → cancel
- `tests/integration/tui/test_viewport_follow.py`:
  - PC в углу → camera в углу
  - PC двинулся за safe_zone → camera сдвинулась
  - PgDn → ручной pan
- `tests/integration/tui/test_dynamic_keybindings.py`:
  - Creature с `keybindings={"z": "weapon_attack"}` → `z` атакует, `a` нет
- `tests/integration/tui/test_action_bar_updates.py`:
  - actor.abilities меняется → action bar перерисовывается

### 6.3 Regression

- 962 существующих теста должны остаться зелёными
- Особое внимание: `tests/integration/tui/test_ux_feedback.py` (только что добавленные)
- Тесты которые поднимали `MovePicker` / `TargetPicker` — переписываются на inline

## 7. Backwards compatibility

- **Domain слой:** не меняется (Action классы остаются как есть).
- **Creature:** `abilities`/`keybindings` — optional с default'ом, существующие тесты не ломаются.
- **MovePicker/TargetPicker:** удаляются. Импорты из них — заменяем (grep по `move_picker`/`target_picker`).
- **MapWidget API:** `refresh_from()` сигнатура расширяется (новые kwargs с default=None), старые вызовы остаются валидными.
- **Default zoom:** `medium` → `small`. Это **намеренный breaking change UX** (пользователь запросил). Документируется в CHANGELOG (или в README/TUI.md). Hotkey `+`/`-` остаётся: можно переключиться на medium вручную.

## 8. Декомпозиция этапа L на подэтапы (для writing-plans)

### L1: Inline UX + viewport + 1×1 default (~10 task'ов)
- L1.1: Default zoom = small + регрессионные тесты
- L1.2: Viewport (camera, pan, center_on, visible_rect)
- L1.3: MapWidget — cursor/highlights/path_preview API
- L1.4: BattleMode enum + state machine skeleton в BattleScreen
- L1.5: NormalModeHandler (lookup ability по hotkey)
- L1.6: MoveModeHandler + path preview integration
- L1.7: TargetModeHandler + Tab-cycle + STATUS-panel update
- L1.8: Удаление MovePicker/TargetPicker + миграция тестов
- L1.9: Pilot smoke L1 + сводный коммит L1

### L2: Ability framework (~8 task'ов)
- L2.1: domain/values/ability.py + AbilityId
- L2.2: AbilityRegistry + register_default_abilities (8 встроенных)
- L2.3: Creature.abilities + Creature.keybindings (с дефолтами)
- L2.4: build_keymap + интеграция в BattleScreen
- L2.5: ActionBarWidget (новый, динамический)
- L2.6: Миграция BattleScreen.BINDINGS → ability-driven
- L2.7: Pilot test: rebind hotkey работает
- L2.8: Сводный коммит L2

### L3: (отдельный спек после L1+L2 — здесь только зафиксирован)
- LocationArtWidget
- Mouse: on_click → cursor в MOVE/TARGET, on_scroll → pan, on_mouse_move → hover-tooltip

## 9. Открытые вопросы (отметить перед start)

- **OQ-1:** Где хранить keybindings — на Creature (per-creature) или глобально в Settings? **Решение:** на Creature; глобальные defaults — в `Ability.default_hotkey`. Settings (per-user) — задача поста-L3.
- **OQ-2:** При смене PC ход (multi-PC encounter) action bar перерисовывается полностью или по-разному per actor? **Решение:** полностью перерисовывается на TurnStarted.
- **OQ-3:** Path preview для Dash — отдельно или вместе с Move? **Решение:** одна общая ability "move" с `requires_path`, доп. бюджет от Dash виден цветом (yellow zone).
- **OQ-4:** TARGET mode — что если нет ни одной reach цели? **Решение:** ability.can_perform проверяется ДО входа в mode; если Forbidden — log + не входим в TARGET.

## 10. Definition of Done для этапа L

- ✅ Все 5 сценариев §3 проходят руками в `dnd play warehouse --tui`
- ✅ 962+N тестов зелёные (N = новые из §6, ожидаемо ~20-25)
- ✅ mypy strict / ruff clean
- ✅ Default zoom = small, картинка PC = `@` в 1 ячейке
- ✅ MovePicker/TargetPicker удалены
- ✅ AbilityRegistry с 8 базовыми, BattleScreen action-bar строится из неё
- ✅ Viewport scrolls на больших картах (тестируем на 30×30 синтетическом encounter)
- ✅ Документация: `docs/TUI.md` обновлена под mode-state machine, `docs/ABILITIES.md` (новый) — описание framework
- ✅ Коммиты под именем "Maxim Lokotkov" / anticrab@users.noreply.github.com

## 11. Инварианты для имплементации (явные anti-regression правила)

1. **Курсор НЕ выходит за границы битфилда** — clamp в move/target mode handler'е.
2. **При смене turn (TurnStarted) mode СБРАСЫВАЕТСЯ в NORMAL** — никаких «застрял в move-mode прошлого хода».
3. **Path preview никогда не показывает невалидный путь** — если `MoveAction.find_path` возвращает пусто, рисуем только cursor.
4. **TARGET mode НЕ открывается с пустым reach-списком** — проверка ability.can_perform ДО входа.
5. **Viewport НЕ скроллится во время mode=MOVE** при движении курсора (курсор может выйти за viewport — это OK, авто-scroll только при движении PC или ручном pan).
6. **Действия из `actor.abilities` СТРОГО валидируются** в AbilityRegistry на старте encounter'а — unknown id → fail fast.
7. **Default keybindings не дублируются** — registry.register_default_abilities проверяет коллизии хоткеев.

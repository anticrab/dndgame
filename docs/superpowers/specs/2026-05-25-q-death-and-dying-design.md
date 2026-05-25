# Этап Q: Death & Dying — Design

**Дата:** 2026-05-25
**Автор:** Maxim Lokotkov (github.com/anticrab)
**Статус:** черновик на ревью

---

## 1. Контекст и мотивация

После этапа O (инвентарь) в движке остаётся фундаментальный пробел против
правил D&D 5e (Книга Игрока 2024, «Падение до 0 хитов», стр. 27): существо
при 0 HP просто становится `not is_alive`, и бой немедленно завершается. Нет:

- спасбросков от смерти у персонажей игроков;
- состояния «без сознания, но ещё живой» (dying);
- стабилизации (Медицина / в будущем Spare the Dying);
- мгновенной смерти от огромного урона (massive damage) на уровне engine;
- лута трупов (хвост этапа O — отложен сюда).

Фундамент частично готов в domain и сейчас **не используется движком**:

- `domain/values/death_save_state.py` — полноценный иммутабельный
  `DeathSaveState` (успехи/провалы/stable, `apply_save_roll`,
  `apply_damage_at_zero`, `stabilized`, `reset`, `is_dead`, `is_stable`);
- `Creature.take_damage()` уже возвращает `was_lethal` и `killed_outright`
  (massive damage);
- `Creature.heal()` уже сообщает «поднял с 0 HP» (`revived`);
- `UnconsciousCondition` + `Creature.is_at_zero_hp` уже есть.

Этап Q — это в основном **wiring уже существующего domain в Encounter** плюс
небольшие новые срезы (флаг на Creature, StabilizeAction, CORPSE-объект,
события и TUI-overlay).

## 2. Скоп

**Включено в Q (этот спек):**

- **Death saves** — спасброски от смерти PC на старте своего хода
  (d20: ≥10 успех, <10 провал, нат-20 → 1 HP, нат-1 → 2 провала).
- **Dying state** — PC при 0 HP получает `Unconscious` + `DeathSaveState`,
  остаётся на карте, не «мёртв» пока не накопит 3 провала.
- **Урон по лежачему** — обычный удар → 1 провал, крит → 2 провала; атака
  в упор (≤5 фт) по лежачему — авто-крит (правило 2024).
- **Massive damage** — overflow ≥ max HP одним ударом → мгновенная смерть.
- **PC vs NPC развилка** — флаг `Creature.uses_death_saves`.
- **End-condition** — пересмотр условия конца боя (downed ≠ поражение).
- **StabilizeAction** — WIS(Медицина) DC10 по союзнику в 0 HP.
- **Лут трупов** — при смерти NPC спавнится `InteractableObject(kind=CORPSE)`
  с инвентарём покойного; лут через существующий Interact+Pickup механизм.
- **События** — `DeathSaveRolled`, `CreatureStabilized`, `CreatureDied`.
- **UI** — рендер событий в CLI/TUI логе + TUI death-save overlay (пипсы).

**Отложено (НЕ в Q):**

- `Spare the Dying` (заговор) — в этап P (заклинания).
- `Character`/`Monster` split, level/xp — этап R.
- `Drop`/`Equip`/`Unequip` интенты, encumbrance penalties — хвост O.
- Воскрешение (Revivify и т.п.), долгий отдых — позже.

## 3. Ключевые решения (выбраны на брейнсторме)

### 3.1. Метка PC/NPC — флаг на Creature

Новое поле `Creature.uses_death_saves: bool = False` (backward-compat через
default). Развязано с `Faction` (которая per-encounter и не свойство
существа). Честно описывает свойство существа: герой/важный NPC vs расходный
моб. Боссу-монстру тоже можно включить флаг.

**Отвергнуто:**
- *По `Faction.PARTY`* — Faction это per-encounter роль; дружественный
  NPC-наблюдатель или временно-NEUTRAL PC ломают семантику; монстру-боссу
  death-saves не выразить.
- *Character/Monster split* — тянет level/xp/statblock, премачюр для Q,
  риск сломать 1132 теста; это этап R.

### 3.2. Лут трупов — труп как InteractableObject

При смерти NPC движок кладёт `InteractableObject(kind=ObjectKind.CORPSE)` на
клетку с `state={open:False, locked:False, contents: dump_loot(inventory),
hp, ac}`. Лут переиспользует весь механизм O: Interact (open) + PickupAction
+ InventoryScreen, те же хоткеи `i`/`l`.

**Отвергнуто:**
- *Новая сущность `Corpse`* — чище семантически, но новый entity + новый
  Action + новый UI-flow ради чистоты; не оправдано для Q.
- *Отложить лут из Q* — пользователь явно хотел лут трупов; механизм O
  делает это дёшево, поэтому включаем.

### 3.3. End-condition — спасброски отыгрываются

Бой НЕ заканчивается при падении PC в 0 HP. На ходах лежачего PC
авто-бросок death save; враги могут добивать. Сторона **повержена** ⇔ нет
существ, которые либо `is_alive`, либо «спасаемы» (0 HP + `uses_death_saves`
+ не `is_dead`). PARTY побеждает ⇔ все MONSTERS не `is_alive` (даже если PC
лежит без сознания — он остаётся на карте dying).

**Отвергнуто:**
- *Мгновенный конец при down* — теряется вся механика death saves
  (нат-20 recover, стабилизация), ради которой и делаем этап.

## 4. Архитектура и компоненты

### 4.1. Domain — `Creature` (entities/creature.py)

Новые поля:

```python
uses_death_saves: bool = False
death_saves: DeathSaveState | None = None  # None пока HP>0
```

Новые/изменённые методы (меняют HP и death_saves согласованно):

- `begin_dying()` — вызывается при первом падении в 0 HP, если
  `uses_death_saves`: `self.death_saves = DeathSaveState()`. Для NPC — no-op
  (NPC просто `not is_alive`, его судьбу решает Encounter → CORPSE).
- `roll_death_save(d20_raw)` — делегирует `death_saves.apply_save_roll`;
  нат-20 → `heal(1)` + `death_saves = None`; иначе обновляет `death_saves`.
  Возвращает структуру с исходом (success/failure/recovered, новые счётчики).
- `take_damage(...)` — расширяется: если **до** удара HP уже был 0 и
  `uses_death_saves` → `death_saves = death_saves.apply_damage_at_zero(
  is_critical=...)`; если `killed_outright` → `death_saves =
  DeathSaveState(failures=3)`.
- `heal(amount>0)` при 0 HP → `death_saves = None` (приходит в сознание;
  снятие `Unconscious` — на уровне Encounter по `HealResult.revived`).
- `is_dead` property: `self.uses_death_saves and self.death_saves is not None
  and self.death_saves.is_dead`. Для NPC — отдельный механизм (Encounter
  убирает с поля в CORPSE; `is_alive` остаётся источником истины «жив ли»).

### 4.2. Engine — `Encounter` (application/engine/encounter.py)

- **При `was_lethal`** (обрабатывается там, где сейчас публикуется
  `AttackResolved.downed`): развилка по `uses_death_saves`. PC → `begin_dying()`
  + наложить `Unconscious` + событие. NPC → пометить на превращение в CORPSE
  (§4.5) + `CreatureDied`.
- **На старте хода** (`start_turn`) существа с 0 HP, `uses_death_saves`,
  `death_saves` не `is_stable` и не `is_dead`: авто-бросок d20 через
  `DiceRoller`, `roll_death_save`, публикуем `DeathSaveRolled`; если recovered
  — снять `Unconscious`; если стало `is_dead` — `CreatureDied` + CORPSE. Ход
  остаётся «пустым» (механизм `skipped = is_at_zero_hp` уже есть).
- **Урон по лежачему в упор**: атака с дистанции ≤5 фт по существу с 0 HP —
  авто-крит (передаём `is_critical=True` в `take_damage`). Это уже частично
  выражается через AttackAction; уточняется в плане.

### 4.3. End-condition (`_check_end_condition`)

```
def faction_defeated(faction):
    members = [c for c in participants if factions[c.id] == faction]
    return all(
        not c.is_alive
        and not (c.uses_death_saves and c.death_saves is not None
                 and not c.death_saves.is_dead)
        for c in members
    )
```

PARTY проигрывает ⇔ `faction_defeated(PARTY)` (все спасаемые мертвы). PARTY
побеждает ⇔ `faction_defeated(MONSTERS)`. Ничья по лимиту раундов — как сейчас.
`survivors` в `EncounterEnded` — те, у кого `is_alive` (лежачий PC не
survivor, но и не «убит»: отдельно отражаем в логе, что он dying).

### 4.4. Actions / Abilities

- `StabilizeAction` (application/engine/actions/stabilize.py) — цель: союзник
  в 0 HP, `uses_death_saves`, не stable, не dead, в пределах 5 фт. Бросок
  WIS(Медицина) vs DC10 через DiceRoller. Успех → `death_saves.stabilized()`
  + `CreatureStabilized`. Не выводит в сознание (нужно лечение).
- Новый `Ability` `stabilize` в `register_default_abilities` с дефолтным
  hotkey; добавляется в `Creature.ability_ids` по умолчанию.
- В одиночной партии латентно (нельзя стабилизировать себя без сознания),
  но правило-корректно и готово к multi-PC. `StabilizeIntent` в
  discriminated union + проброс в CLI/TUI/GameRunner.

### 4.5. Лут трупов

- Новый `ObjectKind.CORPSE`.
- При смерти NPC: Encounter убирает существо как боевую единицу и кладёт
  `InteractableObject(id=f"corpse-{creature_id}", kind=CORPSE, pos=last_pos,
  state={open:False, locked:False, hp:1, ac:5, contents:
  dump_loot_entries(dead.inventory.stacks)})`. Пустой инвентарь → `contents=[]`
  (труп открывается, пусто).
- Рендер `%` (red dim) переезжает с «трупа-существа» на CORPSE-объект; клетка
  проходима (как у трупов сейчас); живые существа рисуются поверх.
- Лут: `i` открыть → `l` InventoryScreen → `PickupAction`. Ноль нового UI.
  `PickupAction` уже работает с любым InteractableObject через `open`/`locked`.

### 4.6. События (application/dto/engine_event.py)

```python
class DeathSaveRolled(EngineEvent):
    actor_id: CreatureId
    d20_raw: int
    result: Literal["success", "failure", "recovered"]
    successes: int
    failures: int

class CreatureStabilized(EngineEvent):
    actor_id: CreatureId
    by: CreatureId

class CreatureDied(EngineEvent):
    actor_id: CreatureId
```

### 4.7. UI

- `EventPrinter` (CLI + TUI LogWidget) — новые handlers:
  - `🎲 aelar death save: 14 → success (1/3)`
  - `✚ cleric stabilizes aelar`
  - `💀 aelar died`
- TUI death-save overlay (mockup C.6 в TUI.md): когда у PC
  `death_saves is not None` — в `StatusWidget` строка пипсов
  `Death saves: [green]●●○[/] / [red]○○○[/]` (успехи / провалы).

## 5. Поток данных (happy path)

```
AttackAction наносит лет. урон PC
  → Creature.take_damage(was_lethal=True)
  → Encounter: PC.begin_dying() + наложить Unconscious
  → событие (downed)
... ход PC ...
  → start_turn: PC 0 HP, не stable
  → DiceRoller d20 → PC.roll_death_save(roll)
  → DeathSaveRolled(result, successes, failures)
  → если 3 успеха: stable; если нат-20: heal(1)+снять Unconscious;
    если 3 провала: CreatureDied + CORPSE
  → ход «пустой», end_turn
... союзник (multi-PC) ...
  → StabilizeAction → death_saves.stabilized() → CreatureStabilized
... либо все враги пали ...
  → _check_end_condition → EncounterEnded(winners=PARTY)
```

## 6. Обработка ошибок и инварианты

1. `death_saves is not None` ⟺ существо в dying (0 HP, ещё не мёртв/не
   поднят). Поднятие лечением или нат-20 → `death_saves = None`.
2. NPC (`uses_death_saves=False`) никогда не получает `death_saves`;
   при 0 HP → CORPSE, `is_alive=False`.
3. Стабилизация/спасброски на `is_dead` или `is_stable` — no-op (уже в VO).
4. CORPSE проходим и не перекрывает обстоятельства pathfinder'а (как трупы
   сейчас); `PickupAction` уважает `open`/`locked`.
5. End-condition: downed-but-not-dead PC держит PARTY в игре; смерть
   последнего спасаемого PC → поражение.
6. Все 1132 существующих теста остаются зелёными (backward-compat через
   `uses_death_saves=False` по умолчанию — старые сценарии ведут себя
   по-прежнему: NPC и PC без флага мрут мгновенно).

## 7. Тестирование

- **domain** (`Creature`): drop в 0 → death_saves инициализируется (только с
  флагом); roll_death_save success/failure/nat20/nat1; урон на 0 HP → провал;
  крит → 2 провала; massive damage → failures=3; heal → death_saves=None.
- **engine lifecycle**: down→saves→death; down→nat20→recover; down→heal→
  conscious; урон-в-упор по лежачему → 2 провала (авто-крит).
- **end-condition**: downed PC ≠ поражение; смерть PC = поражение; все враги
  мертвы при лежачем PC = победа PARTY.
- **StabilizeAction**: успех/провал Медицины; цель не в 0 HP → Forbidden;
  вне 5 фт → Forbidden.
- **corpse**: смерть NPC спавнит CORPSE с правильным contents; пустой
  инвентарь → пустой труп; CORPSE проходим; лут CORPSE через Pickup smoke
  (CLI + TUI pilot).
- **регрессия**: полный прогон pytest -q + mypy strict + ruff.

## 8. Monster AI

`SimpleMonsterAI` при выборе цели предпочитает существа с HP>0; если
единственная достижимая цель PARTY — лежачий PC (0 HP), монстр атакует его
(добивание, авто-крит в упор по правилам). Минимальная правка политики выбора
цели; без сложного «решать, добивать ли».

## 9. Декомпозиция задач

- **Q-1** `Creature.uses_death_saves` + `death_saves` + методы
  (`begin_dying`/`roll_death_save`/`is_dead`) + интеграция в `take_damage`/`heal`.
- **Q-2** Encounter: развилка при `was_lethal` (PC → dying+Unconscious;
  NPC → пометка на CORPSE).
- **Q-3** Encounter: авто death-save на старте хода лежачего PC.
- **Q-4** Урон по лежачему в упор → авто-крит (2 провала).
- **Q-5** End-condition: переписать `_check_end_condition` + `survivors`.
- **Q-6** События `DeathSaveRolled`/`CreatureStabilized`/`CreatureDied` +
  EventPrinter (CLI/TUI).
- **Q-7** `StabilizeAction` + `Ability` + `StabilizeIntent` + проброс.
- **Q-8** `ObjectKind.CORPSE` + спавн трупа при смерти NPC + рендер `%`.
- **Q-9** Corpse-loot wiring (reuse Interact+Pickup) + smoke.
- **Q-10** TUI death-save overlay (пипсы в StatusWidget).
- **Q-11** docs: новый `docs/DYING.md` + обновить ROADMAP/TUI.

## 10. Definition of Done

- `dnd play --tui` (и CLI): PC при 0 HP уходит без сознания, на своих ходах
  бросает death saves (видно в логе + overlay), враги могут добить; 3 провала
  → смерть → CORPSE; 3 успеха → stable; лечение/нат-20 → в сознание.
- Лут трупа павшего врага работает теми же `i`/`l`.
- End-condition корректен: лежачий PC не проигрывает мгновенно; победа при
  смерти всех врагов.
- 1132 + новые тесты зелёные, mypy strict / ruff clean.
- `docs/DYING.md` описывает модель; ROADMAP помечает Q как ✅.

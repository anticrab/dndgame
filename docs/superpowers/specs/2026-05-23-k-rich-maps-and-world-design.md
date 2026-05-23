# Spec — Этап K: богатые карты, sprite-движок, CLI-семья

**Дата:** 2026-05-23
**Автор:** Maxim Lokotkov
**Статус:** approved (по результатам brainstorming-сессии)

## Контекст

После закрытия этапа J (TUI MVP) пользователь сформулировал крупный
вектор развития:

* Карты — не «клеточки 5×5», а **полноценные локации** с богатым
  ландшафтом.
* TUI — спрайты, кратные квадрату, без рамок-разделителей;
  «пиксельартом рисовать стены, мебель, колонны, окна».
* Движок должен **читать ландшафт семантически**: понимать где
  пройти, где cover, где сломать; двери, окна, бочки, сундуки —
  интерактивные.
* **CLI первичен**: полная семья команд `dnd map / sprite / location`
  для управления контентом из shell, JSON-экспорт/импорт для скриптов;
  TUI и редактор — adapters над теми же Port'ами.
* Будущий вектор — открытый мир, переходы между локациями.

Текущая реализация (после fix(audit-18)) — single-zoom 1×1, базовые
`Terrain`-типы, один сценарий `mvp_skirmish`. Этап K — масштабная
переработка.

## Главный архитектурный принцип

Hexagonal-чистота поверх всего:

```
domain/application   — core: tile, sprite-meta, engine, actions, locations
       │
       │ Port: SpriteRegistry / MapRepository / LocationRepository
       │
   ┌───┴────────────────────┬──────────────────┐
   │                        │                  │
CLI-tools              TUI игра          TUI редактор    (+ будущий REST / web)
`dnd map/sprite/...`   `dnd play`         `dnd map edit`
```

Все интерфейсы используют **те же** Port'ы; engine не знает про UI и
формат хранения. JSON — interchange-формат; YAML — для людей; будущий
SQLite — другая реализация того же Port'а без правок engine.

## Цели этапа K

1. Sprite-система — YAML-content, four категорий (terrain/feature/
   object/creature).
2. Tile-модель — композит base + features + object_ref; passability/
   LoS читаются из неё.
3. TUI рендер 5×3 без рамок — визуально квадратные клетки на JetBrains
   Mono.
4. InteractAction + BreakAction — взаимодействие с окружением (двери,
   сундуки, бочки).
5. CLI-семья `dnd map / sprite / location` — полный набор управления
   контентом + JSON export/import.
6. TUI-редактор карт (`dnd map edit <id>`) — палитра + drag-paint.
7. Контент-набор: 7 разнообразных карт для playtest.
8. Локации (post-K core): Location-сущность + LocationRepository, но
   без полноценного open-world UI (это отдельный этап L).

### Что НЕ делаем в K (явно отложено)

* Полноценный exploration screen с переходами между локациями (L).
* Графический редактор картинок (мы про ASCII).
* Multi-zoom small + medium + large одновременно (только small для
  overview + medium 5×3 как default).
* Spell-objects (effects на клетке — будут после магии).

## Архитектурные решения

### Tile-модель (domain)

```
domain/values/sprite_meta.py:
    @dataclass(frozen=True, slots=True)
    class TerrainBase:
        id: str                         # "floor", "grass", "stone", "water", "dirt"
        name: str
        passable: bool
        difficult: bool
        glyph_5x3: tuple[str, str, str] # 3 строки по 5 ячеек
        glyph_1x1: str
        color_token: str                # ссылка на CSS-класс

    @dataclass(frozen=True, slots=True)
    class FeatureKind:
        id: str                         # "wall_v", "wall_h", "column", "table_small", ...
        name: str
        blocks_los: bool
        cover: CoverLevel
        blocks_passage_dirs: frozenset[Direction]
        passable_cost_ft: int           # 0 = непроход, 5 = норм, 10 = difficult
        glyph_5x3: tuple[str, str, str]
        glyph_1x1: str
        color_token: str

domain/values/tile.py:
    @dataclass(frozen=True, slots=True)
    class Tile:
        base: TerrainBase
        features: tuple[FeatureKind, ...]

        def passable_into(self, from_direction: Direction) -> bool: ...
        def blocks_los: bool ...
        def aggregate_cover() -> CoverLevel ...
        def movement_cost_ft() -> int ...

domain/entities/interactable.py:
    class InteractableObject:           # mutable, как Creature
        id: ObjectId
        kind: ObjectKind                # DOOR, CHEST, BARREL, WINDOW
        pos: Square
        state: dict[str, Any]           # {"open": False, "locked": True, "hp": 5, ...}
        sprite_id_by_state: dict[str, str]

        def interact(action: str) -> InteractionResult
        def take_damage(damage: DamageInstance) -> DamageResult
        def current_sprite_id() -> str

domain/values/object_kind.py:
    class ObjectKind(StrEnum): DOOR, CHEST, BARREL, WINDOW
```

`Battlefield` мигрирует:

```
Battlefield:
    _tiles: dict[Square, Tile]                          # вместо _terrain
    _objects_by_square: dict[Square, list[ObjectId]]    # mutable list
    _objects: dict[ObjectId, InteractableObject]

    def tile_at(sq) -> Tile
    def objects_at(sq) -> tuple[InteractableObject, ...]
    def set_tile(sq, tile)                              # для редактора
    def place_object(obj)
    def remove_object(obj_id)

    # Семантика — вычисляется по сумме Tile.features + object.state
    def passable_between(a, b) -> bool
    def line_of_sight(a, b) -> bool
    def cover_against(attacker, target) -> CoverLevel
```

Старые константы (`FLOOR`, `WALL`, `DIFFICULT`) реализуются как готовые
`Tile`-значения для совместимости.

### Sprite-система (контент)

YAML-формат:

```yaml
# data/content/sprites/features/wall_vertical.yaml
id: wall_vertical
category: feature
glyph_5x3: |
  │
  │
  │
glyph_1x1: │
color_token: wall
blocks_los: true
cover: total
blocks_passage_dirs: [E, W]
passable_cost_ft: 0
```

`SpriteRegistry` — Port, реализация `YamlSpriteRegistry`. Loader
читает все `data/content/sprites/**/*.yaml`, валидирует, кэширует в
памяти. `get_sprite(id)` → `SpriteMeta`. `list_by_category(...)` → для
редактора палитры.

Sprite — content. Любой может добавить новый sprite, положив YAML —
engine увидит без правок кода.

### Ports + Repositories

```
application/ports/
    sprite_registry.py        # load/get/list по категориям
    map_repository.py         # load/save/list/delete maps
    location_repository.py    # load/save/list locations (для post-K вектора)

infrastructure/content/
    yaml_sprite_registry.py
    yaml_map_repository.py
    json_map_repository.py   # для import/export
    yaml_location_repository.py
```

Все CLI-команды и игровой движок обращаются только через эти Port'ы.

### CLI-семья

```
dnd map list [--format=table|json]
dnd map show <id> [--zoom=small|medium] [--format=ascii|json]
dnd map validate <id>
dnd map new <id> --size=WxH [--fill=floor]
dnd map paint <id> --at=X,Y --base=<sprite_id>
dnd map paint <id> --at=X,Y --feature=<sprite_id>
dnd map paint <id> --at=X,Y --object=<kind> --state=<json>
dnd map import <file> [--format=json|yaml]
dnd map export <id> [--format=json|yaml]
dnd map edit <id>                       # TUI-редактор

dnd sprite list [--category=...] [--format=table|json]
dnd sprite show <id>                    # ASCII-превью 5×3 + меta
dnd sprite validate <id>

dnd location list
dnd location show <id>
dnd location graph                      # граф мира как DOT/ASCII
```

Каждая sub-команда — модуль в `interfaces/cli/`. Тесты — typer
CliRunner.

JSON-формат — каноничен для всех `--format=json` опций. Скрипты могут
строить pipeline'ы (`dnd map export A --format=json | jq ... | dnd map
import - --format=json`).

### TUI рендер 5×3

Один Tile = 5×3 ячеек терминала. На JetBrains Mono (aspect 0.6) — визуально
квадрат. Без рамок-разделителей — sprites склеиваются в единый пиксель-арт.

`MapWidget` получает `(battlefield, sprite_registry)`. Алгоритм:

```
for y in 0..height:
    for row in 0..3:                    # 3 строки на клетку
        for x in 0..width:
            tile = bf.tile_at(Square(x,y))
            base_glyph = sprite_registry.get(tile.base.id).glyph_5x3[row]
            features_overlay = composite([
                sprite_registry.get(f.id).glyph_5x3[row] for f in tile.features
            ])
            object_glyph = ...
            line = overlay(base_glyph, features_overlay, object_glyph)
            yield line                  # 5 ячеек
```

Цвета через CSS-классы `.tile-wall`, `.tile-pc` — `monochrome` тема
выключает их (как уже сделано).

Hotkey `+`/`-` переключает zoom (medium 5×3 ↔ small 1×1 для overview).

### Interact + Break Actions

```
application/engine/actions/interact.py:
    class InteractAction:
        economy_cost = FREE      # PHB-2024: free object interaction, 1/turn
        params: InteractParams { target_object_id, kind: open/close/use_key/examine }
        # Меняет state объекта, публикует ObjectInteracted event.

application/engine/actions/break_object.py:
    class BreakAction(AttackAction):
        economy_cost = ACTION
        # Подкласс AttackAction для атаки по InteractableObject (не Creature).
        # Имеет AC и HP; та же roll-механика; публикует AttackRolled / ObjectDamaged.
```

Расширение targeting'а: `AttackParams.target_id` сейчас `CreatureId` —
становится union `CreatureId | ObjectId`. AttackAction внутри —
disambiguation.

CLI/TUI меню действий: новый пункт `i Interact` — открывает picker
объектов в reach; новый пункт неявный — Attack автоматически целится
в objects тоже.

### TUI редактор

`dnd map edit <id>` — `TuiApp` в режиме `editor`:

```
EditorScreen:
    Header: "Editing: <id>"
    LeftPanel: PaletteWidget (Tab переключает категорию: base/feature/object)
    Center: MapWidget (тот же что в бою; курсор стрелками)
    BottomPanel: статус (cursor pos, active layer, active sprite, dirty флаг)
    Footer: BINDINGS — `enter` paint, `del` clear, `tab` switch layer,
            `s` save, `u` undo, `q` quit (with confirm if dirty)
```

Сохранение — через `MapRepository.save()`. Undo — stack последних N
изменений (in-memory). Превью — реальный рендер через тот же MapWidget,
сразу видно как будет в бою.

### Контент-набор карт

Семь карт в `data/content/maps/`, каждая в отдельном YAML:

| ID | Размер | Особенности | Что проверяет |
|---|---|---|---|
| `mvp_skirmish` | 5×5 | Открытое поле | Regression — старые тесты |
| `open_field` | 12×8 | Без препятствий | Базовый бой, OA, range |
| `dungeon_hall` | 15×8 | Коридор + 2 комнаты, дверь | Walls, doors, choke point |
| `forest_clearing` | 10×10 | Деревья (cover), grass (difficult) | Cover/difficult, ranged |
| `warehouse` | 14×10 | Бочки, стол, окно, дверь | Interactables: break/open |
| `bridge_crossing` | 18×6 | Узкий мост через воду | Pit/water, линия защиты |
| `ruined_hall` | 16×12 | Колонны, обломки, partial walls | Multi-layered, partial |

Каждая будет иметь YAML-формат под новый Tile-модель; sprite_id'ы
ссылаются на sprite-content. Sсenarios.yaml — отдельный файл, ссылается
на `map_id` (map ≠ scenario decomposition).

## Этапы реализации

Каждый этап — отдельный коммит с тестами. Параллельные таски —
независимые агенты через `dispatching-parallel-agents` skill.

| Этап | Что | Возможна параллель |
|---|---|---|
| **K1** | Domain Tile/Feature/Object + миграция Battlefield (alias-режим: старый Terrain → Tile) | — |
| **K2** | SpriteRegistry Port + YamlSpriteRegistry + 25 базовых sprites (terrain/features/objects/creatures) | K2 параллельно K1 после K1.1 |
| **K3** | MapRepository Port (YAML+JSON) + миграция scenarios.yaml на новый формат | После K1 |
| **K4** | CLI семья `dnd map / sprite / location` | После K3 |
| **K5** | TUI рендер 5×3 через SpriteRegistry — новый MapWidget | После K2 |
| **K6** | InteractAction + BreakAction + интеграция в TUI/CLI | После K5 |
| **K7** | TUI редактор `dnd map edit` | После K3+K5 |
| **K8** | Контент-набор: 7 карт + соответствующие scenarios | K8 после K2; финальные карты — после K6 |
| **K9** | Независимый аудит этапа K | После всех |

## Definition of Done этапа K

* `dnd map list / show / validate` работают для всех 7 карт.
* `dnd map show warehouse --zoom=medium --format=ascii` рисует
  читаемую 5×3 карту с бочками/дверями/окнами.
* `dnd map export warehouse --format=json | dnd map import - --as=copy`
  работает round-trip.
* В TUI `dnd play warehouse-encounter --tui` — реально можно сломать
  бочку, открыть дверь, спрятаться за колонной.
* TUI-редактор `dnd map edit warehouse` — рисуем стену, сохраняем,
  перезапускаем `dnd play` — изменение видно.
* `pytest -q` зелёный, mypy strict / ruff clean.
* Спрайт `monochrome`-темы корректно (без цветов на клетках).
* J-инвариант: `import textual` только в `interfaces/tui/`.

## Риски и снижения

| Риск | Снижение |
|---|---|
| Большой scope → длинный сlippage | Этапы по одному дню каждый; коммит после каждого, fix-on-failure. |
| Sprite ASCII не выглядит читаемо | Контент-набор small (25 sprites) для первой итерации; визуальная проверка через `dnd sprite show` после каждого добавления. |
| Backwards-compatibility ломаем 781+ тест | K1: alias-режим — старый Terrain → Tile, существующие тесты проходят. После K8 — отдельная миграция тестов. |
| Большая площадь правок Battlefield → регрессии | Pytest integration tests (новые) запускаются после каждого этапа; OA, cover, LoS — критические сценарии. |
| TUI редактор сложен → пользователь не использует | CLI `dnd map paint` обеспечивает базу; редактор — UX-обёртка. |

## Зависимости

* `textual >= 0.78` (уже установлен)
* `typer >= 0.12` (уже установлен)
* `pydantic v2` (уже установлен)
* `pyyaml` (уже установлен)
* Новое: ничего.

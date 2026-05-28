# W1+W2 — создание персонажа: дизайн (CharacterSpec → assemble → MonsterTemplate)

> Открывает серию **W** (см. ROADMAP §«Следующие этапы U–Y»). Закрывает блок
> «класс → вид → предыстория → характеристики → экипировка» в виде
> headless-ядра (W1) + CLI с интеграцией в `dnd play` (W2). TUI-визард и
> интерактивный выбор Fighting Style/подкласса на level-up (`FeatureChoiceRequired`)
> — отдельные подэтапы (W3, W4). См. `[[project_interactive_choice_deferred]]`,
> `[[project_item_use_restrictions_deferred]]`.

## 1. Решения (зафиксированы с пользователем)

- **Объём итерации:** W1 (ядро) + W2 (CLI + интеграция `dnd play --character`).
  TUI-визард, `FeatureChoiceRequired`-механика и закрытие T4-долга — **W3+**.
- **Модель PC:** новый `CharacterSpec` (исходные выборы игрока, application-DTO) →
  `CharacterAssembler.assemble()` (pure) → существующий `MonsterTemplate` →
  существующий `build_creature_from_template`. **`MonsterTemplate` не растёт**
  PC-полями: `species_id`/`background_id`/`ability_bumps` остаются в spec.
- **Контент в W1:** 2 вида (Человек, Эльф) + 2 предыстории (Солдат, Учёный).
  Расширение каталога — данные в YAML без правок кода.
- **Стратегии характеристик:** Standard Array + Point Buy. **4d6 drop-lowest
  отложен** (не нужен RNG в creation в первой итерации).
- **PHB-2024 распределение бонусов:** числовые бонусы (+2/+1 или +1/+1/+1) даёт
  **предыстория** (не вид); вид даёт только не-числовые фичи (Darkvision и т.п.).
- **DoD итерации:** `dnd character new/list/show` + `dnd play <scenario> --character <id>`
  (созданным PC реально играешь демо-сцену).
- **Классовые выборы на L1:** Fighting Style (Воин) — выбор простым CLI-prompt'ом;
  стартовая экипировка — **фиксированный пакет** из `classes.yaml` (без A/B вариантов).
- **Подход:** `CharacterSpec` → pure-функция-композер → `MonsterTemplate`
  (вариант A брейнсторма). Не Fluent Builder, не Step-Registry.
- **Persistence:** JSON-файл `~/.local/share/dnd/characters/<id>.json` (через
  `platformdirs.user_data_dir`). SQLite — этап Y.

## 2. Архитектура (потоки)

```
CLI (typer prompts)
   │
   ▼
CharacterSpec  ◄─── исходные выборы игрока (pydantic frozen DTO в application/dto/)
   │
   ├── class_id, species_id, background_id
   ├── name, id
   ├── abilities: AbilityArrangementSpec  (strategy_id + raw_scores)
   ├── ability_bumps: BackgroundBumpsSpec (+2/+1 или +1/+1/+1)
   └── fighting_style? (если класс требует — иначе None)
   │
   ▼ CharacterAssembler.assemble()  (pure-функция, application/services/)
MonsterTemplate  ◄─── существующий путь сборки runtime-Creature
   │
   ▼ build_creature_from_template   (без правок)
Creature  → Encounter → play
```

**Ключевые свойства:**

- `assemble()` детерминистичен: те же входы → тот же `MonsterTemplate`. RNG не
  трогаем — стратегия `4d6 drop-lowest` отложена.
- Виды/предыстории/классы — данные. Расширение каталога = новая запись YAML
  + регистрация фич в `FeatureRegistry` (если фича имеет реальный эффект).
- Origin feat от предыстории/вида в W1 → `FeatureId` в `Creature.always_on_features`,
  но в `FeatureRegistry` запись **no-op** (фактический эффект — W3 после
  `FeatureChoiceRequired`). Это закрывает место в коде без пустых заглушек.
- `CharacterRepository` хранит **`CharacterSpec`**, не `MonsterTemplate`.
  `MonsterTemplate` пересобирается из spec каждый раз — мигрирует автоматически
  при изменении правил сборки.

## 3. Контракты — DTO, типы, файлы

### 3.1 Application DTO

**`src/dnd/application/dto/character_spec.py`** (новый):

```python
class AbilityArrangementSpec(BaseModel):
    """Стратегия + сырое распределение (до бонусов предыстории)."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    strategy: str                  # "standard_array" | "point_buy"
    arrangement: dict[str, int]    # {"STR":15, ...} с ключами STR/DEX/CON/INT/WIS/CHA

class BackgroundBumpsSpec(BaseModel):
    """+2/+1 или +1/+1/+1 на характеристики из background.ability_options."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    bumps: dict[str, int]          # суммарно 3 очка, multiset values ∈ {{2,1}, {1,1,1}}

class CharacterSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: int = 1        # задел под Y (миграции)
    id: str                        # уникальный id для CharacterRepository
    name: str
    class_id: str
    species_id: str
    background_id: str
    abilities: AbilityArrangementSpec
    ability_bumps: BackgroundBumpsSpec
    extra_skills: tuple[str, ...] = ()   # Human.bonus_skill_choices=1 → 1 строка; Elf → ()
    fighting_style: str | None = None
    created_at: datetime
```

**`src/dnd/application/dto/templates.py`** (точечная правка):

```python
class MonsterTemplate(BaseModel):
    # ... существующие поля без изменений ...
    feature_ids: tuple[str, ...] = ()    # NEW: always-on фичи (виды/предыстории)
```

### 3.2 Шаблоны контента (виды/предыстории)

**`src/dnd/application/dto/templates.py`** (добавляются классы рядом с `MonsterTemplate`):

```python
class SpeciesTemplate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    name: str
    size: str                      # "small" | "medium" (W: medium); enum — пост-W
    speed_ft: int = Field(ge=0)
    feature_ids: tuple[str, ...] = ()
    bonus_skill_choices: int = 0   # Human: Skillful (1 доп. навык)
    languages: tuple[str, ...] = ()

class BackgroundTemplate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    name: str
    ability_options: tuple[str, ...]      # 3 рекомендованные характеристики PHB-2024
    skill_proficiencies: tuple[str, ...]  # ровно 2
    origin_feat_id: str | None = None     # в FeatureRegistry — no-op в W1
    starting_inventory: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    tool_proficiency: str | None = None   # строка-плейсхолдер (инструменты — пост-W)
```

### 3.3 Стратегии характеристик

**`src/dnd/application/services/ability_arrangement.py`** (новый):

```python
class AbilityArrangementStrategy(Protocol):
    id: ClassVar[str]
    def validate(self, arrangement: dict[str, int]) -> None: ...

@dataclass(frozen=True)
class StandardArrayStrategy:
    id: ClassVar[str] = "standard_array"
    _ARRAY: ClassVar[tuple[int, ...]] = (15, 14, 13, 12, 10, 8)
    def validate(self, arrangement: dict[str, int]) -> None:
        # ровно 6 ключей STR/DEX/CON/INT/WIS/CHA, multiset == _ARRAY

@dataclass(frozen=True)
class PointBuyStrategy:
    id: ClassVar[str] = "point_buy"
    _COSTS: ClassVar[dict[int, int]] = {8:0, 9:1, 10:2, 11:3, 12:4, 13:5, 14:7, 15:9}
    _BUDGET: ClassVar[int] = 27
    def validate(self, arrangement: dict[str, int]) -> None:
        # каждое значение ∈ 8..15, сумма cost == 27

ABILITY_STRATEGY_REGISTRY: dict[str, AbilityArrangementStrategy] = {
    StandardArrayStrategy.id: StandardArrayStrategy(),
    PointBuyStrategy.id: PointBuyStrategy(),
}
```

Реестр — модульный dict (как `ABILITY_SCORE_PROVIDERS` в проекте). Новая
стратегия = запись в реестре. Open/closed.

### 3.4 Композер

**`src/dnd/application/services/character_assembler.py`** (новый):

```python
@dataclass(frozen=True)
class CharacterAssembler:
    classes: ClassRepository
    species: SpeciesRepository
    backgrounds: BackgroundRepository
    content: ContentRepository      # weapon_by_id
    items: ItemRepository           # для resolve стартового пакета

    def assemble(self, spec: CharacterSpec) -> MonsterTemplate:
        """Pure: CharacterSpec → MonsterTemplate.

        Шаги:
        1. Финальные характеристики = arrangement + bumps (валидация ≤ 20 на L1).
        2. max_hp = class.hit_die_max + CON-mod  (L1: фикс. макс. кости).
        3. armor_class = 10 + DEX-mod (+ доспех из стартового пакета, если есть).
        4. speed_ft = species.speed_ft.
        5. proficiency_bonus = 2  (L1, всегда).
        6. skill_proficiencies = class.starting_skill_choices (выбранные игроком в spec — упрощение
           W1: берутся первые `count` из `class.starting_skill_choices.from`; полноценный
           выбор навыков класса — в W3) ∪ background.skill_proficiencies ∪ spec.extra_skills
           (бонусные навыки от вида, валидируются по `species.bonus_skill_choices`).
        7. feature_ids = species.feature_ids ∪ {background.origin_feat_id}.
        8. starting_inventory = class.starting_inventory ∪ background.starting_inventory.
        9. weapon_id = первое оружие из starting_inventory (heuristic: первый ItemKind.WEAPON).
        10. Для класса-кастера (wizard): spellcasting_ability / known_spells (cantrips L1)
            / spell_slots — из class.l1_spellcasting (новый блок в classes.yaml).
        """
```

### 3.5 Порты репозиториев

**`src/dnd/application/ports/species_repository.py`** (новый):

```python
class SpeciesRepository(Protocol):
    def load(self, species_id: str) -> SpeciesTemplate: ...
    def all(self) -> tuple[SpeciesTemplate, ...]: ...
    def contains(self, species_id: str) -> bool: ...
```

То же для `application/ports/background_repository.py` (BackgroundTemplate).

**`src/dnd/application/ports/character_repository.py`** (новый):

```python
class CharacterRepository(Protocol):
    def save(self, spec: CharacterSpec, *, overwrite: bool = False) -> None: ...
    def load(self, character_id: str) -> CharacterSpec: ...
    def all(self) -> tuple[CharacterSpec, ...]: ...
    def contains(self, character_id: str) -> bool: ...
    def delete(self, character_id: str) -> None: ...
```

### 3.6 Инфра

- **`src/dnd/infrastructure/content/yaml_species_repository.py`** — копия структуры
  `YamlClassRepository` (pydantic-load в `__init__`, кэш в `dict[str, SpeciesTemplate]`).
- **`src/dnd/infrastructure/content/yaml_background_repository.py`** — то же для предысторий.
- **`src/dnd/infrastructure/persistence/json_character_repository.py`** — JSON
  файлы в директории (по умолчанию `platformdirs.user_data_dir("dnd") / "characters"`,
  конструктор принимает `Path` для тестов).

### 3.7 Domain (точечная правка)

**`src/dnd/domain/entities/creature.py`**:

```python
always_on_features: frozenset[FeatureId] = frozenset()
```

Добавляется в `Creature.create(...)` как kwarg. В `build_creature_from_template`
(`src/dnd/application/engine/builder.py`) — копируем `template.feature_ids →
creature.always_on_features` и **применяем** через существующий `FeatureRegistry`
тем же путём, что level-up-фичи:

```python
for fid in creature.always_on_features:
    feature = FEATURE_REGISTRY.get(fid)
    feature.apply(creature)  # для no-op feature — пусто
```

## 4. Контент (YAML)

### 4.1 `data/content/species.yaml` (новый файл)

```yaml
- id: human
  name: Человек
  size: medium
  speed_ft: 30
  feature_ids: [resourceful]      # PHB-2024 Human: Resourceful, Skillful, Versatile
  bonus_skill_choices: 1
  languages: [common]

- id: elf
  name: Эльф
  size: medium
  speed_ft: 30
  feature_ids: [darkvision_60, fey_ancestry, keen_senses]
  bonus_skill_choices: 0
  languages: [common, elvish]
```

В W1 фичи `resourceful`, `darkvision_60`, `fey_ancestry`, `keen_senses` —
**no-op** записи в `FeatureRegistry` (зарегистрированы пустыми обработчиками).
Реальные эффекты — пост-W (часть в Y/X через ConditionService/Light).

### 4.2 `data/content/backgrounds.yaml` (новый файл)

```yaml
- id: soldier
  name: Солдат
  ability_options: [STR, DEX, CON]
  skill_proficiencies: [athletics, intimidation]
  origin_feat_id: savage_attacker      # no-op в W1
  starting_inventory: [longsword, javelin, javelin, javelin, javelin]
  # ↑ tuple[str, ...] — по одной единице каждого id; стаки делаются повторением
  #   (формат идентичен MonsterTemplate.starting_inventory из U5-3).
  tool_proficiency: gaming_set         # строка-плейсхолдер
  languages: []

- id: scholar
  name: Учёный
  ability_options: [INT, WIS, CHA]
  skill_proficiencies: [arcana, history]
  origin_feat_id: magic_initiate_wizard
  starting_inventory: [scholars_pack]   # один комплект items.yaml
  tool_proficiency: calligrapher_supplies
  languages: []
```

### 4.3 Расширение `data/content/classes.yaml`

Добавляются 3 поля к существующим записям классов:

```yaml
- id: fighter
  # ... существующие поля ...
  starting_skill_choices:
    count: 2
    from: [acrobatics, animal_handling, athletics, history, insight,
           intimidation, perception, survival]
  starting_inventory: [chain_shirt, shield]   # длинный меч — от soldier
  l1_choices:
    fighting_style:
      from: [defense, archery, dueling]

- id: wizard
  # ... существующие поля ...
  starting_skill_choices:
    count: 2
    from: [arcana, history, insight, investigation, medicine, religion]
  starting_inventory: [quarterstaff, arcane_focus_orb, spellbook]
  l1_spellcasting:
    ability: INT
    cantrips: [fire_bolt, mage_hand, prestidigitation]
    spell_slots: {1: 2}
    prepared_spells: [magic_missile, shield, sleep]

- id: rogue
  # ... аналогично ...
```

### 4.4 Расширение `data/content/items.yaml` (если потребуется)

В стартовых пакетах могут отсутствовать `gold_piece`, `quarterstaff`, `arcane_focus_orb`,
`spellbook`, `scholars_pack` и т.п. — добавляются по факту нехватки. Уже есть в
items.yaml: `chain_shirt`, `shield`, `longsword`, `javelin` (нужны как стак ×4).

### 4.5 Формат `characters/<id>.json`

```json
{
  "schema_version": 1,
  "id": "alyra",
  "name": "Альйра",
  "class_id": "fighter",
  "species_id": "elf",
  "background_id": "soldier",
  "abilities": {
    "strategy": "standard_array",
    "arrangement": {"STR": 15, "DEX": 14, "CON": 13, "INT": 12, "WIS": 10, "CHA": 8}
  },
  "ability_bumps": {"bumps": {"STR": 2, "DEX": 1}},
  "fighting_style": "defense",
  "created_at": "2026-05-28T14:00:00Z"
}
```

## 5. CLI

### 5.1 `dnd character new`

Файл: `src/dnd/interfaces/cli/commands/character.py` (новый, по образцу
существующего `map_cmds.py`).

Сигнатура:

```python
@character_app.command("new")
def character_new(
    name: str | None = typer.Option(None, "--name", "-n"),
    id_: str | None = typer.Option(None, "--id"),
    from_spec: Path | None = typer.Option(None, "--from",
        help="Загрузить готовый JSON CharacterSpec вместо интерактива."),
    force: bool = typer.Option(False, "--force",
        help="Перезаписать существующий персонаж с таким id."),
) -> None:
    ...
```

Интерактивный flow (одна реализация в helper `_interactive_create_spec`):

1. Имя (`typer.prompt`, default — генератор «Hero N»).
2. ID (`typer.prompt`, default — slug имени).
3. Класс (выбор из `classes.all()`).
4. Вид (выбор из `species.all()`).
5. Предыстория (выбор из `backgrounds.all()`).
6. Стратегия характеристик (`standard_array` / `point_buy`).
7. Распределение значений по STR/DEX/CON/INT/WIS/CHA — серия prompts с
   мгновенной валидацией стратегией.
8. Бонусы от предыстории (+2/+1 или +1/+1/+1; ключи из `background.ability_options`).
9. Если `species.bonus_skill_choices > 0` — prompt «выбери N навыков» (источник:
   объединённый список всех навыков, без дублей с классом/предысторией).
10. `fighting_style` — если `class.l1_choices.fighting_style` есть, выбор из списка.
11. Печать листа персонажа (через `_print_sheet`).
12. Сохранение в `CharacterRepository.save(spec, overwrite=force)`.

**`--from <path.json>`** обходит весь интерактив: читает JSON через
`CharacterSpec.model_validate_json`, валидирует через `assembler.assemble`, сохраняет.
Это путь для тестов и скриптов; e2e-тесты используют только этот режим.

### 5.2 `dnd character list` / `show <id>`

- `list` — табличный вывод (`rich.Table`): `id | имя | класс | вид | предыстория | HP | AC`.
- `show <id>` — полный лист (та же `_print_sheet`, что после `new`).

### 5.3 Интеграция `dnd play --character`

Файл `src/dnd/interfaces/cli/app.py` (модифицируется):

```python
@app.command("play")
def play(
    scenario_id: str,
    tui: bool = typer.Option(False, "--tui"),
    character_id: str | None = typer.Option(None, "--character", "-c"),
    # ... существующие опции ...
) -> None:
    deps = build_cli_dependencies(...)
    pc_override: MonsterTemplate | None = None
    if character_id is not None:
        spec = deps.character_repository.load(character_id)
        pc_override = deps.character_assembler.assemble(spec)
    # передаётся в сборку Encounter (см. §5.4)
    ...
```

### 5.4 Механизм подмены PC-спавна

Композиция (там, где из `ScenarioTemplate.spawns` строятся `Creature`):
- ищется ровно **один** спавн с `faction: PARTY`;
- его `MonsterTemplate` подменяется на `pc_override`, `instance_id` спавна
  сохраняется (`pc#1` или иной — без изменений в YAML карт и сценариев);
- если PARTY-спавнов в сценарии **0 или >1** и `--character` задан — ошибка
  `typer.Exit(1)` с понятным сообщением («сценарий не поддерживает override
  PC: ожидается ровно один PARTY-спавн, найдено N»).

## 6. Композиция

В `src/dnd/composition/__init__.py` (или `interfaces/cli/composition.py`):

- инстанцируются `YamlSpeciesRepository(content_dir / "species.yaml")` и
  `YamlBackgroundRepository(content_dir / "backgrounds.yaml")`;
- инстанцируется `CharacterAssembler(classes, species, backgrounds, content, items)`;
- инстанцируется `JsonCharacterRepository(platformdirs.user_data_dir("dnd") / "characters")`;
- всё доступно через `CliDependencies` namespace (как уже устроено для остальных репозиториев).

## 7. Валидация и ошибки

| Слой | Что валидируется | Ошибка |
|------|------------------|--------|
| `CharacterSpec` (pydantic) | формат полей, `schema_version`, `extra="forbid"` | `ValidationError` от pydantic |
| `AbilityArrangementStrategy.validate()` | standard_array: мультимножество `(15,14,13,12,10,8)`; point_buy: каждое 8..15, сумма cost == 27 | `ValueError("standard_array: ...")` / `ValueError("point_buy: budget exceeded")` |
| `BackgroundBumpsSpec` (post-validator) | сумма bumps == 3; multiset значений ∈ `{{2,1}, {1,1,1}}`; ключи — валидные строки из `Ability` enum | `ValueError("ability_bumps: ожидается +2/+1 или +1/+1/+1")` |
| `CharacterAssembler.assemble()` | существование `class_id`/`species_id`/`background_id`/`fighting_style` в репозиториях; ключи `bumps` ⊆ `background.ability_options` (семантическая ссылка); `len(spec.extra_skills) == species.bonus_skill_choices`; финальные характеристики ≤ 20 на L1 | `LookupError("species 'orc' not found")` / `ValueError("fighter requires fighting_style")` / `ValueError("ability_bumps keys must be subset of soldier.ability_options=[STR,DEX,CON]")` / `ValueError("species 'human' expects 1 extra skill, got 0")` |
| `CharacterRepository.save(...)` | уникальность `id` (без `overwrite=True`); доступ к директории | `FileExistsError("character 'alyra' already exists, use --force")` |
| `dnd play --character X` | существование `X`; ровно один PARTY-спавн в сценарии | `typer.Exit(1)` с сообщением |

Принципы:
- **Валидация в одном слое.** Структура — `CharacterSpec`. Арифметика —
  стратегия. Семантика ссылок — assembler. Не дублируем.
- **Никаких silent-default'ов.** Если `class.l1_choices.fighting_style` задан и
  `spec.fighting_style is None` → ошибка assembler'а (не «возьмём первый из списка»).
- CLI ловит `ValueError`/`LookupError`/`FileExistsError` через единый
  декоратор `@cli_error_boundary` (если уже есть — переиспользуем; если нет —
  добавляется в коммите CLI).

## 8. Тесты

**Размер:** ~10 unit + ~7 integration + 1 e2e + 1 regression-guard ≈ **20 новых тестов**.

### 8.1 Unit

| Файл | Что проверяет |
|------|--------------|
| `tests/unit/application/test_ability_arrangement.py` | `StandardArrayStrategy.validate`: принимает перестановку; отвергает дубли, отсутствующий ключ, лишние значения. `PointBuyStrategy.validate`: принимает 27-очковые распределения (несколько кейсов, включая 15/15/15/8/8/8 → 27); отвергает 26, 28, 16, 7. |
| `tests/unit/application/test_character_spec.py` | `CharacterSpec` round-trip через JSON. `BackgroundBumpsSpec` post-validator: ok для `{STR:2,DEX:1}`, `{STR:1,DEX:1,CON:1}`; fail для `{STR:2,DEX:2}`, `{STR:3}`, ключ `INT` при `options=[STR,DEX,CON]`. |
| `tests/unit/application/test_character_assembler.py` | Для синтетических species/background/class: финальные характеристики = arrangement + bumps; HP = hit_die_max + CON-mod (с CON+2 от bumps); skills = class ∪ background; feature_ids собираются (species ∪ origin_feat); weapon_id heuristic берёт первое WEAPON. |

### 8.2 Integration

| Файл | Что проверяет |
|------|--------------|
| `tests/integration/content/test_yaml_species_repository.py` | Загрузка `species.yaml`; оба вида читаются; `human.feature_ids == ("resourceful",)`; `elf.feature_ids` содержит `darkvision_60`. |
| `tests/integration/content/test_yaml_background_repository.py` | Загрузка `backgrounds.yaml`; `soldier.skill_proficiencies == ("athletics","intimidation")`; `scholar.ability_options == ("INT","WIS","CHA")`. |
| `tests/integration/content/test_w_content_smoke.py` | Каждая запись `species.yaml` ссылается на регистрированные FeatureId; каждый `background.starting_inventory` — на существующие item-id; `class.l1_choices.fighting_style.from` ⊆ зарегистрированных FeatureId. |
| `tests/integration/application/test_assemble_fighter_elf_soldier.py` | Полный путь: pre-built CharacterSpec → assemble → MonsterTemplate с конкретными числами (golden test): STR/DEX/CON/INT/WIS/CHA = (17,15,13,12,10,8); HP=11; AC=16; feature_ids содержит `darkvision_60`, `fey_ancestry`, `keen_senses`, `savage_attacker`; weapon_id=`longsword`; fighting_style=`defense`. |
| `tests/integration/application/test_assemble_wizard_human_scholar.py` | То же для волшебника: spellcasting_ability=INT, known_spells содержит fire_bolt, spell_slots={1:2}; bonus_skill (human) присоединяется к skill_proficiencies. |
| `tests/integration/persistence/test_json_character_repository.py` | Save/load round-trip; `all()` возвращает обоих после двух save; повторный save без `overwrite=True` → FileExistsError; delete удаляет файл. |
| `tests/integration/cli/test_character_commands.py` | `dnd character new --from <fixture.json>` → spec сохранён в репозитории + sheet выведен; `list` показывает обоих; `show alyra` показывает корректный sheet; ошибки (`--from` несуществующего файла, `id` уже существует) переводятся в typer.Exit с сообщением. |

### 8.3 E2E

| Файл | Что проверяет |
|------|--------------|
| `tests/e2e/test_character_play.py` | `dnd character new --from fighter_alyra.json` → `dnd play demo_skirmish --character alyra` (через ScriptedRNG до Victory). PC из CharacterSpec реально едет в Encounter, его характеристики/AC/HP/инвентарь = от assemble(spec). |

### 8.4 Regression-guard

| Файл | Что охраняет |
|------|--------------|
| `tests/integration/cli/test_play_without_character.py` | Существующий `dnd play demo_skirmish` (без `--character`) работает как раньше — дефолтный спавн PC из `monsters.yaml`, ничего не сломано. (Возможно уже покрыт существующим smoke; добавить только при отсутствии.) |

## 9. Что НЕ входит в W1+W2 (отложено)

| Долг | Куда |
|------|------|
| TUI-визард создания (по образцу T4-меню) | **W3** |
| `FeatureChoiceRequired` на level-up (выбор Fighting Style/Subclass через движок) — закрытие T4-долга | **W3+W4** |
| Реальные эффекты origin-feats (Lucky, Magic Initiate и т.п.) | **W3+** |
| Подвиды (Wood/High/Drow Elf) и полный набор PHB (10 видов + 16 предысторий) | **постепенно данными**, без правок кода |
| Стартовая экипировка с вариантами A/B и стартовое золото вместо пакета | **W3+** |
| Множественные PC-слоты в сценарии (`--character` для каждого PARTY-спавна) | **X1** (`GameSession`) |
| Ограничения свитков по классу/уровню — закрытие `[[project_item_use_restrictions_deferred]]` | **W3** |
| SQLite-репозиторий персонажей | **Y** |
| Стратегия `4d6 drop-lowest` (с RNG в creation flow) | **постепенно**, добавление в `ABILITY_STRATEGY_REGISTRY` |
| Реальные инструменты как сущность (`tool_proficiency` сейчас строка) | **постепенно** |

## 10. Совместимость и долги

- **`demo_skirmish` без `--character`** — без изменений. Дефолтный PC из
  `monsters.yaml` (warrior_veteran со starting_inventory). Покрыто
  regression-guard'ом §8.4.
- **`MonsterTemplate.fighting_style`/`subclass`** — остаются на месте (T4 пишет
  туда из YAML шаблона; новый `assemble()` пишет туда из spec). Долг T4 не
  закрывается этой итерацией — он явно перенесён в W3.
- **`Creature.always_on_features`** — добавляется без значения по умолчанию у
  существующих creature-инстансов (`frozenset()`). Backward-compat.
- **`MonsterTemplate.feature_ids`** — `default=()`. Существующие YAML без
  правок (пустой кортеж).

## 11. Структура файлов (новые / правки)

**Новые:**

```
src/dnd/application/dto/character_spec.py
src/dnd/application/ports/species_repository.py
src/dnd/application/ports/background_repository.py
src/dnd/application/ports/character_repository.py
src/dnd/application/services/ability_arrangement.py
src/dnd/application/services/character_assembler.py
src/dnd/infrastructure/content/yaml_species_repository.py
src/dnd/infrastructure/content/yaml_background_repository.py
src/dnd/infrastructure/persistence/__init__.py
src/dnd/infrastructure/persistence/json_character_repository.py
src/dnd/interfaces/cli/commands/__init__.py             # если не существует
src/dnd/interfaces/cli/commands/character.py
data/content/species.yaml
data/content/backgrounds.yaml
docs/CHARACTER.md                                       # документация этапа
tests/unit/application/test_ability_arrangement.py
tests/unit/application/test_character_spec.py
tests/unit/application/test_character_assembler.py
tests/integration/content/test_yaml_species_repository.py
tests/integration/content/test_yaml_background_repository.py
tests/integration/content/test_w_content_smoke.py
tests/integration/application/test_assemble_fighter_elf_soldier.py
tests/integration/application/test_assemble_wizard_human_scholar.py
tests/integration/persistence/test_json_character_repository.py
tests/integration/cli/test_character_commands.py
tests/integration/cli/test_play_without_character.py    # если ещё нет
tests/e2e/test_character_play.py
tests/fixtures/characters/fighter_alyra.json
tests/fixtures/characters/wizard_finn.json
```

**Правки:**

```
src/dnd/application/dto/templates.py                    # +SpeciesTemplate, BackgroundTemplate, MonsterTemplate.feature_ids
src/dnd/application/engine/builder.py                   # +применение always_on_features
src/dnd/domain/entities/creature.py                     # +always_on_features
src/dnd/composition/__init__.py                          # +Species/Background/Character repos, +Assembler
src/dnd/interfaces/cli/composition.py                   # +передача в CliDependencies
src/dnd/interfaces/cli/app.py                           # +character sub-app, +play --character override
data/content/classes.yaml                                # +starting_skill_choices, starting_inventory, l1_choices, l1_spellcasting
docs/ROADMAP.md                                          # пометка W1+W2 ✅
```

## 12. DoD

- `dnd character new --from tests/fixtures/characters/fighter_alyra.json` создаёт
  PC, печатает лист, сохраняет `~/.local/share/dnd/characters/alyra.json`.
- `dnd character new` без флагов проводит интерактивный wizard в CLI и сохраняет
  результат.
- `dnd character list` показывает таблицу с сохранёнными персонажами.
- `dnd character show alyra` печатает лист.
- `dnd play demo_skirmish --character alyra` запускает демо-бой с этим PC
  (вместо дефолтного `warrior_veteran`); сценарий проходим (ScriptedRNG e2e
  до Victory).
- Все гейты зелёные: `ruff check` + `ruff format --check` + `mypy src` + `pytest -q`.
- Контент-смок зелёный: `species.yaml`/`backgrounds.yaml` ссылаются только на
  существующие FeatureId и item-id.
- Regression: `dnd play demo_skirmish` (без `--character`) работает как до W.

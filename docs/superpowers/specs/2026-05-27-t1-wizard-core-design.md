# Этап T1 — Каркас волшебника (играбельный маг) + профициентные спасброски

> Первый срез большого этапа T (волшебник + прогрессия L1–L3). Цель: волшебник,
> который кастует через меню способностей по правилам книги. Попутно закрываем
> отложенный пункт аудита — профициентные спасброски классов.
> Декомпозиция: T1 (этот) → T2 (интересные/контролящие заклинания) → T3 (боевые
> условия) → T4 (подклассы/фичи L1–L3 всех классов).

## 1. Контекст / что уже есть

- Заклинания (P1/P2/P2b): `Spell`, `SpellRepository`, `CastSpellAction` (ATTACK/
  SAVE/AUTO/HEAL/BUFF + AoE + MULTI), расход слотов `consume_spell_slot(level)`,
  `Creature.spell_save_dc`/`spell_attack_bonus` (= 8/+prof+mod, обновляются с
  `proficiency_bonus`). `mage_apprentice` — INT-кастер с `known_spells` + `spell_slots`.
- Прогрессия (R1): `ClassProgression`/`ClassLevel` (есть `spell_slots: dict|None`,
  автоприменяется `LevelUpService`), `XpAwardService`/`LevelUpService`.
- Способности (L2/S): `Ability` (id/icon/hotkey/economy/`requires_target`/
  `requires_path`/factory), `AbilityRegistry`, `Creature.ability_ids`, меню
  способностей (`AbilityMenuScreen`, `Tab`), `spell_ability()` строит `Ability`
  из заклинания (но только для цифровых хоткеев 1–9 и только `requires_target`
  для SINGLE; AREA проваливается как «без таргетинга»).

## 2. Чего нет (объём T1)

### 2.1 Класс `wizard`
`data/content/classes.yaml` + (если надо) поля `ClassProgression`:
- `hit_die: 1d6`; уровни L1–L3 с таблицей слотов:
  - L1 `spell_slots: {1: 2}`, L2 `{1: 3}`, L3 `{1: 4, 2: 2}` (PHB-2024 таблица Wizard).
  - `proficiency_bonus: 2` на L1–L3.
- Фичи: L1 — `arcane_recovery` (ресурс: 1× short rest восстановить слот; для T1 —
  минимально как `ResourceSpec`, восстановление слота — упрощённо или no-op-маркер,
  полноценно при необходимости позже), L2/L3 — пусто (подкласс L3 → T4).
- Содержит `saving_throw_proficiencies: [INT, WIS]` (см. 2.2).

`LevelUpService` уже ставит `creature.spell_slots = dict(lvl.spell_slots)` —
проверить, что слоты растут по уровням мага.

### 2.2 Профициентные спасброски (закрывает отложенное из аудита)
- `ClassProgression.saving_throw_proficiencies: frozenset[Ability]` (+ парсинг
  в `classes.yaml`/`YamlClassRepository`): Воин `{STR, CON}`, Плут `{DEX, INT}`,
  Маг `{INT, WIS}`.
- `Creature.saving_throw_proficiencies: frozenset[Ability]` (default пусто;
  заполняет `build_creature_from_template` из класса, и/или фича на L1).
- **Единая точка броска спасброска** — хелпер `roll_saving_throw(actor, ability,
  dc, ctx) -> bool` (application/engine): `d20 + ability_mod + (prof, если
  ability in saving_throw_proficiencies) + adjustments(SAVING_THROW)`; учитывает
  advantage/disadvantage. Применить:
  - в `SaveSpellHandler` (сейчас `d20 + mod`, без prof);
  - в concentration-CON-save (REV-1, сейчас `d20 + CON_mod`).
- Шаблоны монстров: `saving_throw_proficiencies` не задаются (default пусто) —
  обычные монстры без профициентных спасбросков (упрощение MVP).

### 2.3 Заклинания как `Ability` в меню (+ `requires_area`)
- `Ability` получает поле `requires_area: bool = False`; `__post_init__` запрещает
  более одного из `requires_target/requires_path/requires_area`.
- `spell_ability()` выставляет:
  - `requires_target = targeting.kind is SINGLE`;
  - `requires_area = targeting.kind is AREA`;
  - (MULTI — пока через существующий цифровой хоткей → `BattleMode.MULTI_TARGET`;
    из меню MULTI добавим позже, помечаем как нескоуп T1.)
- **Меню/триггер:** `BattleScreen._trigger_ability` и `_open_ability_menu`
  учитывают `requires_area` → вход в существующий `BattleMode.AREA` (закрывает
  стык из спека S). Точка входа в AREA уже есть (цифровой хоткей AoE-заклинания);
  переиспользуем её.
- **Спеллы в `ability_ids`:** хелпер `spell_ability_ids(actor, spell_repo) ->
  tuple[AbilityId,...]` + регистрация соответствующих `Ability` в реестр, чтобы
  заклинания актора попадали в меню (источник меню — `ability_ids`). Где
  собирать: в `set_active_turn`/composition (там, где уже строится spell-keymap).
  Цифровые хоткеи 1–9 сохраняются.

### 2.4 Контент / играбельность
- `mage_apprentice`: добавить `character_class: wizard`, `level: 1`, привести
  `spell_slots` к таблице L1 (`{1: 2}`) — теперь маг level-up-абелен и слоты от
  класса.
- Демо-хук: добавить мага-PC в сценарий (либо в `demo_skirmish` вторым PC, либо
  отдельный `mage_skirmish` уже есть — обновить под класс), чтобы маг кастовал из
  меню в живой игре.

## 3. Расширяемость / инварианты
- Слоты/фичи мага — **данные** (classes.yaml); рост уровней — через готовый
  `LevelUpService`.
- Спасбросок — **одна** точка (`roll_saving_throw`), prof-логика не дублируется.
- Меню читает `ability_ids` → новые заклинания появляются без правок UI.
- `requires_target ∧ requires_path ∧ requires_area` взаимоисключающие
  (`Ability.__post_init__`).
- Обратная совместимость: монстры без `saving_throw_proficiencies` (пусто),
  существующие спасброски-тесты — пересчитать там, где теперь добавился prof
  (морально могли «протухнуть»).

## 4. Тестирование
- `wizard` грузится; слоты по уровням 1→2→3 после `LevelUpService` (`{1:2}`→
  `{1:3}`→`{1:4,2:2}`).
- `roll_saving_throw`: профициентный спасбросок добавляет prof, непрофициентный —
  нет; advantage/disadvantage учитываются. `SaveSpellHandler` использует его
  (Воин CON-save vs маг — с prof).
- concentration-save (REV-1) использует prof для профициентных в CON (Воин).
- `requires_area` в `Ability` + взаимоисключение в `__post_init__`.
- Pilot: маг открывает меню (`Tab`) → видит заклинания; выбор AoE-заклинания →
  `BattleMode.AREA`; выбор SINGLE → `BattleMode.TARGET`.

## 5. Вне scope T1
- Новые/контролящие заклинания (Sleep/Hold Person/…), правка уровней Fireball/
  Lightning Bolt → **T2**.
- Боевые условия (cross-creature advantage, авто-крит, Dodge-saves, авто-провалы)
  → **T3**.
- Подклассы L3, Fighting Style, Cunning Action, полноценный Arcane Recovery → **T4**.
- Spellbook/подготовка заклинаний — пост-MVP (фиксированный known-list).
- MULTI-заклинания из меню (Magic Missile/Bless) — через цифровой хоткей; меню
  для MULTI — отдельным шагом позже.

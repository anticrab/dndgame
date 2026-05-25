# Этап P1: Заклинания — фундамент — Design

**Дата:** 2026-05-25
**Автор:** Maxim Lokotkov (github.com/anticrab)
**Статус:** черновик на ревью

---

## 1. Контекст и мотивация

После этапа Q (death & dying) корректна модель «жив / без сознания / мёртв», и
лечащие/боевые заклинания обретают смысл. Заклинания — крупная подсистема;
пользователь хочет в перспективе **много** заклинаний с корректной обработкой
каждого, включая **AoE по зоне** и **выбор нескольких целей**, плюс удобную
**справку** по заклинанию/способности (зерно будущей базы знаний).

Чтобы не утонуть и катить рабочий продукт инкрементально, этап P разбит:

- **P1 (этот спек):** фундамент — модель данных `Spell` (сразу с полями под
  таргетинг и описание), `SpellRepository` (YAML), `CastSpellAction`,
  упрощённые ячейки, 5 заклинаний (single-target / self / auto-hit), возврат
  `ActionBarWidget`, события.
- **P2 (позже):** AoE-формы (сфера/линия/конус) + мультитаргет — резолвинг в
  движке и выбор с клавиатуры в TUI.
- **P3 (позже):** справка/inspect по заклинанию-способности → база знаний.

Уже заложено: `SpellId` (dto/ids), `Creature.concentration: SpellId | None`,
`Ability` framework (L2, data-driven `intent_factory`), `DiceRoller`,
`AttackAction`/`StabilizeAction` как образцы, `take_damage`/`heal`,
`ModifierApplier`, conditions.

## 2. Скоуп

**Включено в P1:**

- `Spell` value-объект (frozen) с полями под будущий таргетинг и описание.
- `SpellRepository` (Port) + `YamlSpellRepository` + `data/content/spells.yaml`.
- Поля spellcasting на `Creature`: `spellcasting_ability`, `spell_slots`,
  `known_spells` (backward-compat через default — не-кастер).
- Деривации: spell attack bonus и save DC.
- `CastSpellAction` (один, switch по `effect`): ATTACK / SAVE / AUTO / HEAL /
  BUFF + концентрация.
- 5 заклинаний: Fire Bolt, Sacred Flame, Magic Missile, Cure Wounds,
  Shield of Faith.
- `CastSpellIntent` + проброс в `GameRunner`.
- Динамические `Ability` из `known_spells` + возврат `ActionBarWidget`
  (`[1] Fire Bolt …`).
- Событие `SpellCast` + рендер в `EventPrinter` (CLI + TUI-лог).
- Сценарий выдаёт PC заклинания + слоты.
- `docs/SPELLS.md`.

**НЕ в P1 (отложено):**

- AoE-формы и мультитаргет (резолвинг + TUI-выбор) — P2. Поля в модели данных
  заложены, но `CastSpellAction` в P1 обрабатывает только SELF / SINGLE.
- Справка/inspect-экран и база знаний — P3 (поле `description` заполняется уже
  в P1, но UI его пока не показывает).
- Reaction-каст (Shield как реакция), upcasting (каст на слот выше), ритуалы,
  материальные компоненты, классовые таблицы ячеек (→ R), мультиклассинг.
- Magic Missile в P1 — все дротики в одну цель (распределение по нескольким — P2).

## 3. Ключевые решения

### 3.1. Архитектура каста — data-driven + один `CastSpellAction` (выбран A)

`Spell` — декларативные данные; единственный `CastSpellAction` исполняет по
`spell.effect` (switch на 5 веток). `Ability`/keymap ссылаются на `spell_id`.
Добавление заклинания = строки в YAML + (при новой механике) ветка switch.

**Отвергнуто:** класс на заклинание (B — дубли, расходится с data-driven духом);
реестр SpellEffect-хендлеров (C — переусложнение ради 5 заклинаний; switch
легко мигрирует в C, когда заклинаний станет много, без изменения данных).

### 3.2. Модель данных сразу под AoE/мультитаргет/справку

Даже реализуя в P1 только single/self, `Spell` несёт `targeting: TargetingSpec`
(вид цели + место под форму/число целей) и `description: str`. Это «заклад»,
чтобы P2/P3 не ломали модель и YAML-контент.

### 3.3. Упрощённая модель ячеек

`Creature.spell_slots: dict[int, int]` (level → осталось), заговоры (level 0)
безлимитны. Слоты задаются при создании PC (сценарий/фабрика), без классовой
таблицы — она появится в R. Каст level>0 тратит слот; нет слота → Forbidden.

### 3.4. Spellcasting-способность на `Creature`

`spellcasting_ability: Ability | None` (None = не-кастер). spell attack
= `proficiency_bonus + mod(spellcasting_ability)`; save DC
= `8 + proficiency_bonus + mod(spellcasting_ability)` (PHB-2024 стр. 233).

## 4. Архитектура и компоненты

### 4.1. `domain/values/spell.py`

```python
class SpellEffect(StrEnum):
    ATTACK = "attack"   # spell attack roll → урон
    SAVE = "save"       # цель кидает спасбросок vs DC → урон (пол/полный)
    AUTO = "auto"       # авто-попадание → урон (Magic Missile)
    HEAL = "heal"       # восстановление HP
    BUFF = "buff"       # модификатор/состояние на цель (± concentration)

class TargetKind(StrEnum):
    SELF = "self"
    SINGLE = "single"
    MULTI = "multi"      # P2
    AREA = "area"        # P2

@dataclass(frozen=True, slots=True)
class TargetingSpec:
    kind: TargetKind
    max_targets: int = 1          # для MULTI (P2)
    area_radius_ft: int = 0       # для AREA (P2)
    # форма AoE (sphere/line/cone) — добавится в P2

@dataclass(frozen=True, slots=True)
class Spell:
    id: SpellId
    name: str
    level: int                    # 0 = заговор
    school: str
    effect: SpellEffect
    targeting: TargetingSpec
    range_ft: int
    description: str
    dice: str | None = None       # "1d10" / "1d8" / "3d4+3" (см. ниже)
    damage_type: DamageType | None = None
    save_ability: Ability | None = None   # для SAVE
    save_for_half: bool = True            # успех save → половина урона
    concentration: bool = False
    heal_dice: str | None = None          # для HEAL ("1d8+mod" → mod подставит action)
    ac_bonus: int = 0                     # для BUFF (Shield of Faith +2)
    # валидация в __post_init__: level>=0; ATTACK/AUTO/SAVE требуют dice+damage_type;
    # SAVE требует save_ability; HEAL требует heal_dice; BUFF — ac_bonus или condition.
```

Magic Missile (`3d4+3` фиксированно «3 дротика по 1d4+1») в P1 моделируется как
`AUTO` с `dice="3d4+3"` (все в одну цель). Точное «3×(1d4+1) с раздачей» — P2.

### 4.2. `SpellRepository` (Port) + `YamlSpellRepository`

По образцу `ItemRepository` (application/ports + infrastructure/content):
`list_ids()`, `load(spell_id)`, `contains(spell_id)`. Один YAML
`data/content/spells.yaml` — список заклинаний; guard на дубли id;
отсутствие файла → пустой репозиторий.

### 4.3. `Creature` (entities/creature.py)

Новые поля (default — не-кастер):
```python
spellcasting_ability: Ability | None = None
spell_slots: dict[int, int] = field(default_factory=dict)
known_spells: tuple[SpellId, ...] = ()
```
Методы:
- `spell_attack_bonus() -> int` (raise/0 если не кастер — вызывающий проверяет);
- `spell_save_dc() -> int`;
- `has_spell_slot(level) -> bool` (level 0 → всегда True);
- `consume_spell_slot(level)` (level 0 → no-op).

### 4.4. `CastSpellAction` (application/engine/actions/cast_spell.py)

`CastSpellParams(spell_id, target_id: CreatureId | None)`.
`can_perform_against`: actor — кастер; `spell_id in known_spells`; для level>0
есть слот; цель валидна по `targeting` (SELF → актор; SINGLE → существо в range);
экономика ACTION (cantrip тоже action в MVP). `execute`: тратит слот (level>0) +
ACTION, switch по effect:
- **ATTACK**: spell-attack roll (d20 + spell_attack_bonus) vs AC → при попадании
  `take_damage(dice)`; крит удваивает кости (через DiceRoller, как `AttackAction`).
- **SAVE**: бросок урона; цель кидает спасбросок `save_ability` vs `spell_save_dc`;
  успех + `save_for_half` → половина, иначе 0/полный.
- **AUTO**: `take_damage(dice)` без броска атаки.
- **HEAL**: `target.heal(heal_dice + mod)`.
- **BUFF**: применить эффект (Shield of Faith → +2 AC через `ModifierApplier`
  или временный Condition); при `concentration=True` — `_start_concentration`.
Публикует `SpellCast` + переиспользует `DamageDealt`/`AttackRolled` (для ATTACK)
и эффекты урона/хила.

**Концентрация:** `_start_concentration(caster, spell_id)` — если у кастера уже
есть `concentration`, прежнее заклинание-эффект завершается (снимается баф),
ставится новое. Поле `Creature.concentration` уже существует.

### 4.5. Интенты + Ability + ActionBar

- `CastSpellIntent(spell_id, target_id: CreatureId | None)` в discriminated
  union `PlayerIntent`; `GameRunner._do_cast` (нужен `SpellRepository`).
- `spell_ability(spell) -> Ability` строит `Ability` из заклинания:
  hotkey из позиции (`1..9`), `requires_target = targeting.kind is SINGLE`,
  `intent_factory` → `CastSpellIntent`.
- BattleScreen строит keymap из `known_spells` (через repo) и **возвращает
  `ActionBarWidget`** (скрыт в M) с полосой `[1] Fire Bolt [2] Sacred Flame …`.

### 4.6. События + UI

`SpellCast(caster_id, spell_id, slot_level, target_id)` (DTO). `EventPrinter`:
`✨ aelar casts Fire Bolt at goblin`; далее обычные `AttackRolled`/`DamageDealt`/
heal-строки. Для SAVE — строка исхода спасброска (переиспользуем существующий
рендер save, либо добавим в SpellCast флаг).

## 5. Поток данных (Fire Bolt, happy path)

```
UI: [1] → TARGET mode → выбор goblin → CastSpellIntent(fire_bolt, goblin)
GameRunner._do_cast → CastSpellAction.can_perform_against (Allowed)
 → execute: spend ACTION (cantrip — без слота)
 → SpellCast(aelar, fire_bolt, 0, goblin)
 → effect=ATTACK: d20+spell_attack vs AC → hit
 → DamageDealt(1d10 fire) → goblin.take_damage
 → (если 0 HP → Q-логика: NPC → CORPSE)
```

## 6. Инварианты

1. Не-кастер (`spellcasting_ability is None`) не может кастовать — `CastSpellAction`
   возвращает Forbidden; backward-compat: существующие существа не меняются.
2. `spell_id` должен быть в `known_spells` актора.
3. level>0 без слота → Forbidden; заговор (level 0) безлимитен.
4. Концентрация: одновременно одно concentration-заклинание; новое снимает старое.
5. Урон/хил идут через `Creature.take_damage`/`heal` — death-saves/CORPSE (Q)
   работают без изменений.
6. Все 1162 существующих теста зелёные (новые поля Creature — через default).

## 7. Тестирование

- domain: `Spell.__post_init__` валидация по effect; `YamlSpellRepository`
  (load/contains/дубли/пустой файл); `Creature` деривации (attack/DC), слоты.
- `CastSpellAction` по ветке: ATTACK (hit/miss/крит), SAVE (provsuccess→half,
  fail→full), AUTO, HEAL (не выше max), BUFF (+AC) + concentration-replace.
- слоты: трата level1, нет слота → Forbidden, cantrip безлимит; не-кастер →
  Forbidden; неизвестное заклинание → Forbidden.
- интеграция: `CastSpellIntent` через GameRunner; `spell_ability` + ActionBar
  pilot (полоса `[1]…`); CLI cast пункт; `SpellCast` рендер.
- регрессия: pytest -q + mypy strict + ruff.

## 8. Декомпозиция задач

- **P1-1** `Spell` + `SpellEffect`/`TargetKind`/`TargetingSpec` + валидация.
- **P1-2** `SpellRepository` (Port) + `YamlSpellRepository` + `spells.yaml` (5).
- **P1-3** `Creature` spellcasting-поля + `spell_attack_bonus`/`spell_save_dc`/
  слоты.
- **P1-4** `CastSpellAction` — ATTACK (Fire Bolt).
- **P1-5** + SAVE (Sacred Flame).
- **P1-6** + AUTO (Magic Missile).
- **P1-7** + HEAL (Cure Wounds).
- **P1-8** + BUFF/concentration (Shield of Faith).
- **P1-9** `CastSpellIntent` + `GameRunner._do_cast` + проброс `SpellRepository`.
- **P1-10** `spell_ability` + возврат `ActionBarWidget` в BattleScreen.
- **P1-11** `SpellCast` событие + EventPrinter.
- **P1-12** сценарий: PC получает `known_spells` + `spell_slots` +
  `spellcasting_ability`.
- **P1-13** `docs/SPELLS.md` + ROADMAP.

## 9. Definition of Done

- `dnd play` (CLI и TUI): PC-кастер видит полосу `[1] Fire Bolt …`, кастует все
  5 заклинаний; урон/хил/бафф/save работают корректно; слоты тратятся, заговоры
  безлимитны; концентрация заменяется; death-saves/CORPSE от заклинаний работают.
- Добавление нового заклинания того же типа — только строки в `spells.yaml`.
- 1162 + новые тесты зелёные; mypy strict / ruff clean.
- `docs/SPELLS.md` описывает модель; ROADMAP помечает P1.

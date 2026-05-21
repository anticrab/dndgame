# Аудит 14: Vertical Slice (этап G) — Weapon + AI + composition + E2E

**Автор:** Maxim Lokotkov
**Дата:** 2026-05-22
**Под ревью:**

- `src/dnd/domain/values/attack_kind.py`
- `src/dnd/domain/values/weapon.py`
- `src/dnd/application/engine/actions/weapon_attack.py`
- `src/dnd/application/engine/ai/simple_monster.py`
- `src/dnd/composition.py`
- `src/dnd/domain/entities/creature.py` (поля `proficiency_bonus`, `equipped_weapon`)
- `src/dnd/application/engine/actions/attack.py` (re-export `AttackKind`)
- `tests/unit/application/actions/test_weapon_attack.py`
- `tests/e2e/test_smoke_combat.py`

**Прогон тестов:** `pytest -q` → **656 passed in 1.04s**.

**Не оценивалось** (вне MVP G по тех. заданию): SQLite (этап H), CLI (этап I), spells / классы PC / multiclass.

---

## 1. Резюме

Slice **архитектурно корректен** и закрывает свою цель: composition root собирает `EncounterDependencies` из infra/domain/application слоёв без протечек, `WeaponProfile` живёт в `domain.values` (не зависит от application), `weapon_attack_params` — application-helper над `AttackParams`. AI работает как stateless-функция (`take_monster_turn`), e2e-сценарий «Воин vs Гоблин» сходится, событийная цепочка `InitiativeRolled → TurnStarted → AttackResolved → EncounterEnded` собирается через шину.

**Ключевые S1** (без них вертикальный slice технически работает только для «нормальных» оружий и положительных модификаторов):

- **VS-R001 (S1)** — `UNARMED_STRIKE` неработоспособен в реальной атаке. Конструкция `damage_expr="0"` + сборка `+{ability_mod:+d}` производит строки `"0"` / `"+3"` / `"-2"`, ни одна из которых не парсится `DiceExpr.parse` (регулярка требует литерал `d`/`к`). `AttackAction.execute` падает с `DiceParseError` при первом же `damage_roll`.
- **VS-R002 (S1)** — для отрицательных модификаторов (STR ≤ 7) суммарный `damage_roll.total` может быть `< 0` (например, `1d8-2` → roll=1, total=-1). Это пройдёт через `AttackAction` и сразу же упадёт с `ValueError` в `DamageInstance.__post_init__`. PHB-2024 стр. 26 требует «минимальный урон 0», и клампа нет ни в action, ни в dice.
- **VS-AI001 (S1)** — `SimpleMonsterAI._find_nearest_hostile` **игнорирует `hostile_factions`** (явно `del hostile_factions`) и считает врагами любого видимого не-actor'а. Это значит, что монстр атакует и `Faction.NEUTRAL`, и потенциально союзника-монстра, если оба окажутся в одном `Encounter`. На MVP-сценариях два-фракционно — не баг, но именно это противоречит докстрингу публичной функции, и контракт легко нарушить.
- **VS-G001 (S1)** — отсутствует guard от бесконечного цикла в `Encounter`/AI: если AI стабильно идёт в `Dodge` (нет цели / нет weapon / нет path), а у противника тоже нет способа добить — `is_concluded` не наступает. `_MAX_TURNS=30` есть только в тестах, в продакшен-цикле верхнего уровня лимита нет. Strictly это smell, но для smoke-tier — пограничный S1.

**S0** не обнаружено: текущие тесты проходят, основной happy-path не падает.

---

## 2. Архитектура — S0 / S1 / S2

### VS-A001 (S2) — `weapon_attack_params` нарушает «AttackParams даёт готовые числа»

`AttackParams.damage_expr` документирован (стр. 87–106 `attack.py`) как «базовый урон оружия, включая ability_mod». `weapon_attack_params` собирает его строковой конкатенацией:

```python
damage_expr = f"{weapon.damage_expr}{ability_mod:+d}"  # "1d8+3"
```

Это эквивалентно тому, что в `attack.py` уже специально **запрещено** (см. AT-R001 / 08-аудит: «DiceExpr.parse не поддерживает 1d8+3+2»). Конкатенация работает на старте, но как только `weapon.damage_expr` сам будет содержать модификатор (например, +1 zach. оружие — `"1d8+1"`), запись `"1d8+1+3"` сломает парсер.

**TODO.**

- Парсить `weapon.damage_expr` через `DiceExpr.parse` сразу в `weapon_attack_params`, затем `dataclasses.replace(dice, modifier=dice.modifier + ability_mod)` и `str(dice)`. Это та же техника, что в `AttackAction.execute`. Тест `test_weapon_damage_expr_with_built_in_bonus_keeps_single_modifier` обязателен.

### VS-A002 (S2) — `SimpleMonsterAI` зависит от строки `"dodging"` лишь косвенно

`take_monster_turn` пользуется `DodgeAction` / `combat_stances` без явного импорта `CombatStance` — это **правильно** на текущем срезе (нет циркуляра), но `AttackAction.execute` тоже хардкодит литерал `"dodging"`. Раз slice уже выходит на «общий язык AI ↔ stances», стоит вынести строковый ключ в `domain.values.combat_stance` (или хотя бы `Final[str] DODGING = "dodging"` в `stances.py`), чтобы переименование стойки не разъезжалось по двум местам.

### VS-A003 (S2) — `build_default_dependencies` создаёт `ConditionRegistry` + регистрирует defaults на каждый вызов

В composition root `register_default_conditions(registry)` зовётся **при каждой сборке боя**. Регистрация не идемпотентна по семантике (см. реестр), но и не оптимизирована. На MVP — приемлемо; пост-MVP стоит вынести «глобальный реестр» в модуль-level singleton, а composition только цеплял его. Аналогичная мысль в `02_interfaces_contracts.md`.

### Что **архитектурно ОК**

- `WeaponProfile` живёт в `domain.values` и зависит только от `Ability`, `DamageType`, `AttackKind` — все domain. **Корректно**.
- `attack_kind.py` вынесен отдельно, чтобы и domain-`WeaponProfile`, и application-`AttackAction` пользовались общим enum без зависимости domain → application. **Решение правильное** (см. `attack.py` стр. 61, re-export `AttackKind` через `__all__` — обратная совместимость для тестов).
- `composition.py`: `build_scripted_dependencies` **переиспользует** `build_default_dependencies`, передавая `rng=` и `event_bus=`. Дублирования нет.
- `take_monster_turn` как stateless-функция — на MVP оправдано: нет внутреннего состояния (нет «помню, кого атаковал»), нет конфигурации (агрессивность, KPI). Когда понадобится memory/profile — превращать в класс с `__call__`. Сейчас функция дешевле.
- `proficiency_bonus` / `equipped_weapon` добавлены через `Creature.create` с валидацией (`2..6`). PHB-2024 стр. 32 покрывается, инвариант `current == max` сохранён.

---

## 3. Правила PHB-2024 — S0 / S1 / S2

### VS-R001 (S1) — `UNARMED_STRIKE` неработоспособен

PHB-2024 стр. 209: «Урон безоружного удара = 1 + модификатор Силы, дробящий». В `weapon.py` запрограммировано:

```python
UNARMED_STRIKE = WeaponProfile(..., damage_expr="0", ...)
```

И в `weapon_attack_params`:

```python
if ability_mod == 0 or weapon.damage_expr == "0":
    damage_expr = (
        weapon.damage_expr if ability_mod == 0
        else f"{ability_mod:+d}"
    )
```

Что получается:

| STR  | mod | сформированный `damage_expr` | `DiceExpr.parse` |
| ---- | --- | ---------------------------- | ---------------- |
| 10   | 0   | `"0"`                        | **FAIL**         |
| 16   | +3  | `"+3"`                       | **FAIL**         |
| 6    | -2  | `"-2"`                       | **FAIL**         |

Воспроизведено напрямую: `DiceExpr.parse("+3")` → `DiceParseError: cannot parse dice expression: '+3'`. То есть **любая** атака unarmed-strike падает в `AttackAction.execute` при `DiceExpr.parse(params.damage_expr)`.

Дополнительно: даже если бы парсер принял пустые/нулевые броски, **формула неверна** — книжное «1 + STR» даёт минимум 1 урона даже при STR=10. Текущая реализация даёт 0 (без «+1»).

**TODO.**

- Ввести явный `WeaponProfile.flat_damage: int = 0` (или служебное поле «base flat» / «no_dice»), которое означает «без кубиков, чистый модификатор». `weapon_attack_params` тогда возвращает `damage_expr = f"{flat + mod:+d}"` **только если** `DiceExpr` поддерживает «чистое число» (а не поддерживает — см. парсер). Либо моделировать unarmed как `"1"` через специальный flag «no dice → используем replace(DiceExpr(...), ...)` напрямую в action.
- Альтернатива (минимальная для MVP): задать `damage_expr="1d1"` для unarmed, формула совпадёт с книжной «1 + mod».
- Юнит-тест `test_unarmed_strike_attack_does_not_crash_and_deals_min_one_damage`.

### VS-R002 (S1) — отрицательный итоговый урон не клампится

PHB-2024 стр. 26: «Итоговый урон не меньше 0». Сейчас:

- `weapon_attack_params(STR=6, longsword)` → `damage_expr="1d8-2"` — парсится.
- `damage_roll.total` для roll=1 → `-1`.
- `AttackAction.execute`: `target.take_damage(DamageInstance(amount=damage_roll.total, ...))` → **`ValueError: damage amount must be >= 0`**.

Сейчас тесты на это не падают, потому что во всех smoke-сценариях STR ≥ 10. Но для NPC-карликов / debuff-стека это runtime crash.

**TODO.**

- В `AttackAction.execute` после `damage_roll = ctx.dice_roller.roll(...)` сделать `amount = max(0, damage_roll.total)` перед `DamageInstance(...)`. Скорее всего, корректнее зашить «минимум 0» в `DiceExpr.roll` для broll'ов с purpose=DAMAGE — но это шире, и трогает контракт DiceRoller. Минимальный фикс — в action.
- Тест `test_damage_roll_is_clamped_to_zero_when_modifier_negative_and_roll_low`.

### VS-R003 (S2) — proficiency bonus всегда учитывается, без proficiency-флага

PHB-2024 стр. 25: «Добавляется только если существо обучено владению этим оружием». Сейчас `weapon_attack_params` всегда прибавляет `creature.proficiency_bonus + ability_mod` — нет флага «is_proficient_with(weapon)». Для MVP («все умеют всё своё стартовое») это OK, но это **долг** на этап Equipment/Character. Зафиксировать TODO в docstring `weapon_attack_params`.

### Что **по правилам ОК**

- `attack_bonus = proficiency + ability_mod` (PHB-2024 стр. 25, 32) — корректно для штатных оружий.
- Finesse через `max(STR_mod, DEX_mod)` — реализовано аккуратно (`>= dex_mod` — STR; иначе DEX), что соответствует PHB-2024 стр. 212.
- `proficiency_bonus = 2` по умолчанию для уровня 1 (PHB-2024 стр. 32).
- Тесты `test_finesse_picks_higher_of_str_dex` / `test_higher_proficiency_bonus_applies` хорошо ловят базовые правила.

---

## 4. AI / Smoke — поведение

### VS-AI001 (S1) — `hostile_factions` молча игнорируется

Подпись:

```python
def take_monster_turn(actor, ctx, *, hostile_factions: frozenset[str]) -> None:
```

и сразу:

```python
def _find_nearest_hostile(actor, ctx, hostile_factions):
    del hostile_factions  # MVP: фильтр не применяем — см. docstring
    ...
    for cid, cr in ctx.participants.items():
        if cid == actor.id or not cr.is_alive ...
            continue
```

То есть на MVP **любой не-actor** считается hostile. В двухфракционном бою это совпадает с задачей, но:

1. Если в `Encounter` появится `Faction.NEUTRAL` (бесчувственный наблюдатель, мирный пленник), AI вынесет его первым.
2. Контракт docstring подсказывает иное («множество значений Faction»), и при чтении публичного API легко принять за работающее.
3. `TurnContext` уже несёт `participants` и `battlefield`, но **не** несёт фракции. Это — настоящая причина, по которой реализовать filter невозможно «здесь и сейчас». Это и есть архитектурный «знак»: либо `TurnContext.factions: Mapping[CreatureId, Faction]` пробросить, либо отказаться от параметра.

**TODO.**

- Решение А: пробросить `factions: Mapping[CreatureId, Faction]` в `TurnContext` (это сделано в `participants`, симметрично), убрать параметр `hostile_factions` из AI и считать врагами всё, чья `factions[cid] in hostile_set`.
- Решение Б: оставить параметр, но **реально** фильтровать `ctx.participants` через side-channel (`Encounter` передаёт `factions` в AI отдельно). Сейчас это сделано наполовину.
- Тест `test_ai_does_not_attack_neutral_targets`.

### VS-AI002 (S2) — нет UNARMED_STRIKE fallback в AI

Если у actor нет `equipped_weapon` — AI идёт в `Dodge`. Это эквивалентно «безоружный сидит и ждёт». Книжно правильнее было бы взять `UNARMED_STRIKE` (PHB-2024 стр. 209). Но: см. VS-R001 — `UNARMED_STRIKE` сейчас ломает движок. Поэтому Dodge — **прагматичный fallback**, но это маскирует баг. Чинить вместе с VS-R001.

### VS-AI003 (S2) — `_path_towards` не уважает occupancy

Комментарий в коде честно говорит: «препятствия (другие existo на клетке) на MVP игнорируем». Это значит, что AI пройдёт сквозь союзника и попробует встать на занятую клетку. `Battlefield.move_creature` пускает (Q1 — мультиокупация), но в реальной игре это будет странное поведение. Уже задокументировано как Q1, оставляю как S2 на будущее.

### VS-G001 (S1) — нет hard-guard от бесконечного боя в Encounter

В smoke-тестах верхний цикл сам ограничен (`_MAX_TURNS=30`). В реальном цикле (`while not enc.is_concluded`) — нет. Если оба AI сваливаются в `Dodge` (например, у обеих сторон закончились weapon'ы или нет LoS), бой не закончится никогда. Это пограничный S1: на текущих сценариях не воспроизводится, но любой будущий «monster без weapon» (см. VS-AI002) или «карта с разорванной LoS» откроет дыру.

**TODO.**

- Добавить в `Encounter`: счётчик «раундов без damage-dealing-событий», и при превышении (например, 50) — публиковать `EncounterEnded(winners=None, reason="stalemate")`. Это не книга, но защитная мера от runaway-loop.
- Альтернатива: оставить как «забота вызывающего», но **зафиксировать в `ENCOUNTER.md`** обязательство верхнего цикла иметь watchdog.

### Smoke-тесты — что хорошо, что нет

**Хорошо:**

- `test_smoke_warrior_kills_goblin` ловит и happy-path, и событийный порядок (`InitiativeRolled < TurnStarted < AttackResolved < EncounterEnded`).
- `test_smoke_monster_ai_moves_then_attacks` доказывает, что AI делает связку «move + attack» и попадает по PC.
- `_MAX_TURNS=30` — разумный fuse.

**Slabosti (S2):**

- Все смоки приколочены к конкретным rolls. Это **нормально для smoke** (детерминированность важнее реализма), но любая правка `AttackAction.execute` (например, появление concentration-save после damage) сместит индекс ScriptedRNG и развалит тест без явной семантической причины. Это известный риск.
- Нет смок-сценария «полный round, оба промахиваются»: warrior d20=1 (crit miss), goblin d20=1, … round 2. Сейчас цепочка `AttackResolved → EncounterEnded` проверяется, но `RoundEnded → RoundStarted` для второго раунда — не покрыто smoke'ом.
- Нет смок-сценария «оба ranged, без movement». На MVP не критично.

---

## 5. Пропущенные тесты

1. `test_weapon_damage_expr_with_built_in_bonus_keeps_single_modifier` (VS-A001) — +1 longsword (`damage_expr="1d8+1"`) + STR=16 (+3) должен дать парсимый `1d8+4`, не `"1d8+1+3"`.
2. `test_unarmed_strike_attack_does_not_crash_and_deals_min_one_damage` (VS-R001).
3. `test_damage_roll_is_clamped_to_zero_when_modifier_negative_and_roll_low` (VS-R002).
4. `test_ai_does_not_attack_neutral_targets` (VS-AI001).
5. `test_ai_falls_back_to_dodge_when_no_path_to_target` (VS-G001 косвенно): актёр окружён непроходимыми клетками — должен быть `dodging`.
6. `test_smoke_two_rounds_eventually_concludes` — миссы обоих сторон в первом раунде, попадание во втором; проверка `RoundStarted(round_number=2)` в captured.
7. `test_weapon_attack_params_with_negative_modifier_does_not_produce_unparsable_expr` — STR=8 (-1) с longsword → `"1d8-1"` (граничный случай парсера).

---

## 6. Сводный TODO

| ID        | S   | Что делать                                                                                          | Где                              |
| --------- | --- | --------------------------------------------------------------------------------------------------- | -------------------------------- |
| VS-R001   | S1  | Починить UNARMED_STRIKE: либо `damage_expr="1d1"`, либо явный путь без `DiceExpr.parse` для flat-урона | `weapon.py`, `weapon_attack.py`  |
| VS-R002   | S1  | Клампить `damage_roll.total` к 0 перед `DamageInstance(...)`                                       | `attack.py:386-390`              |
| VS-AI001  | S1  | Реально фильтровать целей по фракции (пробросить `factions` в `TurnContext` или в AI напрямую)     | `simple_monster.py`, `turn_context.py` |
| VS-G001   | S1  | Watchdog stalemate в `Encounter` либо обязательство в `ENCOUNTER.md` для вызывающего              | `encounter.py` / `ENCOUNTER.md`  |
| VS-A001   | S2  | Сборка `damage_expr` через `DiceExpr.parse + replace(modifier=...)`                                | `weapon_attack.py:60-66`         |
| VS-A002   | S2  | Вынести `"dodging"` в константу `CombatStance.DODGING.value` (`Final[str]`), использовать везде     | `stances.py`, `simple_monster.py`, `attack.py` |
| VS-A003   | S2  | `ConditionRegistry` сделать lazy-singleton либо явный «default registry»                            | `composition.py`                 |
| VS-R003   | S2  | Завести флаг `is_proficient_with(weapon)` на пост-MVP                                              | `creature.py` / `weapon_attack.py` |
| VS-AI002  | S2  | После починки VS-R001 — давать AI UNARMED_STRIKE как fallback вместо Dodge                          | `simple_monster.py`              |
| VS-AI003  | S2  | Учитывать occupancy в `_path_towards` (Q1 будущее)                                                  | `simple_monster.py:_path_towards` |
| —         | S2  | Добавить семь тестов из раздела 5                                                                  | `tests/...`                      |

---

**Итог:** S0 не найдено, slice пригоден для следующего этапа (H — SQLite) после починки VS-R001/VS-R002/VS-AI001/VS-G001. Архитектура «WeaponProfile в domain, helper в application, AI stateless, composition разделён на default/scripted» — выбрана корректно и согласована с предыдущими аудитами.

---

## Применённые фиксы (2026-05-22)

**S1 — закрыто:**

* **VS-R001** — `UNARMED_STRIKE` удалён из `weapon.py` (импорт и __all__).
  Текущий `damage_expr` обязан быть dice-формы (`"1d8"`); чистый
  bonus-only (unarmed «1 + STR mod») не поддерживается без расширения
  damage-формата. Закомментировано прямо в коде с явным указанием
  на аудит. weapon_attack_params упрощён: убрана ветка `weapon.damage_expr == "0"`.

* **VS-R002** — clamp `raw_damage = max(0, damage_roll.total)` в
  `AttackAction.execute` перед `DamageInstance`. PHB-2024 стр. 26:
  «минимальный урон». Атака слабого actor'а (STR=6, 1d4-2, roll=1)
  больше не падает с ValueError. Тест
  `test_negative_damage_modifier_clamped_to_zero`.

* **VS-AI001** — параметр `take_monster_turn(... hostile_factions=...)`
  заменён на работающий `is_hostile: Callable[[CreatureId], bool]`.
  Helper `is_hostile_from_factions(actor_id, factions)` строит
  предикат поверх Encounter.factions: NEUTRAL и same-faction → не
  враги. Все callsites обновлены. Тесты
  `test_is_hostile_from_factions_skips_neutral_and_self` и
  `test_is_hostile_from_factions_same_faction_friendly`.

* **VS-G001** — Hard guard в `Encounter`: `MAX_ROUNDS = 100`. При
  превышении лимита бой принудительно завершается с `winners=None`
  и `_log.warning`. Защищает от багов AI / handler'ов
  (например, оба AI бесконечно Dodge'ят). Тест
  `test_round_limit_forces_encounter_end` (102 ходов без действий
  → EncounterEnded с winners=None).

**Итоговые цифры:**

* pytest:   **678 passed** (+4 за тесты фиксов)
* ruff:     All checks passed
* mypy:     Success: no issues found in 87 source files
* coverage: 96.24%

**Что осталось как technical debt:**

* UNARMED-STRIKE правило «1 + STR mod» добавим, когда damage-формат
  будет поддерживать fixed-bonus-без-dice (например, `"+1"` или
  numeric-only DiceExpr).
* MAX_ROUNDS=100 — эмпирическая константа; пост-MVP можно сделать
  настраиваемой через параметр конструктора (`max_rounds=...`).

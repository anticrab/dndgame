# R1 — Прогрессия и level-up в бою (дизайн)

**Дата:** 2026-05-25
**Этап:** R1 (первый срез этапа R «Уровни и опыт»; R2 — навыки/владения + остаток PHB-фич)
**Статус:** дизайн одобрен, спек на ревью
**Опорный документ:** `docs/PROGRESSION.md` (быстрая XP-кривая, level-up в середине боя, фикс. подкласс)

## 1. Цель

Дать игровому персонажу **уровни и опыт** с кульминацией — **level-up в середине
боя** (главная фишка коротких партий: получить +HP на грани смерти). Срез R1
строит ядро прогрессии (level/xp/класс), data-driven таблицы классов
Воин/Плут L1–3, быструю XP-кривую, начисление XP по убийству, применение
level-up (HP/prof/slots/фичи) и TUI-визард level-up. Плюс полный по PHB набор
фич L1–3, который **ложится на уже готовые системы**: Improved Critical,
Sneak Attack, Second Wind, Action Surge. Остальные фичи (Expertise, Fighting
Style, Cunning Action, Fast Hands, Thieves' Cant) и подсистема навыков/владений —
этап R2.

## 2. Принципы (project-wide)

- **Расширяемость через данные/реестры, не switch.** Классы — данные (YAML) +
  `ClassRepository`; фичи — `FeatureRegistry` (feature_id → хендлер), как
  `SpellEffectRegistry`/`AreaShapeRegistry`. Новый класс/фича = данные + хендлер,
  без правки движка.
- **Без Character/Monster split.** `level`/`xp`/`character_class` — опциональные
  поля `Creature` с дефолтами для монстров (прецедент — `uses_death_saves`).
- **Отдых заложен архитектурно правильно.** Полноценная абстракция
  `RestKind`/`RechargeOn`/`RestService`; в R1 единственный триггер — «отдых
  между боями» (SHORT на старте encounter). Будущие short/long rest как действия
  вне боя подключатся к той же службе без переделок — никакого throwaway-кода.
- **domain не зависит от внешних слоёв** (guard-тест `tests/unit/test_layering.py`).
- **Перепроверять ошибки/регрессии** на каждом шаге (pytest -q + mypy strict +
  ruff), не доверять зелёному набору вслепую: старые тесты могли «протухнуть»
  при смене механик (напр. крит-проверка в attack.py).

## 3. Domain — поля Creature и VO

### 3.1 Новые поля `Creature`

```python
level: int = 1
xp: int = 0
character_class: str | None = None        # id класса ("fighter"/"rogue"); None у монстров
challenge_rating: float = 0.0             # для XP-награды; грузится из monsters.yaml
features: tuple[FeatureId, ...] = ()       # обретённые фичи (inspect + повторное применение)
crit_range_min: int = 20                  # порог крита d20; Improved Critical ставит 19
resource_uses: dict[str, int] = field(default_factory=dict)
                                          # счётчики «N раз за отдых» (second_wind, action_surge)
```

* `proficiency_bonus` уже существует — level-up его поднимает по таблице.
* `FeatureId` уже объявлен в `domain/values/ids.py`.
* Валидация в `__post_init__`/`create`: `level >= 1`, `xp >= 0`.

### 3.2 Новый VO `domain/values/rest.py`

```python
class RestKind(StrEnum):
    SHORT = "short"
    LONG = "long"

class RechargeOn(StrEnum):
    TURN = "turn"
    ENCOUNTER = "encounter"
    SHORT_REST = "short_rest"
    LONG_REST = "long_rest"
```

Порядок «силы» отдыха: `TURN < ENCOUNTER < SHORT_REST < LONG_REST` (LONG
восстанавливает всё, что и SHORT, и больше). Утилита сравнения — в этом же
модуле (например, кортеж-ранг). Это «словарь», на который опираются и фичи
(`recharge_on`), и `RestService`.

## 4. Данные классов — `ClassProgression` + репозиторий

### 4.1 Domain VO `domain/values/class_progression.py`

```python
@dataclass(frozen=True, slots=True)
class ClassLevel:
    proficiency_bonus: int
    features: tuple[FeatureId, ...] = ()
    spell_slots: dict[int, int] | None = None   # None для не-кастеров (Воин/Плут)

@dataclass(frozen=True, slots=True)
class ClassProgression:
    id: str
    name: str
    hit_die: str                                # сериализованный DiceExpr, "1d10"
    levels: dict[int, ClassLevel]               # 1..N
```

### 4.2 Контент `data/content/classes.yaml`

```yaml
- id: fighter
  name: "Воин"
  hit_die: "1d10"
  levels:
    1: { proficiency_bonus: 2, features: [second_wind] }
    2: { proficiency_bonus: 2, features: [action_surge] }
    3: { proficiency_bonus: 2, features: [improved_critical] }   # подкласс Чемпион (фикс)
- id: rogue
  name: "Плут"
  hit_die: "1d8"
  levels:
    1: { proficiency_bonus: 2, features: [sneak_attack] }
    2: { proficiency_bonus: 2, features: [] }     # cunning_action → R2
    3: { proficiency_bonus: 2, features: [] }     # thief: fast_hands → R2
```

В R1 таблицы содержат **только R1-фичи**; R2 дополнит уровни/фичи — без
«мёртвых» feature_id, на которые нет хендлера.

### 4.3 Порт + адаптер

* `ClassRepository` (Protocol, `application/ports/class_repository.py`):
  `load(class_id) -> ClassProgression`, `contains(class_id) -> bool`,
  `list_ids() -> tuple[str, ...]`.
* `YamlClassRepository` (`infrastructure/content/yaml_class_repository.py`) —
  как `YamlSpellRepository`.

## 5. XP-кривая — стратегия

`application/engine/progression/xp_curve.py`:

```python
class XpCurve(Protocol):
    def threshold(self, level: int) -> int: ...      # суммарный XP для входа на level
    def level_for_xp(self, xp: int) -> int: ...       # макс. достижимый уровень при xp

class FastXpCurve(XpCurve): ...        # 1→2:100, 2→3:250, 3→4:500, 4→5:900 (суммарно)
class StandardXpCurve(XpCurve): ...    # 300/900/2700/... (книга)
class MilestoneXpCurve(XpCurve): ...   # level_for_xp всегда возвращает текущий (рост по событиям)
```

Какая кривая используется — поле сценария `xp_curve: fast | standard | milestone`
(резолвится фабрикой в composition root). Дефолт — `fast`.

## 6. Награда XP + событие level-up — **по убийству**

PROGRESSION.md §4 делает level-up в середине боя главной фишкой → XP начисляем
**на `CreatureDied` монстра**, не только в конце боя:

* `XpAwardService` (`application/engine/progression/xp_award.py`) подписан на
  `CreatureDied`: если погиб монстр (фракция ≠ PARTY), начисляет
  `int(challenge_rating * 100)` XP всем живым PC (PARTY). После начисления
  проверяет `xp_curve.level_for_xp(pc.xp) > pc.level` → публикует
  `LevelUpReady(actor_id, from_level, to_level)`.
* Бонусы за исследование/тактику (`xp_bonus` сценария) добавляются на
  `EncounterEnded` тем же сервисом (в R1 — минимально, поля сценария уже
  существуют по PROGRESSION.md §2.3; если их нет — закладываем хук, контент
  опционален).
* Новое событие `LevelUpReady(EngineEvent)`: `actor_id`, `from_level`, `to_level`.

`challenge_rating` грузится из `monsters.yaml` (новое поле `cr`, дефолт 0).

## 7. Применение level-up — `LevelUpService`

`application/engine/progression/level_up.py`:

`LevelUpService(class_repository, feature_registry)`:
`apply(creature, to_level, ctx) -> LevelUpResult` — для каждого уровня от
`creature.level+1` до `to_level`:

* **HP**: фикс. среднее кости hit_die (⌈(sides+1)/2⌉) + mod ТЕЛ, прибавляется к
  максимуму и текущему HP (детерминированно, без броска — честно по PHB
  «fixed value» и удобно для тестов/драмы).
* **proficiency_bonus**: из `ClassLevel.proficiency_bonus`.
* **spell_slots**: из `ClassLevel.spell_slots` (для Воина/Плута None — пропуск).
* **features**: `creature.features += level.features`; для каждой новой —
  `feature_registry.get(fid).on_gain(creature, ctx)`.

Идемпотентность: применяется ровно один раз на (class, level) — `creature.level`
двигается вперёд; повторный вызов с тем же `to_level` — no-op.

`LevelUpResult` — что показать в UI (прирост HP, новые фичи, новый prof).

Событие `LeveledUp(actor_id, new_level, hp_gained, features_gained)` — для лога.

## 8. Отдых — `RestService`

`application/engine/progression/rest.py`:

`RestService.apply(creature, kind: RestKind)`:
* сбрасывает все ресурсы `creature.resource_uses[...]` к максимуму, чьё
  `recharge_on ≤ kind` (по рангу из §3.2);
* `SHORT`: восстанавливает short-rest-фичи (Second Wind, Action Surge);
  hit-dice-лечение (если будет) — хук на будущее;
* `LONG`: всё SHORT + полный HP.

Максимумы ресурсов и их `recharge_on` объявляет хендлер фичи (см. §9) —
`RestService` не знает про конкретные фичи, только про `recharge_on` ресурса.

**R1-триггер (единственный):** на старте encounter (`Encounter.start` или первый
`TurnStarted` PC) движок вызывает `RestService.apply(pc, RestKind.SHORT)` для
каждого PC — это «отдых между боями». Будущие short/long rest-действия вне боя
зовут ту же `RestService.apply`.

## 9. Каркас фич — `FeatureRegistry`

`application/engine/features/`:

```python
class FeatureHandler(Protocol):
    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None: ...
    # пассив: повесить модификатор / выставить деривацию (crit_range_min);
    # активная: проинициализировать resource_uses; ability выдаётся через
    # creature.ability_ids (или отдельный реестр способностей).
```

`FeatureRegistry` (feature_id → handler) + `default_feature_registry()`.
Реестр ресурсов: хендлер активной фичи объявляет (resource_key, max_uses,
recharge_on), чтобы `RestService` знал что сбрасывать. Реестр ресурсов —
лёгкая мапа `resource_key → (max, recharge_on)`, наполняется хендлерами фич.

## 10. Фичи R1 (полные по PHB из переиспользующего набора)

* **Improved Critical** (Воин/Чемпион L3) — пассив: `on_gain` ставит
  `creature.crit_range_min = 19`. `AttackAction` крит-проверку меняет с «нат 20»
  на `roll.d20_raw >= attacker.crit_range_min` (и нат-1 промах остаётся).
  *Перепроверить:* старые тесты крита (нат-20) не должны протухнуть — порог по
  умолчанию 20, поведение без фичи не меняется.
* **Sneak Attack** (Плут L1) — `+Nd6` урона, `N = ceil(level/2)`, **раз за ход**,
  если у атакующего преимущество на бросок ИЛИ союзник цели рядом с целью
  (в 5 фт), оружием finesse/дальнобойным. Реализация: хук в `AttackAction`
  после подтверждённого попадания — `SneakAttackSpec` (условие) + флаг
  `sneak_used_this_turn` (сбрасывается на старте хода владельца, как combat_stances).
  Доп. урон того же типа, что оружие; отдельный `DamageDealt`-вклад или
  включается в общий — уточнить в плане (предпочтительно отдельный бросок/строка).
* **Second Wind** (Воин L1) — bonus action: лечение `1d10 + level`;
  ресурс `second_wind` (max=1, `recharge_on: short_rest`); новый `Ability`
  (`second_wind`, hotkey по action-bar) + `Action` (`SecondWindAction`),
  тратит bonus action и use.
* **Action Surge** (Воин L2) — действие: даёт **дополнительное действие** в
  текущем ходу (refresh флага потраченного action в `TurnContext`); ресурс
  `action_surge` (max=1, `recharge_on: short_rest`); `Ability` + `Action`.
  *Перепроверить:* экономика действий (`TurnContext.can_spend/spend`) корректно
  переживает refresh.

## 11. TUI — level-up в середине боя

`LevelUpReady` копится в очереди BattleScreen. В безопасной точке (после резолва
текущего действия, перед запросом следующего intent) BattleScreen открывает
модальный `LevelUpScreen` (по образцу `EndScreen`/`InventoryScreen`):

* **«Сейчас!»** — `LevelUpService.apply(...)`, показать `LevelUpResult` (прирост
  HP, новые фичи, новый prof); бой на паузе (модалка перехватывает ввод).
* **«После боя»** — пометить отложенным (`pending_level_up`), применить на
  `EncounterEnded`.
* **«Подробнее»** — показать, что даёт уровень (фичи/HP), вернуться к выбору.

Бой — FSM; level-up — модальный саб-стейт, не ломающий ход-цикл. Драматический
эффект: +HP при 1/18 может «воскресить» PC посреди боя.

## 12. Composition root

`build_*_dependencies`/`TuiApp` получают `ClassRepository`, `XpCurve` (из
сценария), `FeatureRegistry`; `XpAwardService`/`RestService` подписываются/зовутся
в `Encounter` или `GameRunner` (по месту, как `XpAwardService` на `CreatureDied`).

## 13. Тесты

* **XpCurve**: пороги fast/standard; `level_for_xp` обратное; milestone = no-op.
* **XpAwardService**: убийство монстра CR×100 → PC.xp растёт; пересечение порога →
  `LevelUpReady`; не-PARTY получатель не качается; бонусы на EncounterEnded.
* **LevelUpService**: HP (фикс. среднее + ТЕЛ), prof, slots, features; идемпотентно;
  `LeveledUp` событие.
* **RestService**: SHORT сбрасывает short-rest-ресурсы; LONG + полный HP; ресурсы
  с `recharge_on > kind` не трогаются; рекордер ранга RechargeOn.
* **Recharge на старте боя**: PC начинает encounter с восстановленными
  second_wind/action_surge.
* **Фичи**: Improved Crit меняет порог крита в `AttackAction` (d20=19 → крит при
  фиче, обычный при отсутствии); Sneak Attack +Nd6 при преимуществе/союзнике и
  **не дважды** за ход; Second Wind лечит и тратит use; Action Surge даёт второе
  действие в ходу.
* **ClassRepository**: грузит fighter/rogue; hit_die/levels/features корректны.
* **TUI pilot**: `LevelUpReady` → визард → «Сейчас» применяет (HP вырос, фича
  обретена); «После боя» откладывает (применяется на EncounterEnded).
* **Регрессия**: весь набор зелёный; mypy strict; ruff; layering-guard.
* **Перепроверка протухания**: тесты крита (нат-20) и экономики действий после
  правок `attack.py`/`TurnContext` остаются валидны по смыслу.

## 14. Инварианты

1. `level >= 1`, `xp >= 0`; монстры по умолчанию level=1, character_class=None.
2. XP начисляется только PARTY за смерть не-PARTY; level не «прыгает» через
   уровни без применения (LevelUpService двигает по одному).
3. `crit_range_min` по умолчанию 20 — поведение крита без Improved Critical не
   меняется (нет регрессии).
4. Sneak Attack — максимум один раз за ход владельца.
5. Ресурс восстанавливается ровно по своему `recharge_on`; R1 зовёт SHORT между
   боями — true short/long rest подключатся к той же `RestService` позже.
6. `domain` не импортирует внешние слои.
7. Level-up идемпотентен; «После боя» применяет ровно один раз на EncounterEnded.

## 15. Декомпозиция (уточнится в плане)

R1-1 поля Creature + `rest.py` VO · R1-2 `ClassProgression` + classes.yaml + репо ·
R1-3 XpCurve · R1-4 XpAwardService (kill→LevelUpReady) + cr монстрам ·
R1-5 LevelUpService + LeveledUp · R1-6 RestService + триггер SHORT на старте боя ·
R1-7 FeatureRegistry + реестр ресурсов · R1-8 Improved Critical (+ правка крита
в attack.py) · R1-9 Sneak Attack · R1-10 Second Wind · R1-11 Action Surge ·
R1-12 TUI LevelUpScreen + wiring · R1-13 контент (PC-классы в сценарии, cr
монстрам) + docs (PROGRESSION/ROADMAP/ABILITIES) + независимый аудит.

## 16. Отложено в R2

Подсистема навыков/владений (именованные навыки, proficiency/expertise, вывод
`skill_mod`); Expertise; Fighting Style (выбор + AC/урон); Cunning Action;
Fast Hands; Thieves' Cant; уровни Плута L2–L3 фич. Также пост-MVP: ASI (L4),
полноценный выбор подкласса, true short/long rest как внебоевые действия,
inspiration.

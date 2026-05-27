# T4 — подклассы L3 + боевые стили + Cunning Action: дизайн

> Финал серии T. Доводит классы Воин/Плут/Волшебник до полного L1–3: боевой
> стиль (Воин L1), Cunning Action (Плут L2), подкласс на L3 (Чемпион / Вор /
> Школа Воплощения). Принцип: данные/реестры, не switch; domain не зависит от
> application; гасить техдолг.

## 1. Решения (зафиксированы с пользователем)

- **Выбор — данными шаблона**, не интерактивно: `Creature.fighting_style` /
  `Creature.subclass` приходят из YAML; интерактивный выбор на level-up
  **отложен** (нет создания персонажа). Зафиксировано в памяти
  `project_interactive_choice_deferred` — при появлении создания персонажа
  вернуться и заменить шаблон+автовыбор на UI-выбор. Места помечаем в коде
  комментарием «T4: выбор данными шаблона (интерактив отложен)».
- **Глубина — «реальные где дёшево»**: реализуем механики, ложащиеся на готовый
  фундамент; то, что требует отсутствующих подсистем (навыки, лазание, reroll
  кости), — лёгкая версия/флаг с описанием.
- Режим исполнения: inline. Декомпозиция: T4-a (стиль) · T4-b (подклассы) ·
  T4-c (Cunning Action + добивка + доки).

## 2. Архитектура

### 2.1 Выбор данными (Creature + шаблон)

- `Creature`: новые поля `fighting_style: FeatureId | None = None`,
  `subclass: FeatureId | None = None` (что выбрано). Заполняются builder'ом из
  `MonsterTemplate` (`fighting_style: str`, `subclass: str`).
- `classes.yaml` объявляет на нужном уровне **мета-фичу выбора** в `features`:
  Воин L1 += `fighting_style`, L3 `improved_critical` → `subclass`
  (Чемпион даёт Improved Critical); Плут L2 += `cunning_action`, L3 += `subclass`;
  Волшебник L3 += `subclass`.
- Мета-фича-хендлер (`FightingStyleHandler`, `SubclassHandler`) на `on_gain`
  читает `creature.fighting_style`/`creature.subclass`, и если задано —
  применяет соответствующую конкретную фичу (через тот же `FeatureRegistry`),
  записывает её в `creature.features`. Если не задано — **автовыбор дефолта**
  (Воин→`style_defense`, Плут→`subclass_thief`, Волшебник→`subclass_evoker`,
  Воин-подкласс→`subclass_champion`). Так level-up детерминирован и без UI.

### 2.2 Боевые стили (Воин L1)

Числовые/пассивные бонусы. Чтобы не плодить switch в `attack.py`, выносим в
маленький модуль `application/engine/features/fighting_styles.py` с реестром
``STYLE_EFFECTS: dict[FeatureId, FightingStyleEffect]`` (данные):

| Стиль | id | Эффект | Реализация |
|-------|----|--------|------------|
| Defense | `style_defense` | +1 КД | `on_gain`: `creature.armor_class += 1` (persist) |
| Dueling | `style_dueling` | +2 урон одноручным melee | helper `damage_bonus(creature, kind)` → attack.py |
| Archery | `style_archery` | +2 к атаке ranged | helper `attack_bonus(creature, kind)` → attack.py |
| Great Weapon Fighting | `style_gwf` | переброс 1–2 урона | **отложено** (нет reroll-хука); объявлено как флаг |

`attack.py` зовёт `fighting_style_attack_bonus(actor, params.kind)` и
`fighting_style_damage_bonus(actor, params.kind)` (чистые функции, читают
`actor.fighting_style`) и прибавляет к `attack_bonus`/`damage`-числу. Это
изолировано в одном helper-модуле — не switch по классам в attack.py.

> Dueling «одноручное» приближаем как «melee» (handedness в модели оружия пока
> грубая) — отмечаем упрощение.

### 2.3 Подклассы L3

| Класс | Подкласс | id | Фича | Реализация |
|-------|----------|----|------|------------|
| Воин | Чемпион | `subclass_champion` | Improved Critical (крит 19–20) | переиспользует `ImprovedCriticalHandler` (R1) |
| Плут | Вор (Thief) | `subclass_thief` | Fast Hands | **лёгкая версия**: бонусным действием Interact/Pickup (грант ability с bonus-economy); Second-Story Work — описание (нет лазания) |
| Волшебник | Воплощение | `subclass_evoker` | Sculpt Spells | союзники кастера авто-исключаются из урона его AoE |

- **Sculpt Spells** (реализуемо): в `CastSpellAction` AREA-резолвинге — если у
  кастера фича `subclass_evoker`, из списка целей AoE убираются существа той же
  фракции, что кастер (`ctx.factions`). PHB точнее (выбираешь Cha-мод целей),
  но «все союзники в зоне невредимы» — близкое и понятное упрощение.
- **Fast Hands** (лёгкая): грант ability «использовать предмет/взаимодействие
  бонусным действием» (Interact уже есть; добавляем bonus-economy вариант). Без
  Sleight of Hand (нет навыков). Документируем границу.

### 2.4 Cunning Action (Плут L2)

`CunningActionHandler.on_gain` грантит абилки Dash/Disengage/Hide с экономикой
**bonus action** (Dash/Disengage есть как Action; добавляем bonus-варианты-
абилки, маршрутизируемые в существующие `DashAction`/`DisengageAction` с
bonus-стоимостью; Hide — лёгкая версия/флаг, т.к. полноценный стелс вне scope).
Через меню способностей (S) они появятся автоматически.

> Минимально и честно: Dash/Disengage бонусным действием — реальная механика
> (готовые действия), Hide — заглушка с описанием.

### 2.5 Wiring

- `default_feature_registry` += `FightingStyleHandler`, `SubclassHandler`,
  `CunningActionHandler`, и конкретные `style_*`/`subclass_*` фичи.
- `builder.py`: `creature.fighting_style`/`subclass` из шаблона.
- `MonsterTemplate`: поля `fighting_style: str | None`, `subclass: str | None`.
- `warrior_veteran`/демо-воин: `fighting_style: defense`; mage: `subclass`
  выставится автовыбором на L3 (в демо маг L1 — не дойдёт, но данные готовы).

## 3. Расширяемость

- Новый стиль = строка в `STYLE_EFFECTS` + (если нужен боевой бонус) ветка в
  helper. Новый подкласс/фича = хендлер + регистрация + строка в `classes.yaml`.
- attack.py/cast_spell агностичны к классам — спрашивают helper/фичу.

## 4. Тестирование

- Юнит: `FightingStyleHandler` (defense → +1 AC; автодефолт); helper
  attack/damage bonus (archery +2 ranged, dueling +2 melee). `SubclassHandler`
  (champion → crit_range_min 19; evoker флаг). `CunningActionHandler` (гранты
  bonus-абилок). Sculpt Spells (союзник кастера не получает урон от его Fireball).
- Интеграция: воин L1 defense → AC+1; level-up воина до L3 → champion crit 19.
- e2e: Эвокатор кастует Fireball — враги в зоне получают урон, союзник нет.
- Регрессия: fighter L3 теперь даёт improved_critical через subclass (не
  напрямую) — перепроверить демо-тесты level-up (Action Surge L2 не затронут).
- Полный `pytest -q` + mypy + ruff + guard слоёв.

## 5. Инварианты

1. domain не импортирует application; стили/подклассы — фичи (application) +
   данные (classes.yaml) + поля выбора (domain Creature).
2. level-up детерминирован без UI (автовыбор дефолта, если шаблон не задал).
3. Backward-compat: новые поля Creature/Template — с дефолтами; существующие
   существа без стиля/подкласса не меняются (кроме fighter L3: improved_critical
   теперь через subclass_champion — итог тот же crit 19–20).
4. Sculpt Spells исключает только союзников кастера и только из его AoE-урона.

## 6. Декомпозиция (план)

- **T4-a** поля выбора (Creature/Template/builder) + `FightingStyleHandler` +
  `fighting_styles.py` (defense/archery/dueling) + проводка в attack.py + контент.
- **T4-b** `SubclassHandler` + Champion (перенос improved_critical) + Evoker
  Sculpt Spells (cast_spell) + Thief Fast Hands (лёгкая) + classes.yaml L3.
- **T4-c** `CunningActionHandler` (bonus Dash/Disengage/Hide) + добивка
  classes.yaml + e2e + доки (PROGRESSION/ABILITIES/SPELLS/ROADMAP) + аудит-смок.

## 7. Отложено (пост-T4)

- Интерактивный выбор стиля/подкласса на level-up (создание персонажа).
- Great Weapon Fighting (reroll-хук урона), полноценный Hide/стелс, навыки
  (Sleight of Hand для Fast Hands, лазание для Second-Story Work).
- Точный Sculpt Spells (выбор N=Cha целей, половина урона при провале).
- Уровни 4+ (ASI/feat), прочие подклассы.

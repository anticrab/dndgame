# T3 — боевые условия: дизайн

> Этап серии T (волшебник/боёвка). Закрывает отложенные пункты аудита
> 2026-05-27: cross-creature преимущество, Dodge-спасброски, авто-провалы
> спасбросков, авто-крит в упор. Плюс чинит латентный баг: `provides_modifiers`
> состояний нигде не применялись. Принцип: данные/реестры, не switch в attack.py;
> domain не зависит от application; гасим техдолг сразу.

## 1. Проблема

Состояния влияют на броски по правилам PHB-2024, но движок их почти не
учитывает в бою:

1. **`provides_modifiers` осиротел.** Условия объявляют модификаторы
   (Poisoned/Frightened → помеха на атаки; Prone → помеха на свои атаки;
   Paralyzed/Unconscious → помеха на свои спасброски), но `ModifierApplier.
   collect` читает только из `ModifierBag` (баффы заклинаний). Эти self-помехи
   **никогда не применяются**.
2. **Нет cross-creature.** Атака по цели под Paralyzed/Unconscious/Stunned/
   Restrained должна идти с преимуществом; по Prone — преимущество в упор,
   помеха на расстоянии. Сейчас этого нет.
3. **Авто-крит** только по `is_at_zero_hp` (Q-4). По Paralyzed/Unconscious в
   упор крит тоже обязателен (PHB-2024 стр. 367), даже при полном HP.
4. **Авто-провал спасбросков** Силы/Ловкости под Paralyzed/Unconscious/Stunned
   не реализован (приближался помехой, фактически нет).
5. **Dodge** даёт атакующим помеху (есть), но не даёт dodger'у преимущество на
   спасброски Ловкости (PHB-2024 стр. 22).

## 2. Решения (зафиксированы с пользователем)

- **Боевые данные — поля на состоянии** (декларативно, рядом с `implies`/
  `provides_modifiers`), не центральная таблица: один источник правды.
- **`provides_modifiers` чиним в T3** — проводим через
  `ConditionService.collect_modifiers` на момент броска.
- Режим исполнения: inline.

## 3. Архитектура

### 3.1 Декларативные боевые поля состояния (domain)

`Condition`-протокол (`domain/conditions/base.py`) расширяется атрибутами с
дефолтами (существующие состояния не ломаются — дефолты «ничего не меняет»):

```python
class Condition(Protocol):
    id: ConditionId
    implies: frozenset[ConditionId]
    # T3 — боевые взаимодействия (декларативно):
    grants_advantage_to_attackers: bool        # атаки по носителю — с advantage
    melee_advantage_ranged_disadvantage: bool  # Prone: adv в упор / disadv в дали
    auto_fail_saves: frozenset[Ability]        # авто-провал этих спасбросков
    def provides_modifiers(self, owner_id): ...
```

Значения по builtin-состояниям (`domain/conditions/builtin.py`):

| Состояние    | grants_adv | melee_adv/ranged_disadv | auto_fail_saves |
|--------------|:----------:|:-----------------------:|-----------------|
| Paralyzed    | да         | —                       | {STR, DEX}      |
| Unconscious  | да         | —                       | {STR, DEX}      |
| Stunned      | да         | —                       | {STR, DEX}      |
| Restrained   | да         | —                       | —               |
| Prone        | —          | да                      | —               |
| прочие       | —          | —                       | —               |

> Restrained пока не накладывается контентом, но данные объявляем (дёшево,
> готовит почву). Petrified/Blinded — вне scope T3 (нет состояний в движке).

Поскольку builtin-условия — frozen dataclass'ы, добавляем поля с дефолтами
прямо в нужные классы; остальные наследуют дефолты протокола (через значения
полей по умолчанию в каждом dataclass — Python Protocol дефолтов не даёт,
поэтому дефолт прописываем в каждом dataclass-поле; см. план).

### 3.2 `ConditionService` — мост «данные → бросок» (application)

Три новых метода (чистые чтения, без plumbing apply/remove):

```python
def collect_modifiers(self, creature, target_kind) -> list[Modifier]:
    """Self-модификаторы от активных состояний носителя для данного класса
    броска. Активирует provides_modifiers (T3-фикс)."""
    out = []
    for cid in creature.conditions:
        for m in self._registry.get(cid).provides_modifiers(creature.id):
            if m.target_kind is target_kind:
                out.append(m)
    return out

def incoming_attack_adjustment(
    self, target, *, distance_ft, attack_kind,
) -> tuple[bool, bool]:
    """(advantage, disadvantage) для атакующего по target — из боевых данных
    состояний цели. Prone: melee≤5 → adv, RANGED или melee>5 → disadv."""

def auto_fails_save(self, creature, ability) -> bool:
    """True, если активное состояние носителя авто-проваливает этот спасбросок."""
```

`incoming_attack_adjustment` логика: для каждого состояния цели —
`grants_advantage_to_attackers` → advantage=True;
`melee_advantage_ranged_disadvantage` (Prone) → если `attack_kind is MELEE and
distance_ft<=5` advantage=True, иначе disadvantage=True. Возвращает агрегат
(adv, disadv); правило «adv+disadv=обычный» применит `to_roll_adjustments`/
RollContext позже.

### 3.3 Интеграция в `attack.py`

- **Self-модификаторы:** `atk_mods = bag.collect(actor, ATTACK_ROLL) +
  condition_service.collect_modifiers(actor, ATTACK_ROLL)` → один
  `to_roll_adjustments`. damage/ac не трогаем (condition-модификаторов на них
  нет) — меняем только сбор ATTACK_ROLL.
- **Cross-creature:** `tgt_adv, tgt_disadv = condition_service.
  incoming_attack_adjustment(target, distance_ft=distance_ft, attack_kind=
  params.kind)`. В `RollContext`: `advantage=atk_adj.advantage or help_bonus or
  tgt_adv`, `disadvantage=atk_adj.disadvantage or long_range_penalty or
  dodge_penalty or tgt_disadv`. Книжное adv+disadv=обычный — в DiceRoller (есть).
- **Авто-крит:** расширить условие:
  ```python
  melee_point_blank = params.kind is AttackKind.MELEE and distance_ft <= 5
  helpless = target.is_at_zero_hp or target.has_condition(PARALYZED) \
             or target.has_condition(UNCONSCIOUS)
  if hit and melee_point_blank and helpless:
      is_crit = True
  ```

### 3.4 Интеграция в `saving_throw.py`

- **Авто-провал:** `roll_saving_throw_raw` принимает `condition_service` (или
  отдельный флаг) — в начале: если `condition_service.auto_fails_save(actor,
  ability)` → вернуть False без броска. Чтобы не тащить ConditionService в
  каждую сигнатуру, передаём `condition_service` опционально; `roll_saving_throw`
  (с ctx) берёт `ctx.condition_service`; raw-вызовы (OngoingEffectTracker)
  тоже получают его (трекер уже на application-слое — добавим в конструктор).
- **Dodge DEX-save advantage:** spell/save-хендлеры и tracker не знают про
  стойку — добавляем в `roll_saving_throw[_raw]` проверку:
  `if ability is Ability.DEX and "dodging" in actor.combat_stances and not
  incapacitated(actor): advantage=True`. «incapacitated» — через
  `auto_fails_save`/наличие INCAPACITATED. (Dodge и так подавляется
  инкапаситацией — переиспользуем.) Реализуем как ещё один источник advantage
  в сборке adjustments спасброска.

> Замечание: авто-провал имеет приоритет над Dodge-advantage (Paralyzed →
> авто-провал DEX, даже если зачем-то dodging). Порядок проверок: сначала
> auto-fail → return False.

### 3.5 Wiring

- `ConditionService` уже в `ctx` (TurnContext) и в `EncounterDependencies`.
  `attack.py` берёт `ctx.condition_service`. `saving_throw` (ctx-вариант) — из
  ctx. `OngoingEffectTracker` (raw) — добавить `condition_service` в конструктор
  и прокинуть в composition (`cli/app.py`).

## 4. Расширяемость

- Новое состояние с боевым эффектом = поля в его dataclass (data, не switch).
- attack.py/saving_throw агностичны к конкретным состояниям — спрашивают
  `ConditionService`. Новое правило взаимодействия = новый метод сервиса +
  поле состояния (open/closed).

## 5. Тестирование

- **Юнит `ConditionService`:** `collect_modifiers` (Poisoned→ATTACK_ROLL
  disadvantage); `incoming_attack_adjustment` (Paralyzed→adv; Prone melee≤5→adv,
  Prone ranged→disadv); `auto_fails_save` (Paralyzed DEX→True, CON→False).
- **Юнит/интеграция `attack.py`:** атака по Paralyzed-цели — advantage в
  RollContext; атака Poisoned-атакующего — disadvantage; авто-крит по
  Paralyzed в упор; Prone-цель: melee adv vs ranged disadv.
- **Юнит `saving_throw`:** Paralyzed → DEX-спасбросок авто-провал (без броска);
  Dodge → DEX-спасбросок с advantage; авто-провал приоритетнее Dodge.
- **e2e:** маг Hold Person'ит воина-NPC → союзник бьёт его с преимуществом и
  авто-критом в упор; Paralyzed проваливает DEX-спасбросок против Fireball.
- Регрессия: полный `pytest -q` + `mypy strict` + `ruff` + guard слоёв. Особое
  внимание — старые тесты, где Poisoned/Frightened/Prone теперь РЕАЛЬНО дают
  помеху (могли молча проходить на «нет эффекта»); перепроверить ожидания.

## 6. Инварианты

1. domain не импортирует application (guard зелёный); боевые поля — чистые
   данные в domain.
2. Авто-провал спасброска приоритетнее любых преимуществ (return False первым).
3. `incoming_attack_adjustment` для Prone зависит от `attack_kind`+`distance`.
4. Backward-compat: новые поля состояний имеют дефолты «нет эффекта»; состояния
   без боевых данных ведут себя как раньше + (новое) их `provides_modifiers`
   теперь применяются — это намеренное исправление, тесты обновляются.
5. adv+disadv=обычный бросок — единое место (RollContext/DiceRoller), не дублируем.

## 7. Декомпозиция (план)

- **T3-1** `ConditionService.collect_modifiers` + проводка self-модификаторов в
  `attack.py` (ATTACK_ROLL) и `saving_throw` (SAVING_THROW); фикс орфана.
- **T3-2** боевые поля состояний (domain) + `incoming_attack_adjustment` +
  cross-creature advantage/disadvantage в `attack.py` (Prone-сплит).
- **T3-3** авто-крит vs Paralyzed/Unconscious в упор (расширить условие).
- **T3-4** `auto_fails_save` + авто-провал STR/DEX в `saving_throw` + Dodge
  DEX-save advantage; прокидка `condition_service` в `OngoingEffectTracker`.
- **T3-5** e2e (Hold Person → advantage+авто-крит союзника; Paralyzed→провал
  DEX) + доки (CONDITIONS/MODIFIERS/ROADMAP).

## 8. Отложено (T4/далее)

- Petrified/Blinded/Restrained-контент (данные объявлены, накладывания нет).
- «Cover/невидимость» как источники adv/disadv цели.
- Reach-оружие (>5 фт melee) и его влияние на «в упор» для авто-крита —
  сейчас «в упор» = distance≤5.

# Ability Framework

> Этап L2. Spec: `docs/superpowers/specs/2026-05-23-l-inline-ux-and-abilities-design.md`.
> Plan: `docs/superpowers/plans/2026-05-23-l-inline-ux-and-abilities.md`.

## Концепция

`Ability` — runtime-описание игрового умения, ориентированное на UI:
hotkey, иконка, требования к выбору (target / path) и фабрика
`PlayerIntent`. Это отдельная сущность от `Action`-классов в
`application/engine/actions/`: `Action` выполняет игровую логику и
её результат — событие в EventBus; `Ability` отвечает за то, как
игрок инициирует это действие из TUI и как клавиша на клавиатуре
превращается в `PlayerIntent`.

Граница такая: BattleScreen берёт нажатую клавишу → ищет `Ability` в
keymap → вызывает её `intent_factory(...)` → кладёт `PlayerIntent` в
очередь → GameRunner транслирует его в соответствующий `Action`.

## Структура

```python
@dataclass(frozen=True)
class Ability:
    id: AbilityId              # NewType(str), напр. "weapon_attack"
    name: str                  # "Attack" — для action-bar и логов
    icon: str                  # 1 символ — для action-bar
    default_hotkey: str        # "a"
    economy_cost: ActionEconomyCost
    requires_target: bool      # True → mode TARGET (Tab-cycle)
    requires_path: bool        # True → mode MOVE (курсор по карте)
    requires_area: bool        # True → mode AREA (точка/направление AoE), T1
    intent_factory: Callable[..., PlayerIntent]
```

`requires_target` / `requires_path` / `requires_area` **взаимоисключающие** —
mode-state-machine BattleScreen'а держит ровно один режим за раз (TARGET /
MOVE / AREA); ability, требующий двух режимов сразу, нельзя выразить текущим
machine'ом, поэтому `__post_init__` поднимает `ValueError` (если истинно более
одного флага). `requires_area` (этап T1) ставится автоматически для
AoE-заклинаний (`TargetKind.AREA`) в `spell_ability()`.

## Default-набор (6 умений)

| id            | name      | hotkey | requires_target |
|---------------|-----------|--------|-----------------|
| weapon_attack | Attack    | a      | yes             |
| dodge         | Dodge     | d      | —               |
| dash          | Dash      | h      | —               |
| disengage     | Disengage | g      | —               |
| interact      | Interact  | i      | yes (object)    |
| break_object  | Break     | k      | yes (object)    |

`Move` — намеренно НЕ ability: это **движение** (MOVEMENT), а не
**действие** (ACTION), и обрабатывается отдельным hotkey'ем `m` с
собственным `MoveModeHandler`-ом.

`Help` / `Search` / заклинания — пока без `*Intent`-классов, поэтому
не зарегистрированы. Добавим параллельно с самими intent'ами, чтобы
не плодить ability с фабриками-«заглушками».

См. `register_default_abilities` в `application/abilities/defaults.py`.

## Переопределение хоткеев

Каждое существо несёт `Creature.keybindings: dict[str, AbilityId]` —
персональный override default-хоткеев. По умолчанию пуст, и keymap
строится из `Ability.default_hotkey`. Чтобы переназначить `z` на
атаку:

```python
creature.keybindings["z"] = AbilityId("weapon_attack")
```

`build_keymap(actor, registry)` (`interfaces/tui/screens/keymap.py`)
собирает финальный `{hotkey: Ability}`:

1. для каждого `aid` в `actor.ability_ids` → `keymap[ability.default_hotkey] = ability`;
2. для каждого `(key, aid)` в `actor.keybindings`:
   - снимаем старый `default_hotkey` этой ability (если он там есть),
     иначе одна и та же ability оказалась бы привязана к двум клавишам;
   - назначаем новый `key`.

В BattleScreen.on_key (NORMAL mode) override-хоткей идёт через keymap
и `_trigger_ability(...)`, а **default hotkey'и** остаются на откуп
Textual `BINDINGS` (`action_intent_attack` и пр.) — это сохраняет всё
текущее интеграционное покрытие без изменений и оставляет один путь
выполнения для типичного игрока.

## Расширение

Новое умение регистрируется в `AbilityRegistry` в composition root
(сейчас — внутри `TuiApp.__init__`, при отсутствии явного
`ability_registry`-аргумента):

```python
registry.register(Ability(
    id=AbilityId("fire_bolt"), name="Fire Bolt", icon="*",
    default_hotkey="f", economy_cost=ActionEconomyCost.ACTION,
    requires_target=True, requires_path=False,
    intent_factory=lambda target_id: CastSpellIntent(
        spell_id=SpellId("fire_bolt"), target_id=target_id,
    ),
))
```

Чтобы PC-волшебник видел `[f] Fire Bolt` в action-bar — добавляем
`AbilityId("fire_bolt")` в `Creature.ability_ids` при создании
существа. ActionBarWidget пересоберётся на ближайшем TurnStarted.

## ИНВАРИАНТЫ

* default hotkey'и зарегистрированных ability'ев не коллидируют
  (тест: `tests/unit/abilities/test_default_abilities.py::test_no_hotkey_collisions`);
* `actor.ability_ids` валидируются через registry — `build_keymap`
  вызывает `registry.get(aid)`, который бросает `KeyError` на
  неизвестный id (fail-fast);
* `requires_target ∧ requires_path` запрещены в `__post_init__`.

## Классовые фичи как ability (этап R1)

Активные классовые фичи выдаются ability'ями через тот же реестр:

* **Second Wind** (`w`, bonus action) — Воин L1, лечение 1d10 + уровень;
* **Action Surge** (`x`) — Воин L2, дополнительное действие в этом ходу.

Фичи обретаются при level-up: `FeatureRegistry` (open/closed, feature_id →
хендлер) при `on_gain` добавляет `ability_id` в `Creature.ability_ids` и
инициализирует ограниченный ресурс (`resource_uses`). Ресурсы восстанавливает
`RestService` по политике `recharge_on` (Second Wind / Action Surge — short rest;
в R1 «отдых между боями» на старте encounter). Пассивные фичи (Improved Critical,
Sneak Attack) ability не выдают — действуют в `AttackAction`. См.
`docs/PROGRESSION.md` §7a.

## Меню способностей (этап S)

Помимо хоткеев, все способности активного PC доступны через **меню** —
`AbilityMenuScreen` (`interfaces/tui/screens/ability_menu_screen.py`),
открывается клавишей **`Tab`** в NORMAL-режиме. Это снимает потолок «одна
способность = один хоткей» (важно для волшебника с многими заклинаниями).

* `↑`/`↓` — выбор, `Enter` — применить (через тот же `BattleScreen._trigger_ability`:
  target → TARGET-режим, иначе сразу intent), `Esc` — закрыть.
* `b` + клавиша — **перебиндить** выбранную способность на эту клавишу
  (`rebind_ability` в `keymap.py`; на сессию, в `Creature.keybindings`).
  Инвариант «одна клавиша = одна способность» (старые привязки снимаются),
  затем `BattleScreen._apply_keymap` пересобирает keymap, сохраняя заклинания 1–9.
* Доступность строки — по экономии действия (`ability_can_afford`); грейинг по
  ресурсу/слоту и персист биндов на диск (привязка к персонажу) — отложены
  (см. спек `docs/superpowers/specs/2026-05-27-s-ability-menu-design.md` §5).

Источник строк — `actor.ability_ids → AbilityRegistry` **плюс** заклинания.
Заклинания не лежат в `ability_ids` (они в `keymap` под хоткеями `1–9`), поэтому
`_open_ability_menu` отдельно добавляет в меню строки-`Ability` для каждого
заклинания из keymap (`is_spell_ability`). Так волшебник видит и кастует все
заклинания из одного списка; AoE-заклинание (`requires_area`) при выборе уводит
BattleScreen в режим **AREA** через тот же `_trigger_ability`. Новые способности
и заклинания появляются в меню без правок UI.

## См. также

* `docs/TUI.md` §6 — mode-state machine, ActionBarWidget;
* `docs/ACTIONS.md` — серверная сторона: что делает каждое `Action`;
* `docs/superpowers/specs/2026-05-23-l-inline-ux-and-abilities-design.md` §4.3 — исходный дизайн.

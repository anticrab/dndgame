# UI Mockup — Widgets & micro-elements

ASCII-мокапы переиспользуемых элементов TUI. Все символы — точно те, что
пойдут в код. ANSI-кодов нет; цвет указан комментарием в формате
`<color: token-name>` или сноской под мокапом. Используем только
псевдографику IBM437 + базовый Unicode: `═║╔╗╚╝`, `─│┌┐└┘├┤┬┴┼`,
`╭╮╰╯`, `┏━┓┃┗━┛`, `░▒▓█`, `▀▄▌▐`, `◢◣◤◥`, `■□●○◎▣▤`. Эмодзи запрещены.

Нотация:
- `<focus>` — стиль рамки/элемента при наличии фокуса клавиатуры.
- `<...-fg>` — semantic color token (см. Раздел J).
- `monochrome:` — как тот же элемент рендерится во второй теме.

Базовый размер: 80×24. Все виджеты должны корректно рисоваться при
обрезке (truncation, ellipsis `…`) на узких раскладках.

---

## Раздел A. Стили рамок

Четыре стиля. Каждый стиль — для своего класса панелей. Активный фокус
переключает рамку на `Heavy` (или, при ограниченных символах, на bold).

### A.1 Sharp — основные панели

```
┌─ STATUS ──────────────────────┐
│ Aelar  Fighter 1  HP 12/12    │
│ AC 16  Init 14  XP 0/300      │
├─ INVENTORY ───────────────────┤
│ • Longsword                   │
│ • Shortbow                    │
└───────────────────────────────┘
```

`├┤┬┴┼` — внутренние разделители панели. Sharp — это «база». Sharp без
фокуса.

### A.2 Round — диалоги и модальные

```
            ╭─ Confirm ──────────╮
            │                    │
            │  Delete save?      │
            │                    │
            │  [ Yes ]  [ No  ]  │
            │                    │
            ╰────────────────────╯
```

Используется для popup-окон, подтверждений, ошибок. Не используется для
постоянных панелей — модальные окна всегда «отделены» от хоста.

### A.3 Double — заголовки экранов, выделение секций

```
╔═ COMBAT ═══════════════════════════════════════════════════════════════╗
║ Round 1                                                                ║
╚════════════════════════════════════════════════════════════════════════╝
```

Внешняя обёртка боевого/exploration-экрана. Внутренние секции —
Sharp. Это даёт визуальную иерархию «экран → панели → подпанели».

### A.4 Heavy — активный фокус, alerts

```
┏━ ACTIONS ━━━━━━━━━━━━━━━━━━━━━┓        ┏━ ALERT ━━━━━━━━━━━━━━┓
┃ [A] Attack   [M] Move         ┃        ┃ ! Save corrupted     ┃
┃ [D] Dodge    [I] Inventory    ┃        ┃   See log for detail ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛        ┗━━━━━━━━━━━━━━━━━━━━━━┛
                                          <color: error-fg>
```

### A.5 Active vs inactive — одна и та же панель

Inactive (виджет не получает фокус):

```
┌─ PARTY ───────────────────────┐
│ Aelar    HP 14/18             │
│ Sila     HP 11/14             │
└───────────────────────────────┘
```

Active (получил фокус — рамка становится Heavy):

```
┏━ PARTY ━━━━━━━━━━━━━━━━━━━━━━━┓   <focus>  <color: accent-fg>
┃ Aelar    HP 14/18             ┃
┃ Sila     HP 11/14             ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

Альтернатива для терминалов, не отрисовывающих `━`: добавить ` ▸` в
заголовок, рамку оставить Sharp, заголовок — bold inverse.

```
┌─▸STATUS ──────────────────────┐   <focus, fallback>
│ ...                           │
└───────────────────────────────┘
```

`monochrome:` Heavy-рамка читается отлично; для совсем старых терминалов
выбираем fallback (`-ascii-only`): `+--+ |  | +--+`.

---

## Раздел B. Прогрессбары

Используем символы заполнения `█` (full), `▓` (3/4), `▒` (1/2), `░`
(1/4), пробел (empty). Все бары — фиксированной ширины, в каждом
варианте показано числовое значение слева/справа.

### B.1 HP bar — три состояния и temp HP

`█` — текущие HP, `░` — пустые. `▓` — temp HP, рисуется поверх «пустой»
части, как если бы они шли «вперёд» от текущего max.

Full (≥ 50%):

```
HP 14/18  [██████████░░░]              <color: success-fg>
```

Wounded (< 50%):

```
HP  8/18  [█████░░░░░░░░]              <color: warning-fg>
```

Critical (< 25%):

```
HP  3/18  [██░░░░░░░░░░░]              <color: error-fg>
```

С временными хитами (`Aid`, `False Life`):

```
HP 14/18 +5 THP  [██████████░░░▓▓▓▓]   <color: success-fg + info-fg(THP)>
```

В широком виде:

```
HP 14/18  [████████████████████░░░░░░░░░░░░░░░░░░░░]
THP  +5   [▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]
```

Числовые проверки:
- full      = HP / max ≥ 0.50
- wounded   = 0.25 ≤ HP / max < 0.50
- critical  = HP / max < 0.25
- 0 HP      = `HP 0/18 [░░░░░░░░░░░░░] DOWN` (`<color: dim-fg>` + label).

### B.2 XP bar

```
Level 2  XP 240/300  [█████████░░░]
```

При level-up — короткая «вспышка» (1 frame heavy fill):

```
Level 2 -> 3  XP 300/300  [█████████████]  LEVEL UP!
                                            <color: accent-fg, bold>
```

### B.3 Resource bar — ячейки заклинаний / use counters

Ячейки заклинаний (Wizard L3, 4 первого и 2 второго уровня; 1 уровня
израсходовано 1):

```
Spells L1: ■■■□    L2: ■■    L3: □
```

`■` — заряженная, `□` — потрачена. После короткого отдыха — снова
заполнить (для тех абилок, что восстанавливаются на короткий отдых):

```
Action Surge:  [●]            <color: accent-fg>
Second Wind:   [○]   (used)   <color: dim-fg>
```

### B.4 Compact bar — однострочная

Для PARTY-панели в раскладке 120×40:

```
Aelar   HP 14/18 ▓▓▓▓▓░    AC 16
Sila    HP 11/14 ▓▓▓▓░░    AC 13
Kael    HP  3/16 ▓░░░░░    AC 14    <color: error-fg>
```

6-символьный мини-бар. `▓` = одна шестая HP, округление вниз.

### B.5 Cast bar / long-action bar

10-минутный короткий отдых, обновляется каждые 60 секунд игрового
времени:

```
Resting  [████░░░░░░] 4/10 min                    <color: info-fg>
```

Ритуальное заклинание (Detect Magic, 10 мин):

```
Casting "Detect Magic" (ritual)
[██████████████░░░░░░] 7/10 min   [Esc] cancel    <color: effect-fg>
```

При прерывании:

```
Casting "Detect Magic" (ritual)
[███░░░░░░░░░░░░░░░░░] CANCELLED                  <color: warning-fg>
```

### B.6 Варианты ширины — одинаковое значение, разные ширины

Значение: 14/18 HP = 78%.

```
w=10   [████████░░]
w=20   [████████████████░░░░]
w=40   [████████████████████████████████░░░░░░░░]
```

Округление — `floor(value * width / max)`; финальный `█` заменяется на
`▒`, когда остаток в полу-ячейке, чтобы избежать «прыгающего» хвоста:

```
w=20   13/18  [██████████████▒░░░░░]
```

`monochrome:` все три состояния HP — одинаковый зелёный недоступен,
поэтому: `bold` (full), `regular` (wounded), `bold inverse` (critical).
Заполнители `█/▒/░` остаются.

---

## Раздел C. Иконки статусов и эффектов

Каждое состояние — 1-2 ASCII-символа. Используем латинские буквы как
fallback (терминал на Windows-1251 точно отрисует), плюс альтернативный
«символьный» вариант. В UI настройка `condition_icons: letters | glyphs`.

### C.1 Таблица меток

| Condition       | Letter | Glyph | Color token       | Notes                |
|-----------------|--------|-------|-------------------|----------------------|
| Blinded         | `Bl`   | `o.`  | `effect-fg`       | глаз закрыт          |
| Charmed         | `Ch`   | `♥ `  | `effect-fg`       | сердце; ASCII: `<3` |
| Deafened        | `Df`   | `))`  | `effect-fg`       | волны звука          |
| Frightened      | `Fr`   | `!!`  | `warning-fg`      | страх                |
| Grappled        | `Gr`   | `=O`  | `effect-fg`       | захват               |
| Incapacitated   | `In`   | `--`  | `dim-fg`          |                      |
| Invisible       | `Iv`   | `..`  | `dim-fg, italic`  | точки = «нет тела»   |
| Paralyzed       | `Pa`   | `Px`  | `error-fg`        |                      |
| Petrified       | `Pe`   | `##`  | `wall-fg`         | «камень»             |
| Poisoned        | `Pn`   | `▓ `  | `success-fg dim`  | зелёное              |
| Prone           | `Pr`   | `↓ `  | `dim-fg`          | стрелка вниз         |
| Restrained      | `Rs`   | `=+`  | `warning-fg`      | путы                 |
| Stunned         | `St`   | `*~`  | `warning-fg`      |                      |
| Unconscious     | `Un`   | `ZZ`  | `dim-fg`          |                      |
| Exhaustion (L)  | `Ex1`..`Ex6` | `Ex` | `warning-fg` | с уровнем            |

Дополнительно — не состояния, а маркеры:

| Marker          | Letter | Glyph | Color token      | Назначение         |
|-----------------|--------|-------|------------------|--------------------|
| Temp HP         | `THP`  | `+`   | `info-fg`        | временный хит      |
| Concentration   | `Co`   | `◎`   | `effect-fg`      | держит концентрацию|
| Hidden          | `Hd`   | `?.`  | `dim-fg`         | прячется           |
| Surprised       | `Sp`   | `!?`  | `warning-fg`     | застигнут          |

### C.2 На карте боя

Маленький layout (small zoom, 1 клетка = 1 ячейка) — статус приклеен к
символу существа через `subscript`-нотацию, когда позволяет ширина:

```
g     просто гоблин
g²    клетка с двумя гоблинами (ENGINE.md §2.2)
gᴾ    гоблин со статусом Poisoned (одиночная буква-подсказка)
```

Когда статусов больше одного — выводим **самый тяжёлый** (порядок:
Unconscious > Paralyzed > Stunned > Frightened > Poisoned > … > others).
Полный список доступен по `F` (focus в боковой панели).

Medium/large zoom — иконка-метка лепится в правый верхний угол клетки:

```
┌───┬───┬───┐
│   │ Pn│   │
│   │ g │   │
│   │   │   │
├───┼───┼───┤
│Pr │   │   │
│ @ │   │   │
│   │   │   │
└───┴───┴───┘
```

### C.3 В очереди инициативы

```
INITIATIVE
1 ▶ Aelar       14
2   Goblin A    11   Pn,Pr     <color: enemy-fg + status palette>
3   Goblin B     8   St
4   Sila        10   Co        <color: pc-fg + effect-fg>
```

`Pn,Pr` — список через запятую, не больше двух показываем; третий и
дальше — `+N`: `Goblin A    11   Pn,Pr +2`.

### C.4 На листе персонажа — блок Active conditions

```
┌─ Active conditions ──────────────────────────────────────────────┐
│  [Pn] Poisoned    until end of next turn   src: goblin's blade   │
│  [Co] Concentr.   on "Bless"               drops on damage / sav │
│  [+5] Temp HP     from "Aid"               until long rest       │
└──────────────────────────────────────────────────────────────────┘
```

Пустой блок:

```
┌─ Active conditions ──────────────────────────────────────────────┐
│  (none)                                                          │
└──────────────────────────────────────────────────────────────────┘
```

---

## Раздел D. Индикатор удачи (Luck indicator)

Источник — `DiceStatisticsService`. Поле `luck = session_avg − 10.5`.
Три зоны: lucky (≥ +0.8) — зелёный, normal (−0.8 .. +0.8) — нейтральный,
unlucky (≤ −0.8) — красный.

### D.1 Текстовый компакт (помещается в STATUS-полоску)

```
Luck +1.4 =                            <color: success-fg>
Luck -0.2 =                            <color: dim-fg>
Luck -2.1 =                            <color: error-fg>
```

Знаки — ASCII `+` / `-`. Не используем `−` (U+2212), чтобы не ломать
терминалы без широких шрифтов.

### D.2 Микро-гистограмма (1×5, помещается в углу STATUS)

5 столбцов по 5 высот (`░▒▓█`), сжатая из 20 граней d20 в 5 ведер
(1-4 / 5-8 / 9-12 / 13-16 / 17-20):

```
▒█▓▒░       n=37  Luck +1.4              <color: success-fg>
░░▒░▒       n= 7  not enough data        <color: dim-fg>
```

При n < 10 — индикатор серый (`dim-fg`), подпись «not enough data».

### D.3 Полный режим (по `S`) — гистограмма 20×10 + счётчики

20 столбцов по 10 в высоту. Высота нормирована к максимуму. Подсветка:
крит (20) — зелёным, фиаско (1) — красным.

```
╔═ Dice statistics — d20 raw ═════════════════════════════════════════════╗
║                                                                         ║
║       █                                                                 ║
║       █                          █                                      ║
║       █     █  █                 █                                      ║
║       █     █  █  █     █     █  █                                      ║
║       █  █  █  █  █     █  █  █  █                       █              ║
║    █  █  █  █  █  █  █  █  █  █  █  █  █     █     █     █              ║
║    █  █  █  █  █  █  █  █  █  █  █  █  █  █  █  █  █  █  █              ║
║ █  █  █  █  █  █  █  █  █  █  █  █  █  █  █  █  █  █  █  █              ║
║ █  █  █  █  █  █  █  █  █  █  █  █  █  █  █  █  █  █  █  █              ║
║ 1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20              ║
║                                                                         ║
║ Rolls (session):  n = 137     avg raw = 11.06     luck = +0.56          ║
║ Rolls (save):     n = 412     avg raw = 10.41     luck = -0.09          ║
║                                                                         ║
║ Crits (20): 11    Fumbles (1):  6                                       ║
║                                                                         ║
║ Last 10:  17, 14, 3, 20, 11, 9, 7, 18, 12, 5                            ║
║                                                                         ║
║ [Esc] back   [C] clear session   [E] export CSV                         ║
╚═════════════════════════════════════════════════════════════════════════╝
```

Color tokens: подсвечен столбец `20` — `crit-fg`, столбец `1` —
`fumble-fg`; `luck` число — green/grey/red в зависимости от зоны.

---

## Раздел E. Маркер вмешательства мастера

Маркер — префикс `*` (звёздочка-астериск) перед строкой лога + цветовой
токен `master-fg`. В `monochrome` — `bold inverse` (никакой звёздочки
недостаточно, мастеру нужно зрительно выделяться).

Базовая строка (когда игрок видит — режим `tagged` или `full`):

```
* master rerolled goblin A's attack: 12 -> 18                  <color: master-fg>
* master applied advantage to Aelar's next save                <color: master-fg>
  reason: "father's blade"
```

Полный пример лога в трёх режимах прозрачности (одна и та же ситуация:
гоблин промазал, мастер заставил его попасть).

### E.1 `master_transparency: hidden` (по умолчанию)

Игрок видит **только результат**. Никаких намёков на вмешательство.

```
┌─ LOG ─────────────────────────────────────────────────────────────────────┐
│ > Goblin A attacks Aelar: 1d20+3 = 18 vs AC 16. HIT.                      │
│ > Damage: 1d6+1 piercing = 5. Aelar 14/18 -> 9/18.                        │
└───────────────────────────────────────────────────────────────────────────┘
```

(В мастерском логе — полная история; см. ниже.)

### E.2 `master_transparency: tagged`

Игрок видит пометку, но не причину.

```
┌─ LOG ─────────────────────────────────────────────────────────────────────┐
│ > Goblin A attacks Aelar: 1d20+3 = 12 vs AC 16. MISS.                     │
│ * master adjusted the roll.                          <master-fg>          │
│ > Goblin A attacks Aelar: 1d20+3 = 18 vs AC 16. HIT.                      │
│ > Damage: 1d6+1 piercing = 5. Aelar 14/18 -> 9/18.                        │
└───────────────────────────────────────────────────────────────────────────┘
```

### E.3 `master_transparency: full`

Видна и причина — для дидактического / настольно-классического режима.

```
┌─ LOG ─────────────────────────────────────────────────────────────────────┐
│ > Goblin A attacks Aelar: 1d20+3 = 12 vs AC 16. MISS.                     │
│ * master rerolled the attack (12 -> 18).             <master-fg>          │
│   reason: "first hit must land, dramatic beat"                            │
│ > Goblin A attacks Aelar: 1d20+3 = 18 vs AC 16. HIT.                      │
│ > Damage: 1d6+1 piercing = 5. Aelar 14/18 -> 9/18.                        │
└───────────────────────────────────────────────────────────────────────────┘
```

### E.4 Мастерский лог (всегда `full`)

Мастер видит каждое своё вмешательство, в любом режиме прозрачности:

```
┌─ MASTER LOG ──────────────────────────────────────────────────────────────┐
│ R1 T3  * reroll(roll_id=a7c1, 12 -> 18)              "dramatic beat"      │
│ R1 T4  * grant_advantage(Aelar, next=1)              "father's blade"     │
│ R1 T5  * narrate("The blade hums in your hand.")     audience=Aelar       │
│ R1 T6  * apply_modifier(item=dagger, +1 atk)         "fathers' blade"     │
└───────────────────────────────────────────────────────────────────────────┘
```

Поля: `R<round> T<tick>`, тип `MasterIntent`, краткие args, причина в
кавычках (если есть).

---

## Раздел F. Тосты и нотификации

Тост — 3-5 строк, появляется в правом верхнем углу (по умолчанию) или
правом нижнем (для боя — чтобы не закрывать INITIATIVE). Скрывается
автоматически: `info` — 4 с, `warn` — 6 с, `error` — пока не нажмут;
`crit` — 1 с (вспышка).

### F.1 Базовая форма

```
                                              ╭─ Notification ────────╮
                                              │  +50 XP               │
                                              │  Defeated goblin      │
                                              ╰───────────────────────╯
                                              <color: info-fg>
```

### F.2 Виды

Level up (золотой акцент, 5 секунд):

```
╭─ Level up! ───────────────╮      <color: accent-fg, bold>
│  Aelar reached level 2    │
│  +1 feature unlocked      │
│  Press [C] to assign      │
╰───────────────────────────╯
```

Loot (синий):

```
╭─ Found ───────────────────╮      <color: info-fg>
│  Talisman of Fortitude    │
│  (Uncommon, attuned)      │
╰───────────────────────────╯
```

XP (нейтральный):

```
╭─ XP ──────────────────────╮      <color: neutral-fg>
│  +50 XP                   │
╰───────────────────────────╯
```

Discovery (фиолетовый — magical/effect):

```
╭─ Discovery ───────────────╮      <color: effect-fg>
│  Hidden passage found     │
│  (south wall)             │
╰───────────────────────────╯
```

Quest (зелёный):

```
╭─ Quest updated ───────────╮      <color: success-fg>
│  "Find the lost miners"   │
│  Step 2/4 completed       │
╰───────────────────────────╯
```

Critical hit (красная вспышка, ровно 1 с):

```
╭─ ! CRIT ! ────────────────╮      <color: crit-fg, bold inverse>
│  Aelar -> Goblin A        │
│  damage x2 = 14           │
╰───────────────────────────╯
```

### F.3 Стек нотификаций

Когда есть несколько — складываются сверху вниз, новые сверху:

```
                                              ╭─ Quest updated ───────╮
                                              │  "Find lost miners"   │
                                              │  Step 2/4 done        │
                                              ╰───────────────────────╯
                                              ╭─ Found ───────────────╮
                                              │  Talisman of Fort.    │
                                              ╰───────────────────────╯
                                              ╭─ +50 XP ──────────────╮
                                              │  Defeated goblin      │
                                              ╰───────────────────────╯
```

Максимум 3 одновременно; остальные ждут очереди. Свернуть весь стек —
клавиша `N`.

### F.4 Локализация

EN:

```
╭─ Found ───────────────────╮
│  Talisman of Fortitude    │
╰───────────────────────────╯
```

RU (длиннее, рамка тянется или используется `*_short`):

```
╭─ Найдено ─────────────────────────╮
│  Талисман Стойкости               │
╰───────────────────────────────────╯
```

На 80×24 если рамка не помещается — берём `*_short`:

```
╭─ Найдено ─────────────────╮
│  Талисман Стойк.          │
╰───────────────────────────╯
```

---

## Раздел G. Кнопки, hotkey-подсказки

### G.1 Стиль кнопок

Unfocused:

```
 Save     Load     Quit
```

Focused (Heavy-обводка скобками):

```
[ Save ]  Load     Quit                    <color: accent-fg>
```

Pressed (мгновенный «дребезг», ~50 мс):

```
< Save >  Load     Quit                    <color: accent-fg, inverse>
```

### G.2 Hotkey подсветка первой буквы

В большинстве экранов hotkey — отдельная буква в квадратных скобках:

```
[S]ave   [L]oad   [Q]uit
```

В `monochrome` буква в скобках идёт `bold`, остальные — regular.

### G.3 Группы кнопок — горизонтально / вертикально

Горизонтально (footer боевого экрана):

```
[A]ttack  [M]ove  [D]odge  [I]nventory  [S]tats  [?] Help
```

Вертикально (главное меню):

```
   ┌─────────────────────────┐
   │  [N]  New game          │
   │  [C]  Continue          │
   │  [B]  Create character  │
   │  [O]  Options           │
   │  [Q]  Quit              │
   └─────────────────────────┘
```

### G.4 Локализованные сокращения

RU полная форма помещается на 120+:

```
[A]така   [M]Движение   [D] Уклон   [I]нвент.   [S]тат.   [?] Помощь
```

На 80×24 RU — короткая форма (`*_short`):

```
[А]так   [М]Дв.   [У]кл.   [И]нв.   [С]ат.   [?] Спр.
```

Замечание: ключи `attack_short = "Атак"`, `move_short = "Дв."`, и т.д.,
плюс отдельный ключ `attack_key = "А"` (буква-хоткей, не первая буква
лейбла — её надо явно прописать в локалях).

### G.5 Footer-стрипа — сводка hotkeys текущего экрана

Внизу каждого экрана — постоянная полоска. Шрифт — обычный, но клавиши
`[X]` — bold; разделитель — `·`.

```
[A]ttack · [M]ove · [D]odge · [I]nventory · [S]tats · [Tab] cycle · [?] help · [Esc] cancel
```

Когда не влезает — обрезается с конца, добавляется `…`:

```
[A]ttack · [M]ove · [D]odge · [I]nventory · [S]tats …
```

(Скрытые — доступны по `?`.)

Локализация (узкий вид, 80):

```
[А]так · [М]Дв · [У]кл · [И]нв · [С]ат · [Tab] цикл · [?] спр · [Esc] отм
```

---

## Раздел H. Фокус и выделение

### H.1 Фокус на панели — Heavy-рамка

```
┏━ PARTY ━━━━━━━━━━━━━━━━━━━━━━━┓   <focus>
┃ Aelar    HP 14/18             ┃
┃ Sila     HP 11/14             ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

### H.2 Выбранный пункт меню — символ `>` + inverse

```
   New game
 > Continue                <inverse, accent-fg>
   Create character
   Options
   Quit
```

В `monochrome` — `>` + `bold inverse`. Без цвета.

### H.3 Disabled — `dim-fg`, без хоткея

```
   New game
   Continue                <color: dim-fg>   (no save found)
 > Create character
```

При попытке выбрать — короткий «зум»-эффект (1 frame inverse) +
status-bar message «no save found».

### H.4 Курсор в полях ввода

Текстовый курсор — символ `▏` (U+258F, вертикальная полоска) или `_`
(fallback). Мигает каждые 500 мс.

```
Name: [Aelar▏                ]
```

При не-фокусе:

```
Name: [Aelar                  ]
```

### H.5 Курсор на карте боя

Маркер цели/выбора клетки — мигающие `[ ]` вокруг ячейки:

small zoom:

```
#..[g]....#
```

medium zoom:

```
┌───┰───┰───┐
│   ┃ g ┃   │
│   ┃   ┃   │
│   ┃   ┃   │
└───┸───┸───┘
```

`┃┰┸` — выделение клетки под курсором (heavy-граница только этой
клетки). Это часть карты, не отдельный виджет; здесь — для справки.

---

## Раздел I. Поля ввода

### I.1 Текстовое поле

Unfocused:

```
Name:  [                              ]
```

Focused (Heavy-скобки + курсор):

```
Name:  ┃Aelar▏                        ┃
```

С placeholder (dim-fg, italic):

```
Name:  [ enter name…                  ]      <color: dim-fg>
```

С ошибкой валидации:

```
Name:  [                              ]
       ! name is required                     <color: error-fg>
```

### I.2 Число с шагом (spinner)

```
Age:   [<  25  >]                     range 18..120
```

`<` и `>` — кнопки `-/+` (клавиши `←/→`). Focused — Heavy-скобки:

```
Age:   ┃<  25  >┃                     <focus>
```

### I.3 Чекбокс

```
[x] Enable autosave
[ ] Color theme
```

Focused:

```
[x] Enable autosave
[ ] Color theme       <inverse>      <focus>
```

`monochrome:` `[x]` остаётся, заполнение — bold.

### I.4 Радиогруппа

```
Theme:   (•) Color    ( ) Monochrome
```

Focused-сейчас выбранный — inverse:

```
Theme:   (•) Color    ( ) Monochrome      <focus on Color>
         ^^^^^^^^^^
```

Альтернативный набор символов (когда `•` не отрисовывается): `(*)` /
`( )`.

### I.5 Дроп-даун (closed / open)

Closed:

```
Language:  [ English        ▼]
```

Focused, closed:

```
Language:  ┃ English        ▼┃
```

Open:

```
Language:  ┃ English        ▲┃
           ╭─────────────────╮
           │ > English       │   <focus, accent-fg>
           │   Русский       │
           ╰─────────────────╯
```

### I.6 Слайдер

```
Volume:  [████████░░░░░░░░░░░░]   40 / 100
```

Focused — добавляется маркер позиции `▌`:

```
Volume:  ┃████████▌░░░░░░░░░░░┃   40 / 100   <focus>
```

`←/→` — шаг 5; `Shift+←/→` — шаг 25; `Home/End` — края.

---

## Раздел J. Цветовые токены — полная таблица

База для CSS-переменных в `color.tcss` и `monochrome.tcss`. Используется
**только** через эти токены — в виджетах никакого hardcoded `#rrggbb`.

| Token         | Назначение                            | `color` (приоритет) | `monochrome`              |
|---------------|---------------------------------------|---------------------|---------------------------|
| `pc-fg`       | имя/символ PC, своя партия            | bright yellow       | `bold`                    |
| `friendly-fg` | дружественные NPC                     | cyan                | `bold dim`                |
| `enemy-fg`    | враги                                 | red                 | `inverse`                 |
| `neutral-fg`  | нейтральные NPC                       | yellow (no bright)  | regular                   |
| `dead-fg`     | мёртвые/без сознания                  | dark grey           | `dim strike`              |
| `object-fg`   | сундуки, двери, объекты               | blue                | regular                   |
| `wall-fg`     | стены, скалы                          | white dim           | `dim`                     |
| `effect-fg`   | области заклинаний, статусы           | magenta             | `italic`                  |
| `dim-fg`     | приглушённый текст, disabled          | grey                | `dim`                     |
| `accent-fg`   | акцент (фокус, level up, кнопки)      | bright white        | `bold inverse`            |
| `warning-fg`  | warning, низкий ресурс                | bright yellow       | `bold`                    |
| `error-fg`    | ошибка, critical HP, fumble банер     | bright red          | `bold inverse`            |
| `success-fg`  | success, full HP, quest done          | bright green        | `bold`                    |
| `info-fg`     | информация, THP, loot                 | bright cyan         | `bold dim`                |
| `master-fg`   | вмешательства мастера                 | bright magenta      | `bold inverse italic`     |
| `crit-fg`     | критический успех (20)                | bright green        | `bold inverse`            |
| `fumble-fg`   | фиаско (1)                            | bright red          | `bold strike`             |

Применение:
- В `*.tcss` определяется `$pc-fg: yellow;` (color) и `$pc-fg: $foreground;
  text-style: bold;` (monochrome).
- `widgets/*.py` — `Static("@", classes="pc")`, в `.tcss`:
  `.pc { color: $pc-fg; }`.
- Композитные стили (например, dead PC) — два класса:
  `Static("@", classes="pc dead")`.

Соответствие `sprite_color_token` (`UI.md` §4.1) ↔ palette:

| sprite_color_token | text token   |
|--------------------|--------------|
| `pc`               | `pc-fg`      |
| `friendly`         | `friendly-fg`|
| `enemy`            | `enemy-fg`   |
| `neutral`          | `neutral-fg` |
| `object`           | `object-fg`  |

---

## Раздел K. Спрайт-шаблоны для контента

Каждый блок — точно то, что пойдёт в `content/sprites/<id>.yaml`.
Соблюдены инварианты `UI.md` §4: `char_small` (1×1), `sprite_medium`
(3×3), `sprite_large` (5×3 или 5×5), `char_dead` (1×1).

### K.1 Aelar — человек, воин (PC)

```yaml
id: pc_human_fighter_aelar
char_small: '@'
sprite_medium: |
  -+-
  '@'
  /|\
sprite_large: |
   ,-.
  |   |
  |@@@|
  / | \
   / \
char_dead: 'x'
sprite_color_token: pc
description:
  en: "A square-jawed human fighter in chainmail."
  ru: "Скуластый человек-воин в кольчуге."
```

Визуальная проверка:

```
small:  @
medium: -+-
        '@'
        /|\
large:   ,-.
        |   |
        |@@@|
        / | \
         / \
```

### K.2 Sila — эльфийка, плут (PC)

```yaml
id: pc_elf_rogue_sila
char_small: '@'
sprite_medium: |
  /^\
  >@<
  /=\
sprite_large: |
   /^\
  / o \
  | @ |
   \=/
   /|\
char_dead: 'x'
sprite_color_token: pc
description:
  en: "A lithe elf rogue, daggers ready."
  ru: "Гибкая эльфийка-плут с парой кинжалов."
```

```
small:  @
medium: /^\
        >@<
        /=\
large:   /^\
        / o \
        | @ |
         \=/
         /|\
```

### K.3 Goblin (enemy)

```yaml
id: goblin
char_small: 'g'
sprite_medium: |
  ,_,
  o^o
  /|\
sprite_large: |
  .-.-.
  ( o o)
   \"v"/
   /|||\
    / \
char_dead: 'x'
sprite_color_token: enemy
description:
  en: "A small green humanoid, mean and quick."
  ru: "Мелкий зеленокожий, злой и шустрый."
```

```
small:  g
medium: ,_,
        o^o
        /|\
large:  .-.-.
        ( o o)
         \"v"/
         /|||\
          / \
```

### K.4 Skeleton (enemy)

```yaml
id: skeleton
char_small: 's'
sprite_medium: |
  .O.
  -+-
  /|\
sprite_large: |
   _.O._
  /  +  \
  | --- |
   \ | /
    /|\
char_dead: 'x'
sprite_color_token: enemy
description:
  en: "A rattling skeleton, jaw hanging askew."
  ru: "Гремящий скелет с перекошенной челюстью."
```

```
small:  s
medium: .O.
        -+-
        /|\
large:   _.O._
        /  +  \
        | --- |
         \ | /
          /|\
```

### K.5 Chest (object)

```yaml
id: chest
char_small: 'o'
sprite_medium: |
  ___
  |o|
  ===
sprite_large: |
   ______
  |  __  |
  | |  | |
  |_|__|_|
   ======
char_dead: ''               # объекты не «умирают»
sprite_color_token: object
description:
  en: "A sturdy wooden chest with iron bands."
  ru: "Крепкий деревянный сундук с железными полосами."
states:
  closed:
    sprite_medium_override: |
      ___
      |o|
      ===
  open:
    sprite_medium_override: |
      \_/
      |.|
      ===
  locked:
    sprite_medium_override: |
      ___
      |L|
      ===
```

```
small:  o
medium closed:   ___      open:   \_/      locked: ___
                 |o|              |.|              |L|
                 ===              ===              ===
large closed:    ______
                |  __  |
                | |  | |
                |_|__|_|
                 ======
```

### K.6 Door (object) — closed / open

```yaml
id: door
char_small_closed: '+'
char_small_open:   '/'
sprite_medium_closed: |
  ___
  |H|
  | |
sprite_medium_open: |
  __
   /|
    |
sprite_large_closed: |
   ____
  |    |
  |  H |
  |    |
  |____|
sprite_large_open: |
   ____
  | /  
  |/   
  /    
  |____|
char_dead: ''
sprite_color_token: object
description:
  en: "A reinforced wooden door."
  ru: "Укреплённая деревянная дверь."
```

```
small closed:   +       open:   /
medium closed:  ___     open:   __
                |H|              /|
                | |               |
large closed:    ____    open:    ____
                |    |           | /
                |  H |           |/
                |    |           /
                |____|           |____|
```

Заметка по дверям: легенда боевой карты говорит «`+` closed, `/` open»
— одинаково для обеих локалей.

---

## Открытые вопросы (для последующих PR)

1. `condition_icons: letters | glyphs` — глобальная настройка или
   per-theme? Предположение: глобально, дефолт — `letters` (надёжнее на
   разных шрифтах).
2. Cast bar при ритуалах: показывать в STATUS или отдельным toast?
   Сейчас нарисован как toast/centered panel — нужно решение, согласуется
   ли с `request_intent` событиями (см. ENGINE.md §3).
3. Сокращения RU для длинных терминов (`Иниц.`, `Атак`, `Спр.`) —
   зафиксированы как `*_short` ключи; нужен gettext-конвенция: один
   ключ `attack_short` или контекстный `pgettext("button_short", "Attack")`.
4. Звук/анимация для `crit`-toast — пока нет требований; крит-toast 1 с
   считаем достаточным.

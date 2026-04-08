# Spec: Memory & Context

## Обзор

У агентов три уровня памяти, и все должны уместиться в контекстное окно LLM. World State — факты в SQLite. Сжатая история — суммаризация прошлых событий. Рабочий контекст — последние ходы без обработки.

---

## Сессия

### Структура

```python
@dataclass
class Session:
    session_id: str
    campaign_id: str
    created_at: datetime
    last_active: datetime
    turn_count: int
    round_count: int
    state: SessionState  # awaiting_player | processing | session_ended
    party: list[Character]
    active_scene: str  # текущая локация
```

### World State (SQLite)

World State организован по паттерну **Repository per aggregate** (см. `docs/system-design.md`, секция «Архитектура World State Store»). Каждый агрегат хранится в своей таблице и управляется своим репозиторием. WorldStateDB — фасад, координирующий транзакции и snapshot.

Строковые поля с фиксированным набором значений описаны как enum'ы — это даёт валидацию на уровне типов. Полные определения — в `contracts/models.py`.

```python
class CharacterStatus(str, Enum):  # alive | dead | incapacitated | deprived | paralyzed | delirious
class Disposition(str, Enum):      # friendly | neutral | hostile
class CharacterRole(str, Enum):    # player | companion | npc
class QuestStatus(str, Enum):      # active | completed | failed
class EventType(str, Enum):        # combat | dialogue | discovery | quest | death
class TurnRole(str, Enum):         # player | dm | companion_a | companion_b

@dataclass
class Character:  # все сущности: игрок, компаньоны, NPC, враги
    id: str
    name: str
    class_: str
    role: CharacterRole
    strength: int
    dexterity: int
    willpower: int
    max_strength: int      # начальное значение, фиксируется при создании
    max_dexterity: int     # начальное значение, фиксируется при создании
    max_willpower: int     # начальное значение, фиксируется при создании
    hp: int
    max_hp: int
    armor: int = 0
    gold: int = 0
    inventory: list[InventoryItem] = field(default_factory=list)
    fatigue: int = 0  # каждая усталость занимает 1 слот инвентаря
    status: CharacterStatus = CharacterStatus.ALIVE
    location_id: str = ""
    description: str = ""
    disposition: Disposition = Disposition.NEUTRAL
    notes: str = ""  # свободное поле для DM

@dataclass
class InventoryItem:
    name: str
    slots: int = 1       # сколько слотов занимает (громоздкие = 2)
    bulky: bool = False   # громоздкий предмет

@dataclass
class Location:
    id: str
    name: str
    description: str
    connected_to: list[str]  # ID соседних локаций
    discovered: bool = False

@dataclass
class Quest:
    id: str
    title: str
    description: str
    status: QuestStatus = QuestStatus.ACTIVE
    giver_character_id: str = ""

@dataclass
class Event:
    id: int
    turn_number: int
    description: str
    event_type: EventType
    created_at: datetime

@dataclass
class Turn:  # сырые ходы, нужны для восстановления сессии
    id: int
    turn_number: int
    role: TurnRole
    content: str
    commands: list[dict] | None = None
    created_at: datetime

@dataclass
class CompressedHistory:
    id: int
    summary: str
    covers_turns_from: int
    covers_turns_to: int
    created_at: datetime
```

### Снимок World State

Перед каждым LLM-вызовом собирается текстовое представление мира. Формируется кодом, не LLM.

```
## Состояние мира

Локация: Тёмная пещера (выходы: Лесная поляна, Подземный зал)

Партия:
- Игрок (Воин): HP 8/12, STR 14, DEX 10, WIL 8, Броня 2, Золото 15 | Усталость: 1 | Меч (1), щит (1), факел (1) [4/10 слотов]
- Кира (Следопыт): HP 6/6, STR 10, DEX 14, WIL 8, Броня 1, Золото 8 | Усталость: 0 | Лук (2, громоздкий), кинжал (1) [3/10 слотов]
- Торин (Наёмник): HP 4/8, STR 14, DEX 8, WIL 12, Броня 1, Золото 3 | Усталость: 0 | Секира (2, громоздкий) [2/10 слотов]

Другие персонажи здесь:
- Гоблин-стражник (NPC, враждебный): HP 4/4, STR 8, DEX 12, WIL 6, Броня 0

Активные квесты:
- Найти пропавших шахтёров

Последние события:
- Партия вошла в пещеру
- Торин ранен гоблином (−4 HP)
```

Объём: 300–600 токенов.

---

## Политика памяти

### Три уровня

| Уровень | Хранилище | Обновление | Размер |
|---------|-----------|-----------|--------|
| **World State** | SQLite | После каждого хода DM (через команды) | Растёт с миром |
| **Сжатая история** | SQLite | При срабатывании триггера компрессии | ~500–1000 токенов |
| **Рабочий контекст** | В памяти + дублируется в SQLite (таблица `turns`) для восстановления сессии | Каждый ход (добавление) | Последние N ходов |

### Правила

1. **World State — главный источник фактов.** В промпте DM-агента прописано:
   «если сжатая история и World State расходятся — верь World State».
   Автоматической проверки нет — полагаемся на инструкцию в промпте.
2. **Сжатая история — контекст, не факты.** Даёт нарративную связность,
   но может потерять или исказить детали при компрессии.
3. **Рабочий контекст — последние ходы как есть.** Без них LLM не поймёт,
   что сейчас происходит.

---

## Бюджет контекста

### DM-агент

| Компонент | Токены | Источник |
|-----------|--------|----------|
| System prompt + шпаргалка механик | 1400–1800 | Статичный шаблон + ключевые правила Cairn |
| Снимок World State | 400–600 | Из SQLite |
| Схемы команд | 300–500 | Статичные JSON-схемы |
| Правила Cairn (RAG) | 0–400 | Если ход затрагивает механику |
| Сжатая история | 500–1000 | Из SQLite |
| Последние ходы (как есть) | 1500–2500 | 5–8 ходов |
| **Итого вход** | **4100–6800** | |
| **Бюджет на ответ** | **500–1000** | |

### Companion-агент

| Компонент | Токены | Источник |
|-----------|--------|----------|
| System prompt + профиль | 400–600 | Шаблон + config |
| Снимок World State | 300–400 | Из SQLite |
| Сжатая история | 300–600 | Из SQLite |
| Последние ходы (как есть) | 1000–2000 | 3–5 ходов |
| **Итого вход** | **2000–3600** | |
| **Бюджет на ответ** | **200–400** | |

### Что резать при превышении

Если контекст не влезает, режем в таком порядке:
1. Правила Cairn — с 3 чанков до 1
2. Сжатая история — обрезаем начало
3. Последние ходы — с 8 до 3
4. Снимок World State — убираем неактивные квесты, далёкие локации

System prompt и схемы команд не трогаем.

---

## Компрессия

### Триггер

Когда рабочий контекст перевалил за 3000 токенов (~6000–9000 символов кириллицей, 2–3 раунда игры). Считаем через tiktoken.

### Процесс

```
1. Берём самые старые ~1500 токенов из рабочего контекста
2. LLM-вызов (temperature=0.2): суммаризировать, сохранив ключевые факты
3. Добавить результат к сжатой истории
4. Дописать факты из World State (SELECT из SQLite, без LLM)
5. Удалить сжатые ходы из рабочего контекста
```

### Промпт компрессора

```
[prompt_version: compressor-v1]

Ты — ассистент для ведения журнала RPG-сессии.

Суммаризуй следующие события, сохранив ВСЕ ключевые факты:
- Кто погиб, кто ранен, какие статусы изменились
- Какие решения приняли персонажи
- Куда переместилась партия
- Какие предметы найдены или потеряны
- Как изменились квесты

Пиши кратко, в прошедшем времени. Не добавляй интерпретаций.

{turns_to_compress}
```

Temperature 0.2 — минимум креативности, максимум точности.

### Дополнение из World State

После компрессии к summary дописываются факты из SQLite (простой SELECT, без LLM):
- Персонажи со статусом `dead`, `incapacitated`, `deprived`, `paralyzed` или `delirious`
- Квесты со статусом `completed` или `failed`
- Текущая локация партии

Даже если компрессор что-то потерял — критичные факты на месте.

### Если компрессия упала

Timeout или ошибка LLM — просто обрезаем старые ходы. Грубо, но World State никуда не денется, агенты продолжат работать. В лог пишем warning.

### Известное ограничение

На длинных кампаниях (50+ раундов) сжатая история проходит через несколько циклов перекомпрессии — детали нарратива теряются. Факты остаются в World State. Путь развития — RAG по истории событий.

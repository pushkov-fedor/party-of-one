# Spec: Tools & API Integrations

## Обзор

Внешние зависимости и инструменты агентов. DM Agent обновляет состояние мира
через tool use (function calling), а не свободным текстом.

---

## LLM API

### Контракт

| Параметр | Значение |
|----------|----------|
| Провайдер | OpenRouter (доступ к разным моделям через единый API) |
| Протокол | HTTPS, REST |
| Аутентификация | API key (env variable) |
| Timeout | 10 с на вызов |
| Max retries | 3 |
| Нарастающая пауза | Exponential: 1 с -> 2 с -> 4 с |
| Rate limit handling | Retry на 429 с Retry-After header |

### Вызовы по типам

| Вызов | Модель (через OpenRouter) | Temperature | Max tokens | Tools |
|-------|--------------------------|-------------|-----------|-------|
| DM narrative + actions | GPT-4o / Claude Sonnet | 0.7–0.8 | 1000 | Да (world state tools) |
| Companion action | GPT-4o / Claude Sonnet | 0.6–0.7 | 400 | Нет |
| History compression | GPT-4o-mini / Claude Haiku | 0.2 | 500 | Нет |

На компрессию ставим дешёвую модель -- там не нужна
креативность, нужны точность и скорость.

### Ошибки

| Код | Причина | Реакция |
|-----|---------|---------|
| 200 | OK | Парсинг ответа |
| 400 | Невалидный запрос | Логируем, не ретраим (это баг) |
| 401 | Невалидный ключ | Завершаем сессию, сообщаем пользователю |
| 429 | Rate limit | Нарастающая пауза + retry |
| 500+ | Server error | Нарастающая пауза + retry |
| Timeout | Нет ответа за 10 с | Retry |
| Connection error | Сеть недоступна | Retry, потом автосохранение |

### Side effects

LLM API stateless. Единственный side effect -- потребление токенов (деньги).
Промпты не сохраняются на стороне провайдера (через API, не playground).

---

## Команды, доступные DM Agent

DM получает команды через function calling / tool use. У каждой команды есть
JSON schema и валидация.

### Чтение (без побочных эффектов)

#### roll_dice

Бросок кубиков. Результат из локального RNG, не от LLM.

```json
{
  "name": "roll_dice",
  "description": "Бросить кубик(и). Результат определяется RNG, не AI.",
  "parameters": {
    "sides": {"type": "integer", "enum": [4, 6, 8, 10, 12, 20]},
    "count": {"type": "integer", "minimum": 1, "maximum": 10, "default": 1}
  },
  "returns": {"rolls": [4, 6], "total": 10},
  "side_effects": "Нет"
}
```

#### get_entity

Чтение полной записи из SQLite. Используется, когда DM нужна деталь,
которой нет в снимке (например, инвентарь конкретного персонажа или описание
далёкой локации). Реализация -- один SELECT.

```json
{
  "name": "get_entity",
  "description": "Получить полную запись о сущности из World State.",
  "parameters": {
    "type": {"type": "string", "enum": ["character", "location", "quest"]},
    "id": {"type": "string"}
  },
  "validation": [
    "type входит в допустимый список",
    "сущность с данным id существует в соответствующей таблице"
  ],
  "returns": "Полная запись сущности (все поля из SQLite)",
  "side_effects": "Нет"
}
```

### Запись (меняют World State)

#### damage_character

```json
{
  "name": "damage_character",
  "parameters": {
    "character_id": {"type": "string"},
    "amount": {"type": "integer", "minimum": 1}
  },
  "validation": [
    "character_id существует",
    "character.status != 'dead'",
    "amount > 0"
  ],
  "side_effects": "Уменьшает HP. Если HP <= 0 — уменьшает STR на остаток. Если STR <= 0 — status='dead'",
  "rollback": "Транзакция SQLite — при ошибке откат"
}
```

#### heal_character

```json
{
  "name": "heal_character",
  "parameters": {
    "character_id": {"type": "string"},
    "amount": {"type": "integer", "minimum": 1}
  },
  "validation": [
    "character_id существует",
    "character.status != 'dead'",
    "HP не может превысить max_hp"
  ],
  "side_effects": "Увеличивает HP (cap: max_hp)"
}
```

#### update_character

```json
{
  "name": "update_character",
  "parameters": {
    "character_id": {"type": "string"},
    "field": {"type": "string", "enum": ["status", "disposition", "location_id", "notes"]},
    "value": {"type": "string"}
  },
  "validation": [
    "character_id существует",
    "field входит в допустимый список",
    "если field='status' — value in ['alive', 'dead', 'incapacitated']",
    "если field='disposition' — value in ['friendly', 'neutral', 'hostile']",
    "если field='location_id' — location существует"
  ],
  "side_effects": "Обновляет поле персонажа в SQLite"
}
```

#### move_entity

```json
{
  "name": "move_entity",
  "parameters": {
    "entity_id": {"type": "string"},
    "location_id": {"type": "string"}
  },
  "validation": [
    "entity существует в таблице characters",
    "entity.status != 'dead'",
    "location_id существует",
    "location доступна из текущей (connected_to)"
  ],
  "side_effects": "Обновляет location_id сущности"
}
```

#### add_event

```json
{
  "name": "add_event",
  "parameters": {
    "description": {"type": "string", "maxLength": 200},
    "event_type": {"type": "string", "enum": ["combat", "dialogue", "discovery", "quest", "death"]}
  },
  "validation": ["description не пустое"],
  "side_effects": "Append в таблицу events"
}
```

#### update_quest

```json
{
  "name": "update_quest",
  "parameters": {
    "quest_id": {"type": "string"},
    "status": {"type": "string", "enum": ["active", "completed", "failed"]}
  },
  "validation": ["quest_id существует"],
  "side_effects": "Обновляет статус квеста"
}
```

#### add_item / remove_item

```json
{
  "name": "add_item",
  "parameters": {
    "character_id": {"type": "string"},
    "item": {"type": "string", "maxLength": 100}
  },
  "validation": ["character_id существует"],
  "side_effects": "Append в inventory (JSON array)"
}
```

```json
{
  "name": "remove_item",
  "parameters": {
    "character_id": {"type": "string"},
    "item": {"type": "string"}
  },
  "validation": ["character_id существует", "item есть в inventory"],
  "side_effects": "Удаляет первое совпадение из inventory"
}
```

#### create_character

```json
{
  "name": "create_character",
  "description": "Создать нового персонажа любого типа (NPC, враг, компаньон и т.д.).",
  "parameters": {
    "name": {"type": "string", "maxLength": 100},
    "role": {"type": "string", "enum": ["npc", "companion"]},
    "class_": {"type": "string", "maxLength": 100},
    "description": {"type": "string", "maxLength": 500},
    "disposition": {"type": "string", "enum": ["friendly", "neutral", "hostile"]},
    "location_id": {"type": "string"},
    "strength": {"type": "integer"},
    "dex": {"type": "integer"},
    "wil": {"type": "integer"},
    "hp": {"type": "integer"},
    "armor": {"type": "integer", "default": 0}
  },
  "validation": [
    "name не пустое",
    "location_id существует",
    "role != 'player' (игрок создаётся только при инициализации)"
  ],
  "side_effects": "INSERT в таблицу characters, генерирует уникальный character_id. max_hp устанавливается равным hp при создании."
}
```

#### restore_stat

```json
{
  "name": "restore_stat",
  "description": "Восстановить характеристику после отдыха или лечения.",
  "parameters": {
    "character_id": {"type": "string"},
    "stat": {"type": "string", "enum": ["strength", "dex", "wil"]},
    "amount": {"type": "integer", "minimum": 1}
  },
  "validation": [
    "character_id существует",
    "character.status != 'dead'",
    "итоговое значение не превышает начальное (max)"
  ],
  "side_effects": "Увеличивает указанную характеристику (cap: начальное значение)"
}
```

#### update_location

```json
{
  "name": "update_location",
  "description": "Изменить описание или связи существующей локации.",
  "parameters": {
    "location_id": {"type": "string"},
    "field": {"type": "string", "enum": ["description", "connected_to"]},
    "value": {"type": "string"}
  },
  "validation": [
    "location_id существует",
    "если field='connected_to' — value это JSON array, все ID существуют"
  ],
  "side_effects": "Обновляет поле локации. Если connected_to — обновляет связи в обе стороны."
}
```

#### create_quest

```json
{
  "name": "create_quest",
  "description": "Создать новый квест.",
  "parameters": {
    "title": {"type": "string", "maxLength": 200},
    "description": {"type": "string", "maxLength": 500},
    "giver_character_id": {"type": "string"}
  },
  "validation": [
    "title не пустое",
    "giver_character_id существует в characters"
  ],
  "side_effects": "INSERT в таблицу quests со статусом 'active'"
}
```

#### create_location

```json
{
  "name": "create_location",
  "description": "Создать новую локацию (при исследовании мира).",
  "parameters": {
    "name": {"type": "string", "maxLength": 100},
    "description": {"type": "string", "maxLength": 500},
    "connected_to": {"type": "array", "items": {"type": "string"}, "minItems": 1}
  },
  "validation": [
    "name не пустое",
    "каждый id в connected_to существует в таблице locations",
    "connected_to содержит хотя бы одну локацию"
  ],
  "side_effects": "INSERT в таблицу locations, генерирует уникальный location_id. Обновляет связи в обе стороны."
}
```

---

## Защита команд

### Валидация

Каждая команда проходит три шага:

1. **Schema validation.** Параметры соответствуют JSON schema.
2. **Referential integrity.** Все entity_id есть в базе.
3. **Business rules.** Мёртвого персонажа нельзя двигать, heal не может
   поднять HP выше max, и т.д.

### Атомарность

Все команды одного хода идут в одной SQLite-транзакции.
Если хоть одна невалидна -- откатываем всё, DM получает re-prompt
с описанием ошибки.

### Лимиты

| Лимит | Значение | Обоснование |
|-------|----------|-------------|
| Max команд per turn | 10 | Обычный ход: 1-3 команды. AoE по группе: ~6. 10 -- запас на сложные сцены и защита от галлюцинаций |
| Max damage per call | 50 | Максимальный кубик в Cairn -- d12 (12). 50 покрывает любой легитимный урон с множителями |
| Max inventory size | 20 items | В Cairn лимит 10 слотов; 20 -- с запасом на мелочь вне слотов |

Превышение -- команда отклоняется, DM получает сообщение об ошибке.

---

## Dice Roller

Локальный RNG. LLM не генерирует результаты бросков.

```python
import random

def roll_dice(sides: int, count: int = 1) -> dict:
    rolls = [random.randint(1, sides) for _ in range(count)]
    return {"rolls": rolls, "total": sum(rolls)}
```

Для тестов фиксируем seed. В production -- `random.SystemRandom()`.

---

## Embedding API

| Параметр | Значение |
|----------|----------|
| Модель | `text-embedding-3-small` (через OpenRouter) |
| Вызов | При RAG-запросе (не каждый ход) |
| Timeout | 5 с |
| Retry | 2 попытки |
| Fallback | DM работает без RAG (warning в логах) |
| Кэш | In-memory LRU, 100 entries |

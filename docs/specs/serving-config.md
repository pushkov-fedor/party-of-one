# Spec: Serving & Configuration

## Обзор

Как запустить, как настроить, куда складывать секреты.

---

## Запуск

### Минимальный запуск

```bash
# Python 3.11+
python --version  # >= 3.11

# Установка зависимостей
pip install -r requirements.txt

# Инициализация RAG-индекса (однократно)
python -m party_of_one.init_index --source data/cairn-srd-ru.md

# Запуск игры
python -m party_of_one.cli

# Запуск в watch mode (для eval)
python -m party_of_one.cli --watch --rounds 30
```

### Зависимости (ожидаемые)

| Пакет | Назначение |
|-------|-----------|
| `openai` | LLM API клиент (OpenAI-compatible API для OpenRouter) |
| `chromadb` | Локальный vector store |
| `sentence-transformers` | Локальная embedding модель |
| `tiktoken` | Подсчёт токенов |
| `sqlite3` | Встроен в Python |
| `pydantic` | Валидация команд и конфигов |
| `structlog` | Structured logging |
| `python-dotenv` | Загрузка .env файла |
| `textual` | TUI-фреймворк (терминальный интерфейс) |
| `rich` | Стилизованный вывод в терминал (используется Textual) |

---

## Конфигурация

### Файл конфигурации

`config.yaml` в корне проекта:

```yaml
# LLM
llm:
  provider: "openrouter"         # openrouter
  model: "openai/gpt-4.1"                       # DM agent (tool use + narrative)
  model_companion: "openai/gpt-4.1-mini"        # Companion agents (structured JSON, без tool use)
  model_cheap: "openai/gpt-4.1-mini"            # History compression
  temperature_dm: 0.75
  temperature_companion: 0.65
  temperature_compressor: 0.2
  max_tokens_dm: 1000
  max_tokens_companion: 400
  timeout_seconds: 10
  max_retries: 3

# RAG
rag:
  embedding_model: "deepvk/USER-bge-m3"   # локальная модель, русский язык
  vector_store_path: "./data/chroma"
  top_k: 3
  min_similarity: 0.3

# Context
context:
  compression_threshold_tokens: 3000
  max_recent_turns: 8
  max_recent_turns_companion: 5

# Session
session:
  db_dir: "./data/sessions"        # директория, файл на сессию ({session_id}.db)
  auto_save_interval_turns: 5

# Guardrails
guardrails:
  pre_llm_enabled: true
  post_llm_enabled: true
  max_input_length: 1000
  max_retries_on_block: 2

# Logging
logging:
  level: "INFO"
  file: "./logs/session.jsonl"
  log_prompts: true          # полные промпты в лог (для отладки)
  log_responses: true        # полные ответы в лог

# Game
game:
  max_tool_calls_per_turn: 10
  max_inventory_slots: 10       # Cairn: 10 слотов (items + fatigue)
  companion_profiles_path: "./data/companions.yaml"
  cairn_srd_path: "./data/cairn-srd-ru.md"
```

### Переопределение через env

Любой параметр можно переопределить переменной окружения:

```bash
PARTY_LLM__PROVIDER=openrouter
PARTY_LLM__MODEL=anthropic/claude-sonnet-4-20250514
PARTY_SESSION__DB_PATH=/tmp/test.db
```

Формат: `PARTY_{SECTION}__{KEY}`, двойное подчёркивание как разделитель.

---

## Секреты

### Хранение

В config.yaml секретов нет. Только через env:

```bash
export OPENROUTER_API_KEY="sk-or-..."
```

### .env файл

Для локальной разработки -- `.env` в корне, добавлен в .gitignore:

```
OPENROUTER_API_KEY=sk-or-...
```

Подхватывается через `python-dotenv` при старте.

### Ротация

Ключи можно менять без рестарта -- клиент читает env при каждом вызове.
(Для PoC ладно, если читаем только при инициализации.)

---

## Версии моделей

### Стратегия

Используем OpenRouter как единый провайдер. В конфиге указываем OpenRouter model id
(формат `vendor/model-name`), например:

```yaml
model: "anthropic/claude-sonnet-4-20250514"
model: "openai/gpt-4o-2024-08-06"
model: "google/gemini-2.0-flash-001"
```

Пишем конкретную версию, не alias -- alias на стороне OpenRouter может поменяться.

### Переключение

Смена модели -- одна строчка в конфиге. Промпты модель-агностичны,
специфичных фич провайдера не используем (кроме tool use, он стандартизирован через OpenRouter).

### Совместимость

Минимум от модели:
- Tool use / function calling
- Context window >= 8K токенов
- Нормальное следование system prompt

---

## Структура проекта (ожидаемая)

```
party-of-one/
├── config.yaml
├── pyproject.toml          # зависимости и метаданные (uv + .venv)
├── .env                    # секреты (в .gitignore)
├── contracts/              # абстрактные интерфейсы (source of truth для API)
│   ├── models.py           # dataclass-модели + enum'ы
│   ├── world_state.py      # WorldStateDB ABC
│   ├── tools.py            # ToolExecutor ABC
│   ├── dm_agent.py         # DMAgent Protocol
│   ├── companion.py        # CompanionAgent Protocol
│   ├── orchestrator.py     # Orchestrator Protocol
│   ├── config.py           # AppConfig структура
│   └── dice.py             # roll_dice контракт
├── data/
│   ├── cairn-srd-ru.md     # правила Cairn (перевод на русский)
│   ├── companions.yaml     # преднастроенные профили компаньонов
│   ├── chroma/             # vector store (в .gitignore)
│   └── sessions/           # SQLite файлы сессий (в .gitignore)
├── logs/
│   └── session.jsonl       # логи (в .gitignore)
├── docs/                   # документация и спецификации
├── src/
│   └── party_of_one/
│       ├── __init__.py
│       ├── models.py        # dataclass-модели + enum'ы (реэкспорт из contracts + доп. свойства)
│       ├── config.py        # Config loading
│       ├── logger.py        # Structured logging
│       ├── orchestrator.py  # Turn management, координация агентов
│       ├── play.py          # Non-interactive CLI (для тестирования)
│       ├── agents/
│       │   ├── llm_client.py  # Общий LLM-клиент (retry, API key)
│       │   ├── dm.py          # DM Agent
│       │   └── companion.py   # Companion Agent
│       ├── tools/
│       │   ├── dice.py            # Dice roller (локальный RNG)
│       │   ├── tool_definitions.py # JSON-схемы tool use для DM
│       │   └── world.py          # ToolExecutor (валидация + исполнение)
│       ├── rag/
│       │   ├── indexer.py   # Cairn SRD indexing
│       │   └── retriever.py # Search
│       ├── guardrails/
│       │   ├── pre_llm.py   # Input filter
│       │   └── post_llm.py  # Output filter
│       └── memory/
│           ├── schema.py              # DDL-схема SQLite
│           ├── world_state.py         # WorldStateDB — фасад (транзакции, snapshot, get_entity)
│           ├── character_repo.py      # CharacterRepository (CRUD, damage, heal, inventory, gold)
│           ├── location_repo.py       # LocationRepository (CRUD, connections, movement)
│           ├── quest_repo.py          # QuestRepository (CRUD, status transitions)
│           ├── event_repo.py          # EventRepository (append, query)
│           ├── turn_repo.py           # TurnRepository (turns, compressed history)
│           ├── compressor.py          # History compression
│           └── context.py             # Context builder (сборка промптов)
└── tests/
```

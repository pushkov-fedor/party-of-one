# Spec: Retriever (RAG Module)

## Обзор

RAG-модуль даёт DM Agent доступ к правилам Cairn через семантический поиск.
DM формулирует запрос исходя из текущего хода, получает релевантные куски правил
и принимает решения на их основе.

---

## Источники

| Источник | Объём | Лицензия | Обновление |
|----------|-------|----------|-----------|
| Cairn SRD (перевод на русский) | ~15 страниц | CC-BY-SA 4.0 | Статичный (pre-built index) |

Оригинал: [github.com/yochaigal/cairn](https://github.com/yochaigal/cairn), файл `first-edition/cairn-srd.md`. Переводим на русский и храним как `data/cairn-srd-ru.md`. Перевод делается один раз перед индексацией.

Что есть в Cairn:
- Создание персонажа (STR, DEX, WIL)
- Боевая система (урон, critical damage, saves)
- Магия (свитки, реликвии)
- Снаряжение и экономика
- Бестиарий (~30 существ)
- Правила исследования подземелий

---

## Индексация

### Chunking

- Paragraph-level splitting
- Размер чанка: ~150--250 токенов
- Overlap: 20 токенов
- Метаданные: `{section, subsection, page}`

Пример:
```
Chunk 1: {section: "Combat", subsection: "Damage"}
  "Damage that reduces a target's HP below zero decreases a target's STR
   by the amount remaining. They must then make a STR save to avoid
   critical damage..."

Chunk 2: {section: "Combat", subsection: "Critical Damage"}
  "If a character takes critical damage, they are incapacitated. If left
   untreated, they die within the hour..."
```

### Embedding

- Модель: `deepvk/USER-bge-m3` (локальная, через sentence-transformers)
- Размерность: 1024
- Язык: русский (и правила, и запросы на русском — билингвальной проблемы нет)
- Индексируем один раз при деплое, складываем в ChromaDB

---

## Поиск

### Пайплайн

```
1. DM Agent обрабатывает действие игрока
       |
2. Если DM нужны правила (бой, saves, магия и т.д.) —
   вызывает search_rules(query="критический урон спасбросок силы")
       |
3. Embedding модель → вектор запроса
       |
4. ChromaDB: cosine similarity, top-k=3, min_similarity >= 0.3
       |
5. Результат возвращается DM как tool result
       |
6. DM использует правила для принятия решений и продолжает генерацию
```

### Параметры поиска

| Параметр | Значение |
|----------|----------|
| top-k | 3 |
| Similarity metric | Cosine |
| Min similarity threshold | 0.3 (ниже -- не включать, правила нерелевантны) |

### Формирование запроса

DM Agent сам решает, когда ему нужны правила, и вызывает tool `search_rules(query)` с осмысленным запросом. Это аналогично `roll_dice` и `get_entity` — agent-driven, не orchestrator-driven. Keyword detection на стороне Orchestrator убран: хрупкий (пропускает парафразы), DM видит полный контекст и формулирует точный запрос.

---

## Когда используется

| Ситуация | RAG | Причина |
|----------|-----|---------|
| Атака / урон | да | Нужны правила damage и saves |
| Проверка характеристики | да | Нужны правила saves |
| Магия / свитки | да | Нужны описания эффектов |
| Снаряжение / предметы | да | Нужны характеристики |
| Свободный нарратив | нет | Правила не нужны |
| Диалог с NPC | нет | Правила не нужны |
| Ход компаньона | нет | Правила проверяет DM, не компаньон |

DM сам решает когда вызвать `search_rules`. Orchestrator не фильтрует.

---

## Reranking

В PoC не делаем. При ~15 страницах и top-k=3 семантический поиск справляется.

При добавлении дополнительных источников правил понадобится:
- Cross-encoder reranker
- Фильтрация по metadata (section-based)
- Увеличенный top-k с последующим reranking до top-3

---

## Оценка качества

Набор из 10–15 тестовых запросов с ожидаемыми секциями правил (например, «атака мечом» → Combat/Damage). Прогоняем через retriever, проверяем что нужный чанк попал в top-3. Целевое значение: hit rate ≥ 90%. Подробнее — `docs/specs/observability-evals.md`.

---

## Ограничения

- **Маленький корпус.** 15 страниц — ошибок меньше, чем на большом корпусе,
  но поиск по ключевым словам может промахнуться при нестандартных формулировках.
- **Нет обновления в runtime.** Если DM придумает новое правило на ходу,
  оно не попадёт в RAG. Только в World State.
- **Нет fallback при недоступности vector store.** Если ChromaDB упал --
  DM работает без правил, опираясь на знания модели. Пишем warning в лог.

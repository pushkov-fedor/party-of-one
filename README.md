# Party of One — AI Dungeon Master & Companions

## Задача

Проект для тех, кто хочет играть в D&D, но не может собрать постоянную группу.
Нужно четыре-пять человек с совпадающим расписанием, нужен мастер, и всё это
должно держаться неделями. Большинство кампаний не начинаются вообще, остальные
разваливаются на третьей сессии.

Party of One — агентная система, где AI-мастер ведёт историю, а в группе с игроком
два AI-персонажа со своими характерами и мотивами. Мир помнит всё что происходило
и не противоречит сам себе.

## Что делает PoC на демо

Игрок выбирает класс и описывает сеттинг в свободной форме — тёмное фэнтези,
детективный городской мир, классическое подземелье. Дальше AI-мастер берёт слово:
описывает обстановку, управляет NPC, следит за правилами и реагирует на то, что делает
игрок. Два AI-компаньона идут рядом — у каждого свой характер и собственные мотивы,
которые иногда расходятся с тем, что хочет игрок.

Можно играть самому или просто наблюдать — в режиме наблюдения все роли занимают
агенты и человек в цепочке не участвует.

Мир и история сохраняются между сессиями — можно закрыть, вернуться через день
и продолжить с того же места.

Демо — это запущенная сессия в терминале (Textual TUI). Видно, как
DM-агент пишет нарратив, AI-компаньоны принимают решения, а рядом обновляется
состояние мира: HP персонажей, статус NPC, журнал событий.


## Запуск

### Вариант 1: Docker из GitHub Container Registry (рекомендуется)

```bash
# Скачать готовый образ (751 MB)
docker pull ghcr.io/pushkov-fedor/party-of-one:latest

# Интерактивная игра (Textual TUI — выбор класса, компаньонов, мира)
docker run -it -e OPENROUTER_API_KEY=sk-or-... ghcr.io/pushkov-fedor/party-of-one

# Watch mode (AI играет сама, бесконечно до смерти всей команды)
docker run -it -e OPENROUTER_API_KEY=sk-or-... ghcr.io/pushkov-fedor/party-of-one party_of_one --watch

# Watch mode с лимитом раундов
docker run -it -e OPENROUTER_API_KEY=sk-or-... ghcr.io/pushkov-fedor/party-of-one party_of_one --watch --rounds 10
```

### Вариант 2: Docker из исходников

```bash
# Сборка образа
docker build -t party-of-one .

# Интерактивная игра
docker run -it -e OPENROUTER_API_KEY=sk-or-... party-of-one

# Watch mode
docker run -it -e OPENROUTER_API_KEY=sk-or-... party-of-one party_of_one --watch
```

### Вариант 3: Локальная установка

```bash
# Зависимости
uv pip install -e ".[dev]"

# .env файл с API-ключом
echo "OPENROUTER_API_KEY=sk-or-..." > .env

# Интерактивная игра (Textual TUI)
python -m party_of_one

# Watch mode
python -m party_of_one --watch

# Неинтерактивная игра (CLI)
python -m party_of_one.play --new --name "Hero" --class_ "Warrior" \
  --companions "Бранка,Тихомир" --setting "Тёмный лес"

# Eval pipeline (watch mode + все оценки)
python -m party_of_one.eval --mode watch --rounds 10 \
  --dm-model qwen/qwen3-max \
  --companion-model qwen/qwen3-235b-a22b-2507 \
  --judge-model anthropic/claude-sonnet-4.6 \
  --save-log eval/data/session_log.json \
  --output eval/results/eval_results.json

# Тесты
python -m pytest tests/ -q
```

### Результаты eval (Qwen3 Max + Qwen3-235B, judge: Claude Sonnet 4.6)

**RAG retriever** — 90.8% hit rate (108/119), MRR 0.843

**Guardrails (embedding)** — 98.0% true positive, 0% false positive (49 инъекций, 57 легитимных)

**DM eval** (session-level, шкала 1-5):

| Критерий | Оценка | Описание |
|----------|--------|----------|
| Plot progression | **2-3**/5 | Сюжет движется, но DM иногда игнорирует решения компаньонов |
| Adaptivity | **2**/5 | DM реагирует на действия, но часто генерирует события независимо от контекста |
| Repetition | **2-3**/5 | Структурные повторы в нарративе |
| Consistency | **2**/5 | ID-путаница (создаёт NPC с одним ID, бьёт по другому), нарратив расходится с world state |
| Rules | **2**/5 | Armor не применяется, спасброски пропускаются, враги бьют нескольких за ход |

**Companion eval** (batched per-companion, шкала 1-5):

| Критерий | Бранка | Тихомир |
|----------|--------|---------|
| In-character | **5**/5 | **4**/5 |
| Agency | **3-4**/5 | **2-3**/5 |
| Variety | **3-4**/5 | **2-3**/5 |
| Liveliness | **4-5**/5 | **4**/5 |

**Holistic** — progression 2-3/5, diversity 3-4/5, reactivity 2/5, narrative 3/5

**Известные проблемы DM (требуют code-level game engine):**
- DM не ставит armor при create_character, даже если выдаёт доспехи — партия умирает за 2-3 раунда
- Враги атакуют 2-3 цели за ход вместо одной
- STR save при HP=0 пропускается — сразу incapacitated
- DM путает ID сущностей между ходами

**Сравнение моделей** — прогоны в `eval/results/`:

| Конфигурация | DM plot | DM rules | Companion character | Файл |
|-------------|---------|----------|---------------------|------|
| **Qwen3 Max + Qwen3-235B** | **2-3** | 2 | **5** | `eval_results_final_v2.json` |
| GPT-4.1 + GPT-4.1-mini | 3 | 2 | 4 | `eval_results_baseline.json` |
| DeepSeek V3.2 + Qwen3-235B | 3 | 2 | 3 | `eval_results_ds_qwen.json` |

## Что PoC не делает

- Полноценный конструктор персонажа: только фиксированные архетипы
- Мультиплеер с другими людьми
- Полный рулбук D&D 5e: механики упрощены
- Графический интерфейс: только текст

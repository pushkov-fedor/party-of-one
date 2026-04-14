<!-- /home/fedor/Study/lectures/Bonus_Track_LLM_Agentic_AI_2025-2026/README.md -->

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

# Watch mode (AI играет сама, бесконечно до TPK)
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

### Результаты eval (лучшая конфигурация: Qwen3 Max + Qwen3-235B, judge: Claude Sonnet 4.6)

**RAG retriever** — 93.3% hit rate (111/119), MRR 0.867

**Guardrails (embedding)** — 98.0% true positive, 0% false positive (49 инъекций, 57 легитимных)

**DM eval** (session-level, шкала 1-5):

| Критерий | Оценка | Описание |
|----------|--------|----------|
| Plot progression | **4**/5 | Сюжет движется: поляна → лес → бой с гоблинами → пленный → раскрытие угрозы → финальная схватка |
| Adaptivity | **3**/5 | DM реагирует на действия компаньонов, но иногда генерирует события независимо |
| Repetition | **3**/5 | Меньше повторений, но механические вставки рвут атмосферу |
| Consistency | **2**/5 | Временные несостыковки, сущности создаются после упоминания |
| Rules | **2**/5 | Спасброски и урон иногда применяются некорректно |

**Companion eval** (batched per-companion, шкала 1-5):

| Критерий | Бранка | Тихомир |
|----------|--------|---------|
| In-character | **4**/5 | **4**/5 |
| Agency | **4**/5 | **3**/5 |
| Variety | **4**/5 | **4**/5 |
| Liveliness | **3**/5 | **3**/5 |

**Holistic** — progression 4/5, diversity 4/5, reactivity 3/5, narrative 3/5

**Сравнение моделей** — 8 прогонов в `eval/results/eval_results_*.json`:

| Конфигурация | DM plot | DM rules | Companion variety | Файл |
|-------------|---------|----------|-------------------|------|
| **Qwen3 Max + Qwen3-235B** | **4** | 2 | **4** | `eval/results/eval_results_qwen_v4_armor.json` |
| GPT-4.1 + GPT-4.1-mini | 3 | 2 | 2 | `eval/results/eval_results_baseline.json` |
| DeepSeek V3.2 + Qwen3-235B | 3 | 2 | 3 | `eval/results/eval_results_ds_qwen.json` |
| GPT-5 + Qwen3-235B | 2 | 1 | 2 | `eval/results/eval_results_gpt5_qwen.json` |

## Что PoC не делает

- Полноценный конструктор персонажа: только фиксированные архетипы
- Мультиплеер с другими людьми
- Полный рулбук D&D 5e: механики упрощены
- Графический интерфейс: только текст

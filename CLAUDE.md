# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies (use uv, never install globally)
uv pip install -e ".[dev]"

# Run all tests
python -m pytest tests/

# Run a single test file
python -m pytest tests/test_phase1_world_state.py -v

# Run a single test class or method
python -m pytest tests/test_phase1_world_state.py::TestDamageSimple::test_damage_reduces_hp -v

# Run tests matching keyword
python -m pytest tests/ -k "guardrail" -v

# Play interactively
python -m party_of_one.play

# Play non-interactively (for automated testing)
python -m party_of_one.play --new --name "Hero" --class_ "Warrior" --companions "Бранка,Тихомир" --setting "Тёмный лес"
python -m party_of_one.play --session <SESSION_ID> --action "Атакую мечом"
```

## Development Flow (STRICT)

**spec → contracts → tests → code.** Never skip steps.

1. **Specs** (`docs/specs/`, `docs/system-design.md`) — describe system behavior
2. **Contracts** (`contracts/`) — abstract interfaces generated from specs, source of truth for API
3. **Tests** (`tests/`) — written by tester agent from specs/contracts, never from code
4. **Code** (`src/`) — implementations inherit from contract ABCs

If changing behavior: update spec first. If spec doesn't change, code shouldn't change.

## Architecture

Solo RPG with 3 AI agents (DM + 2 companions) using Cairn rules, OpenRouter LLM API.

### Key patterns

- **Repository per aggregate**: `CharacterRepository`, `LocationRepository`, `QuestRepository`, `EventRepository`, `TurnRepository` — each in `src/party_of_one/memory/`. `WorldStateDB` is a thin facade (transaction, snapshot, get_entity).
- **Contract inheritance**: all implementations inherit from ABCs in `contracts/`. Python raises `TypeError` if an `@abstractmethod` is missing.
- **SQLAlchemy Core**: no raw SQL anywhere. Schema in `memory/schema.py` via `Table`/`Column`.
- **GuardedToolExecutor**: wraps `ToolExecutor` with guardrail validation BEFORE execution. DM Agent's tool_use_loop calls execute() which validates first, then runs.
- **Three-layer pre-LLM guardrail**: regex+normalization → embedding similarity → delimiter isolation.

### Data flow per round

```
Player input → pre-LLM guardrail → DM Agent (LLM + tool_use_loop) → post-LLM guardrail → narrative
                                    ↓
                              GuardedToolExecutor → PostLLMGuardrail.validate_commands → ToolExecutor → Repository → SQLite
                                    ↓
                              Companion A (LLM, free text) → DM Agent processes → narrative
                              Companion B (LLM, free text) → DM Agent processes → narrative
```

### LLM configuration

- DM: `openai/gpt-4.1` (tool use + narrative)
- Companion: `openai/gpt-4.1-mini` (free text, no tools)
- All prompts in Russian

## Rules

- **Language**: respond in Russian, code stays in English
- **File size**: max 200-300 lines per file
- **No raw SQL**: SQLAlchemy Core minimum
- **Tests ownership**: only tester agent and game-player agent may create/modify `tests/` files
- **Dependencies**: never install globally, use `uv` + `.venv`
- **Contracts = source of truth**: if code diverges from contract, fix the code (or update spec first, then contract, then code)

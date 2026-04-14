"""Configuration loading: YAML file + environment variable overrides."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel


class LLMConfig(BaseModel):
    provider: str = "openrouter"
    model: str = "openai/gpt-4.1"
    model_companion: str = "openai/gpt-4.1-mini"
    model_cheap: str = "openai/gpt-4.1-mini"
    temperature_dm: float = 0.4
    temperature_companion: float = 0.65
    temperature_compressor: float = 0.2
    max_tokens_dm: int = 2000
    max_tokens_companion: int = 400
    timeout_seconds: int = 30
    max_retries: int = 3


class RAGConfig(BaseModel):
    embedding_model: str = "baai/bge-m3"
    vector_store_path: str = "./data/chroma"
    top_k: int = 3
    min_similarity: float = 0.3


class ContextConfig(BaseModel):
    compression_threshold_tokens: int = 8000
    max_recent_turns: int = 8
    max_recent_turns_companion: int = 5


class SessionConfig(BaseModel):
    db_dir: str = "./data/sessions"
    auto_save_interval_turns: int = 5


class GuardrailsConfig(BaseModel):
    pre_llm_enabled: bool = True
    post_llm_enabled: bool = True
    max_input_length: int = 1000
    max_retries_on_block: int = 2
    embedding_similarity_threshold: float = 0.82


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = "./logs/session.jsonl"
    log_prompts: bool = True
    log_responses: bool = True


class GameConfig(BaseModel):
    max_tool_calls_per_turn: int = 10
    max_inventory_slots: int = 10
    companion_profiles_path: str = "./data/companions.yaml"
    cairn_srd_path: str = "./data/cairn-srd-ru.md"


class AppConfig(BaseModel):
    llm: LLMConfig = LLMConfig()
    rag: RAGConfig = RAGConfig()
    context: ContextConfig = ContextConfig()
    session: SessionConfig = SessionConfig()
    guardrails: GuardrailsConfig = GuardrailsConfig()
    logging: LoggingConfig = LoggingConfig()
    game: GameConfig = GameConfig()


def _apply_env_overrides(data: dict) -> dict:
    """Apply PARTY_{SECTION}__{KEY} env vars to config dict."""
    prefix = "PARTY_"
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        parts = key[len(prefix) :].lower().split("__", 1)
        if len(parts) != 2:
            continue
        section, field = parts
        if section in data and isinstance(data[section], dict):
            if field in data[section]:
                target_type = type(data[section][field])
                if target_type is bool:
                    data[section][field] = value.lower() in ("true", "1", "yes")
                elif target_type is int:
                    data[section][field] = int(value)
                elif target_type is float:
                    data[section][field] = float(value)
                else:
                    data[section][field] = value
    return data


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Load config from YAML file with env overrides."""
    path = Path(path)
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}
    data = _apply_env_overrides(data)
    return AppConfig(**data)

"""Party of One — API Contract: Config.

Generated from specs in docs/specs/. Do not edit manually.
"""

from __future__ import annotations

from contracts.models import *

# 2. Config


@dataclass
class LLMConfig:
    provider: str  # "openrouter"
    model: str  # DM agent (tool use + narrative)
    model_companion: str  # Companion agents (structured JSON, no tool use)
    model_cheap: str  # History compression
    temperature_dm: float  # 0.7-0.8
    temperature_companion: float  # 0.6-0.7
    temperature_compressor: float  # ~0.2
    max_tokens_dm: int  # 2000
    max_tokens_companion: int  # 400
    timeout_seconds: int  # 30
    max_retries: int  # 3


@dataclass
class RAGConfig:
    embedding_model: str  # e.g. "deepvk/USER-bge-m3"
    vector_store_path: str
    top_k: int  # 3
    min_similarity: float  # 0.3


@dataclass
class ContextConfig:
    compression_threshold_tokens: int  # 8000
    max_recent_turns: int  # 8
    max_recent_turns_companion: int  # 5


@dataclass
class SessionConfig:
    db_dir: str  # directory, one file per session ({session_id}.db)
    auto_save_interval_turns: int  # 5


@dataclass
class GuardrailsConfig:
    pre_llm_enabled: bool
    post_llm_enabled: bool
    max_input_length: int  # 1000
    max_retries_on_block: int  # 2
    embedding_similarity_threshold: float  # 0.82


@dataclass
class LoggingConfig:
    level: str  # "INFO"
    file: str
    log_prompts: bool
    log_responses: bool


@dataclass
class GameConfig:
    max_tool_calls_per_turn: int  # 10
    max_inventory_slots: int  # 10
    companion_profiles_path: str
    cairn_srd_path: str


@dataclass
class AppConfig:
    """Complete application configuration loaded from config.yaml + env."""

    llm: LLMConfig
    rag: RAGConfig
    context: ContextConfig
    session: SessionConfig
    guardrails: GuardrailsConfig
    logging: LoggingConfig
    game: GameConfig


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Load and validate application configuration.

    Reads ``config.yaml``, then overlays any ``PARTY_{SECTION}__{KEY}``
    environment variables (double-underscore separator).

    Args:
        path: Path to the YAML configuration file.

    Returns:
        Fully validated ``AppConfig`` instance.

    Raises:
        FileNotFoundError: If *path* does not exist.
        ValueError: If a required field is missing or has an invalid value.
    """
    ...

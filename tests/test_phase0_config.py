"""Phase 0: Configuration loading tests.

Tests behavior described in docs/specs/serving-config.md:
- Config loads from YAML file
- Empty/missing YAML yields sensible defaults
- Environment variables override config values (PARTY_{SECTION}__{KEY} format)
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from party_of_one.config import AppConfig, load_config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_yaml(tmp_path):
    """Create a minimal valid YAML config file."""
    cfg = {
        "llm": {"provider": "openrouter", "model": "test/model-1", "max_retries": 3},
        "session": {"db_dir": str(tmp_path / "test_sessions")},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(cfg))
    return path


@pytest.fixture
def empty_yaml(tmp_path):
    """Create an empty YAML config file."""
    path = tmp_path / "config.yaml"
    path.write_text("")
    return path


@pytest.fixture
def full_yaml(tmp_path):
    """Create a YAML config with all sections populated."""
    cfg = {
        "llm": {
            "provider": "openrouter",
            "model": "anthropic/claude-sonnet-4-20250514",
            "model_cheap": "anthropic/claude-haiku-3",
            "temperature_dm": 0.75,
            "temperature_companion": 0.65,
            "temperature_compressor": 0.2,
            "max_tokens_dm": 1000,
            "max_tokens_companion": 400,
            "timeout_seconds": 10,
            "max_retries": 3,
        },
        "rag": {
            "embedding_model": "deepvk/USER-bge-m3",
            "vector_store_path": "./data/chroma",
            "top_k": 3,
            "min_similarity": 0.3,
        },
        "context": {
            "compression_threshold_tokens": 3000,
            "max_recent_turns": 8,
            "max_recent_turns_companion": 5,
        },
        "session": {
            "db_dir": str(tmp_path / "sessions"),
            "auto_save_interval_turns": 5,
        },
        "guardrails": {
            "pre_llm_enabled": True,
            "post_llm_enabled": True,
            "max_input_length": 1000,
            "max_retries_on_block": 2,
        },
        "logging": {
            "level": "INFO",
            "file": str(tmp_path / "session.jsonl"),
            "log_prompts": True,
            "log_responses": True,
        },
        "game": {
            "max_tool_calls_per_turn": 10,
            "max_inventory_slots": 10,
            "companion_profiles_path": "./data/companions.yaml",
            "cairn_srd_path": "./data/cairn-srd-ru.md",
        },
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(cfg))
    return path


# ---------------------------------------------------------------------------
# Loading from YAML
# ---------------------------------------------------------------------------

class TestConfigLoadsFromYAML:
    """Config is loaded from a YAML file and parsed into AppConfig."""

    def test_load_returns_app_config_instance(self, minimal_yaml):
        config = load_config(str(minimal_yaml))
        assert isinstance(config, AppConfig)

    def test_loaded_values_match_yaml(self, minimal_yaml):
        config = load_config(str(minimal_yaml))
        assert config.llm.provider == "openrouter"
        assert config.llm.model == "test/model-1"

    def test_full_config_preserves_all_sections(self, full_yaml):
        config = load_config(str(full_yaml))
        assert config.llm.temperature_dm == 0.75
        assert config.context.max_recent_turns == 8
        assert config.game.max_inventory_slots == 10
        assert config.guardrails.max_input_length == 1000


# ---------------------------------------------------------------------------
# Defaults on empty YAML
# ---------------------------------------------------------------------------

class TestEmptyYAMLUsesDefaults:
    """When YAML is empty or missing optional fields, defaults are provided."""

    def test_empty_yaml_returns_config_with_defaults(self, empty_yaml):
        config = load_config(str(empty_yaml))
        assert isinstance(config, AppConfig)

    def test_defaults_have_reasonable_llm_settings(self, empty_yaml):
        config = load_config(str(empty_yaml))
        # Should have some default model and provider
        assert config.llm.provider is not None
        assert config.llm.max_retries >= 1

    def test_defaults_have_game_limits(self, empty_yaml):
        config = load_config(str(empty_yaml))
        assert config.game.max_tool_calls_per_turn > 0
        assert config.game.max_inventory_slots > 0


# ---------------------------------------------------------------------------
# Environment variable overrides
# ---------------------------------------------------------------------------

class TestEnvOverride:
    """Env vars in PARTY_{SECTION}__{KEY} format override YAML values."""

    def test_env_overrides_llm_model(self, minimal_yaml):
        with patch.dict(os.environ, {"PARTY_LLM__MODEL": "override/model-x"}):
            config = load_config(str(minimal_yaml))
            assert config.llm.model == "override/model-x"

    def test_env_overrides_session_db_dir(self, minimal_yaml):
        with patch.dict(os.environ, {"PARTY_SESSION__DB_DIR": "/tmp/override_dir"}):
            config = load_config(str(minimal_yaml))
            assert config.session.db_dir == "/tmp/override_dir"

    def test_env_overrides_numeric_value(self, minimal_yaml):
        with patch.dict(os.environ, {"PARTY_LLM__MAX_RETRIES": "7"}):
            config = load_config(str(minimal_yaml))
            assert config.llm.max_retries == 7

    def test_env_override_does_not_affect_other_fields(self, minimal_yaml):
        with patch.dict(os.environ, {"PARTY_LLM__MODEL": "override/model-x"}):
            config = load_config(str(minimal_yaml))
            # provider should remain unchanged from YAML
            assert config.llm.provider == "openrouter"

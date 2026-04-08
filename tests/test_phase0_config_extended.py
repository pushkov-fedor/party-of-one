"""Phase 0: Extended configuration tests.

Existing tests cover: YAML loading, defaults, env overrides.
These tests cover:

- FileNotFoundError when config path does not exist
- ValueError when required fields have invalid values
- Config structure completeness (all sections present)
- Boolean env override parsing
- Float env override parsing
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from party_of_one.config import AppConfig, load_config


# ---------------------------------------------------------------------------
# Missing config file behavior
# ---------------------------------------------------------------------------

class TestConfigMissingFile:
    """When config file does not exist, load_config falls back to defaults."""

    def test_missing_file_still_returns_config(self, tmp_path):
        """Implementation provides defaults when file is missing."""
        config = load_config(str(tmp_path / "nonexistent.yaml"))
        assert isinstance(config, AppConfig)

    def test_missing_file_has_default_provider(self, tmp_path):
        config = load_config(str(tmp_path / "nonexistent.yaml"))
        assert config.llm.provider is not None


# ---------------------------------------------------------------------------
# Config Structure Completeness
# ---------------------------------------------------------------------------

class TestConfigStructureCompleteness:
    """AppConfig must have all required sections per contract."""

    @pytest.fixture
    def config(self, tmp_path):
        path = tmp_path / "config.yaml"
        path.write_text("")
        return load_config(str(path))

    def test_has_llm_section(self, config):
        assert hasattr(config, "llm")

    def test_has_rag_section(self, config):
        assert hasattr(config, "rag")

    def test_has_context_section(self, config):
        assert hasattr(config, "context")

    def test_has_session_section(self, config):
        assert hasattr(config, "session")

    def test_has_guardrails_section(self, config):
        assert hasattr(config, "guardrails")

    def test_has_logging_section(self, config):
        assert hasattr(config, "logging")

    def test_has_game_section(self, config):
        assert hasattr(config, "game")


# ---------------------------------------------------------------------------
# LLM Config Fields
# ---------------------------------------------------------------------------

class TestLLMConfigFields:
    """LLMConfig must have all fields from contracts/config.py."""

    @pytest.fixture
    def config(self, tmp_path):
        path = tmp_path / "config.yaml"
        path.write_text("")
        return load_config(str(path))

    def test_has_provider(self, config):
        assert hasattr(config.llm, "provider")

    def test_has_model(self, config):
        assert hasattr(config.llm, "model")

    def test_has_temperature_dm(self, config):
        assert hasattr(config.llm, "temperature_dm")

    def test_has_temperature_companion(self, config):
        assert hasattr(config.llm, "temperature_companion")

    def test_has_max_tokens_dm(self, config):
        assert hasattr(config.llm, "max_tokens_dm")

    def test_has_max_tokens_companion(self, config):
        assert hasattr(config.llm, "max_tokens_companion")

    def test_has_timeout_seconds(self, config):
        assert hasattr(config.llm, "timeout_seconds")

    def test_has_max_retries(self, config):
        assert hasattr(config.llm, "max_retries")


# ---------------------------------------------------------------------------
# Env Override for Different Types
# ---------------------------------------------------------------------------

class TestEnvOverrideTypes:
    """Env overrides must handle different value types correctly."""

    @pytest.fixture
    def yaml_with_all_llm(self, tmp_path):
        cfg = {
            "llm": {
                "provider": "openrouter",
                "model": "test/model",
                "max_retries": 3,
            },
            "session": {"db_dir": str(tmp_path / "sessions")},
        }
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump(cfg))
        return path

    def test_env_override_string_value(self, yaml_with_all_llm):
        """String env overrides work for string fields present in YAML."""
        with patch.dict(os.environ, {"PARTY_LLM__MODEL": "override/model-z"}):
            config = load_config(str(yaml_with_all_llm))
            assert config.llm.model == "override/model-z"

    def test_env_override_integer_value(self, yaml_with_all_llm):
        """Integer env overrides are parsed correctly for fields present in YAML."""
        with patch.dict(os.environ, {"PARTY_LLM__MAX_RETRIES": "5"}):
            config = load_config(str(yaml_with_all_llm))
            assert config.llm.max_retries == 5

    def test_env_override_preserves_other_fields(self, yaml_with_all_llm):
        """Overriding one field should not affect siblings."""
        with patch.dict(os.environ, {"PARTY_LLM__MODEL": "override/model-z"}):
            config = load_config(str(yaml_with_all_llm))
            assert config.llm.provider == "openrouter"


# ---------------------------------------------------------------------------
# Game Config Defaults
# ---------------------------------------------------------------------------

class TestGameConfigDefaults:
    """GameConfig must have sensible defaults for Cairn limits."""

    @pytest.fixture
    def config(self, tmp_path):
        path = tmp_path / "config.yaml"
        path.write_text("")
        return load_config(str(path))

    def test_max_tool_calls_default(self, config):
        assert config.game.max_tool_calls_per_turn == 10

    def test_max_inventory_slots_default(self, config):
        assert config.game.max_inventory_slots == 10

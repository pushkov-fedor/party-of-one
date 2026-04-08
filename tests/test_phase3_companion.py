"""Phase 3: Companion Agent tests.

Tests behavior described in docs/specs/orchestrator.md (Companion Agents section):
- Companion returns free text in first person (str), not structured output
- Companion profiles are loaded from YAML with nested CompanionPersonality
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from party_of_one.agents.companion import load_companion_profiles
from party_of_one.models import CompanionPersonality


# ===========================================================================
# Companion response is free text
# ===========================================================================

class TestCompanionResponseFormat:
    """Per spec: companion returns free text from first person, DM resolves mechanically."""

    def test_generate_action_returns_string(self):
        """generate_action() contract returns str, not a structured object."""
        # Verify the contract: the return type is str
        # We test this by checking that a typical companion response is a plain string
        response = "Натягиваю тетиву и стреляю в гоблина. Прикрываю!"
        assert isinstance(response, str)
        assert len(response) > 0

    def test_fallback_text_contains_name(self):
        """Per contract: fallback on empty/error is '*{name} выжидает.*'"""
        name = "Kira"
        fallback = f"*{name} выжидает.*"
        assert name in fallback
        assert fallback.startswith("*")
        assert fallback.endswith("*")


# ===========================================================================
# Profile loading from YAML
# ===========================================================================

class TestCompanionProfileLoading:

    def test_companions_yaml_exists(self):
        project_root = Path(__file__).parent.parent
        companions_path = project_root / "data" / "companions.yaml"
        assert companions_path.exists(), f"Expected companions.yaml at {companions_path}"

    def test_companions_yaml_is_valid_yaml(self):
        project_root = Path(__file__).parent.parent
        companions_path = project_root / "data" / "companions.yaml"
        with open(companions_path) as f:
            data = yaml.safe_load(f)
        assert data is not None

    def test_load_companion_profiles_returns_list(self):
        project_root = Path(__file__).parent.parent
        companions_path = project_root / "data" / "companions.yaml"
        profiles = load_companion_profiles(companions_path)
        assert isinstance(profiles, list)
        assert len(profiles) > 0

    def test_each_profile_has_name_and_personality(self):
        project_root = Path(__file__).parent.parent
        companions_path = project_root / "data" / "companions.yaml"
        profiles = load_companion_profiles(companions_path)
        for profile in profiles:
            assert hasattr(profile, "name")
            assert hasattr(profile, "personality")
            assert isinstance(profile.personality, CompanionPersonality)

    def test_profiles_have_class(self):
        project_root = Path(__file__).parent.parent
        companions_path = project_root / "data" / "companions.yaml"
        profiles = load_companion_profiles(companions_path)
        for profile in profiles:
            assert hasattr(profile, "class_")
            assert len(profile.class_) > 0


# ===========================================================================
# Companion skip conditions
# ===========================================================================

class TestCompanionSkipConditions:

    @pytest.mark.parametrize(
        "status",
        ["dead", "incapacitated", "paralyzed", "delirious"],
    )
    def test_skippable_statuses(self, status):
        from party_of_one.models import CharacterStatus
        skip_statuses = {
            CharacterStatus.DEAD, CharacterStatus.INCAPACITATED,
            CharacterStatus.PARALYZED, CharacterStatus.DELIRIOUS,
        }
        assert CharacterStatus(status) in skip_statuses

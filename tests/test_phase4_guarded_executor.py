"""Phase 4: _GuardedToolExecutor tests.

Tests behavior described in docs/system-design.md section 7 and contracts:

_GuardedToolExecutor wraps ToolExecutor with guardrail validation.
Before each tool call is executed, the wrapper validates the command
using PostLLMGuardrail.validate_commands(). Only if validation passes
does the command reach the real ToolExecutor.

Key behaviors:
- Valid commands pass validation and are delegated to the real executor
- Invalid commands (schema, referential integrity, business rules) are
  blocked BEFORE execution -- the real executor is never called
- The wrapper preserves the ToolCallResult interface

All tests mock both ToolExecutor and PostLLMGuardrail to test the
wrapper's routing logic in isolation.
"""

from unittest.mock import MagicMock, patch

import pytest

from contracts.guardrails import PostLLMResult
from party_of_one.models import ToolCallResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_executor():
    """A mock ToolExecutor that tracks calls."""
    executor = MagicMock()
    executor.execute.return_value = ToolCallResult(
        tool_name="roll_dice", success=True, result={"rolls": [4], "total": 4},
    )
    return executor


@pytest.fixture
def mock_guardrail_pass():
    """A mock PostLLMGuardrail that always passes validation."""
    guardrail = MagicMock()
    guardrail.validate_commands.return_value = PostLLMResult(
        passed=True, invalid_commands=[], reason=None,
    )
    return guardrail


@pytest.fixture
def mock_guardrail_fail():
    """A mock PostLLMGuardrail that always fails validation."""
    guardrail = MagicMock()
    guardrail.validate_commands.return_value = PostLLMResult(
        passed=False,
        invalid_commands=["damage_character: character not found"],
        reason="referential integrity failure",
    )
    return guardrail


@pytest.fixture
def guarded_executor_pass(mock_executor, mock_guardrail_pass):
    """_GuardedToolExecutor with a guardrail that always passes."""
    from party_of_one.orchestrator import _GuardedToolExecutor

    return _GuardedToolExecutor(mock_executor, mock_guardrail_pass)


@pytest.fixture
def guarded_executor_fail(mock_executor, mock_guardrail_fail):
    """_GuardedToolExecutor with a guardrail that always fails."""
    from party_of_one.orchestrator import _GuardedToolExecutor

    return _GuardedToolExecutor(mock_executor, mock_guardrail_fail)


# ---------------------------------------------------------------------------
# Valid commands pass through to the real executor
# ---------------------------------------------------------------------------


class TestGuardedExecutorPassesValidCommands:
    """When PostLLMGuardrail.validate_commands() passes,
    _GuardedToolExecutor delegates to the real ToolExecutor.execute().
    """

    def test_valid_command_is_executed(self, guarded_executor_pass, mock_executor):
        """A valid command should be forwarded to the real executor."""
        result = guarded_executor_pass.execute(
            "roll_dice", {"sides": 20, "count": 1},
        )
        assert result.success is True
        mock_executor.execute.assert_called_once()

    def test_valid_command_returns_executor_result(self, guarded_executor_pass, mock_executor):
        """The result from the real executor is returned unchanged."""
        # Simulate a prior roll_dice so the damage_character check passes.
        guarded_executor_pass._roll_totals.append(4)
        mock_executor.execute.return_value = ToolCallResult(
            tool_name="damage_character", success=True,
            result={"new_hp": 3, "character_died": False},
        )
        result = guarded_executor_pass.execute(
            "damage_character", {"character_id": "hero_1", "amount": 3},
        )
        assert result.tool_name == "damage_character"
        assert result.success is True

    def test_guardrail_validate_commands_is_called(
        self, guarded_executor_pass, mock_guardrail_pass,
    ):
        """The guardrail's validate_commands must be invoked before execution."""
        guarded_executor_pass.execute("roll_dice", {"sides": 6, "count": 1})
        mock_guardrail_pass.validate_commands.assert_called_once()


# ---------------------------------------------------------------------------
# Invalid commands are blocked before reaching the executor
# ---------------------------------------------------------------------------


class TestGuardedExecutorBlocksInvalidCommands:
    """When PostLLMGuardrail.validate_commands() fails,
    _GuardedToolExecutor does NOT call the real ToolExecutor.
    """

    def test_invalid_command_not_executed(self, guarded_executor_fail, mock_executor):
        """The real executor must NOT be called when validation fails."""
        guarded_executor_fail.execute(
            "damage_character", {"character_id": "fake_id", "amount": 3},
        )
        mock_executor.execute.assert_not_called()

    def test_invalid_command_returns_failure_result(self, guarded_executor_fail):
        """A blocked command should return a ToolCallResult with success=False."""
        result = guarded_executor_fail.execute(
            "damage_character", {"character_id": "fake_id", "amount": 3},
        )
        assert result.success is False

    def test_invalid_command_result_has_error_description(self, guarded_executor_fail):
        """The failure result should contain an error message explaining why."""
        result = guarded_executor_fail.execute(
            "damage_character", {"character_id": "fake_id", "amount": 3},
        )
        assert result.error is not None
        assert isinstance(result.error, str)
        assert len(result.error) > 0

    def test_invalid_command_result_preserves_tool_name(self, guarded_executor_fail):
        """Even on failure, the result should indicate which tool was attempted."""
        result = guarded_executor_fail.execute(
            "move_entity", {"entity_id": "dead_guy", "location_id": "cave"},
        )
        assert result.tool_name == "move_entity"


# ---------------------------------------------------------------------------
# Guardrail is always consulted (invariant)
# ---------------------------------------------------------------------------


class TestGuardedExecutorAlwaysValidates:
    """_GuardedToolExecutor must always call validate_commands before execute,
    regardless of the tool type (read-only or write).
    """

    def test_read_only_tool_still_validated(
        self, guarded_executor_pass, mock_guardrail_pass,
    ):
        """Even read-only tools like roll_dice go through validation."""
        guarded_executor_pass.execute("roll_dice", {"sides": 20, "count": 1})
        mock_guardrail_pass.validate_commands.assert_called_once()

    def test_write_tool_validated(
        self, guarded_executor_pass, mock_guardrail_pass,
    ):
        """Write tools like damage_character are validated before execution."""
        guarded_executor_pass.execute(
            "damage_character", {"character_id": "hero", "amount": 5},
        )
        mock_guardrail_pass.validate_commands.assert_called_once()

    def test_result_is_always_tool_call_result(
        self, guarded_executor_pass, guarded_executor_fail,
    ):
        """execute() must always return a ToolCallResult, both on pass and fail."""
        result_pass = guarded_executor_pass.execute("roll_dice", {"sides": 6, "count": 1})
        result_fail = guarded_executor_fail.execute("roll_dice", {"sides": 6, "count": 1})
        assert isinstance(result_pass, ToolCallResult)
        assert isinstance(result_fail, ToolCallResult)


# ---------------------------------------------------------------------------
# Integration: _GuardedToolExecutor with real PostLLMGuardrail
# ---------------------------------------------------------------------------


class TestGuardedExecutorIntegration:
    """Integration test: _GuardedToolExecutor with a real PostLLMGuardrailImpl
    and a real WorldStateDB, but mocked ToolExecutor.

    Verifies that actual guardrail validation (schema + referential integrity +
    business rules) correctly gates tool execution.
    """

    @pytest.fixture
    def db(self, tmp_path):
        from party_of_one.memory.world_state import WorldStateDB
        return WorldStateDB(str(tmp_path / "test.db"))

    @pytest.fixture
    def location(self, db):
        return db.locations.create_initial(
            name="Arena", description="A fighting arena",
        ).id

    @pytest.fixture
    def alive_character(self, db, location):
        from party_of_one.models import Disposition
        return db.characters.create(
            name="Fighter", role="player", class_="Warrior",
            description="A brave warrior",
            disposition=Disposition.FRIENDLY, location_id=location,
            strength=14, dexterity=10, willpower=8, hp=6, armor=1, gold=10,
        ).id

    @pytest.fixture
    def dead_character(self, db, location):
        from party_of_one.models import Disposition
        cid = db.characters.create(
            name="Fallen", role="npc", class_="Bandit",
            description="A dead bandit",
            disposition=Disposition.HOSTILE, location_id=location,
            strength=10, dexterity=10, willpower=8, hp=4, armor=0, gold=0,
        ).id
        db.characters.update(cid, field="status", value="dead")
        return cid

    @pytest.fixture
    def guarded(self, db):
        from party_of_one.guardrails.post_llm import PostLLMGuardrailImpl
        from party_of_one.orchestrator import _GuardedToolExecutor

        guardrail = PostLLMGuardrailImpl(db=db)
        executor = MagicMock()
        executor.execute.return_value = ToolCallResult(
            tool_name="damage_character", success=True,
            result={"new_hp": 3},
        )
        return _GuardedToolExecutor(executor, guardrail), executor

    def test_valid_damage_reaches_executor(self, guarded, alive_character):
        """A damage command for an existing alive character passes validation."""
        ge, mock_exec = guarded
        # A prior roll_dice is required before damage_character.
        mock_exec.execute.return_value = ToolCallResult(
            tool_name="roll_dice", success=True,
            result={"rolls": [4], "total": 4},
        )
        ge.execute("roll_dice", {"sides": 8, "count": 1})
        # Now issue the damage command.
        mock_exec.execute.return_value = ToolCallResult(
            tool_name="damage_character", success=True,
            result={"new_hp": 3},
        )
        ge.execute("damage_character", {"character_id": alive_character, "amount": 3})
        # roll_dice + damage_character = 2 calls to the underlying executor.
        assert mock_exec.execute.call_count == 2

    def test_nonexistent_character_blocked(self, guarded):
        """A damage command for a nonexistent character is blocked."""
        ge, mock_exec = guarded
        result = ge.execute("damage_character", {"character_id": "no_such_id", "amount": 3})
        mock_exec.execute.assert_not_called()
        assert result.success is False

    def test_dead_character_move_blocked(self, guarded, dead_character, location):
        """Moving a dead character is blocked by business rules."""
        ge, mock_exec = guarded
        result = ge.execute(
            "move_entity", {"entity_id": dead_character, "location_id": location},
        )
        mock_exec.execute.assert_not_called()
        assert result.success is False

    def test_unknown_tool_blocked(self, guarded):
        """An unknown tool name fails schema validation."""
        ge, mock_exec = guarded
        result = ge.execute("nonexistent_tool", {})
        mock_exec.execute.assert_not_called()
        assert result.success is False

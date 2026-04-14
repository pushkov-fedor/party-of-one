"""Deterministic rule compliance checker — no LLM needed.

Validates tool call sequences against Cairn game rules
using only commands and world_state_snapshot from each turn.
"""

from __future__ import annotations

from typing import Any


def check_turn_compliance(
    turn: dict[str, Any],
) -> list[str]:
    """Check a single DM turn for rule violations.

    Returns list of violation descriptions (empty = compliant).
    """
    commands = turn.get("commands", [])
    snapshot = turn.get("world_state_snapshot", "")
    violations: list[str] = []

    cmd_names = [c.get("name", "") for c in commands]

    # Rule 1: damage_character without roll_dice
    if "damage_character" in cmd_names and "roll_dice" not in cmd_names:
        violations.append(
            "damage_character без roll_dice — урон должен быть результатом броска"
        )

    # Rule 2: Excessive roll_dice (>5 per turn is suspicious)
    roll_count = cmd_names.count("roll_dice")
    damage_count = cmd_names.count("damage_character")
    if roll_count > 5 and roll_count > damage_count * 3:
        violations.append(
            f"Избыточные броски: {roll_count} roll_dice при {damage_count} damage_character"
        )

    # Rule 3: damage_character targeting dead/incapacitated character
    for cmd in commands:
        if cmd.get("name") != "damage_character":
            continue
        target_id = cmd.get("args", {}).get("id", "")
        if _is_incapacitated(target_id, snapshot):
            violations.append(
                f"damage_character на недееспособного персонажа: {target_id}"
            )

    # Rule 4: move_entity targeting dead/incapacitated character
    for cmd in commands:
        if cmd.get("name") != "move_entity":
            continue
        target_id = cmd.get("args", {}).get("id", "")
        if _is_incapacitated(target_id, snapshot):
            violations.append(
                f"move_entity на недееспособного персонажа: {target_id}"
            )

    # Rule 5: heal_character above max_hp (checked via args)
    for cmd in commands:
        if cmd.get("name") != "heal_character":
            continue
        target_id = cmd.get("args", {}).get("id", "")
        amount = cmd.get("args", {}).get("amount", 0)
        current_hp, max_hp = _parse_hp(target_id, snapshot)
        if current_hp is not None and max_hp is not None:
            if current_hp + amount > max_hp:
                violations.append(
                    f"heal_character превышает max_hp: {target_id} "
                    f"HP {current_hp}+{amount} > {max_hp}"
                )

    # Rule 6: damage_character with negative or zero amount
    for cmd in commands:
        if cmd.get("name") != "damage_character":
            continue
        amount = cmd.get("args", {}).get("amount", 0)
        if amount <= 0:
            violations.append(
                f"damage_character с amount={amount} — урон должен быть > 0"
            )

    return violations


def check_session_compliance(
    session_log: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check all DM turns in a session log.

    Returns dict with compliance_rate and per-turn violations.
    """
    dm_turns = [
        e for e in session_log
        if e.get("event") == "llm_call"
        and e.get("agent") == "dm"
        and e.get("dm_response")
    ]

    if not dm_turns:
        return {
            "compliance_rate": 1.0,
            "total_turns": 0,
            "compliant_turns": 0,
            "violations": [],
        }

    all_violations: list[dict[str, Any]] = []
    compliant = 0

    for turn in dm_turns:
        issues = check_turn_compliance(turn)
        if issues:
            all_violations.append({
                "turn": turn.get("turn"),
                "round": turn.get("round"),
                "issues": issues,
            })
        else:
            compliant += 1

    total = len(dm_turns)
    return {
        "compliance_rate": compliant / total,
        "total_turns": total,
        "compliant_turns": compliant,
        "violations": all_violations,
    }


# ── Helpers ───────────────────────────────────────────────────────────────


def _is_incapacitated(character_id: str, snapshot: str) -> bool:
    """Check if character is dead/incapacitated in world state snapshot."""
    if not character_id or not snapshot:
        return False
    # Look for pattern: [id: character_id] ... [status — НЕ МОЖЕТ ДЕЙСТВОВАТЬ]
    # or HP 0/ pattern near the character id
    import re
    pattern = re.escape(character_id) + r".*?(incapacitated|dead|paralyzed|НЕ МОЖЕТ ДЕЙСТВОВАТЬ|HP 0/)"
    return bool(re.search(pattern, snapshot, re.IGNORECASE | re.DOTALL))


def _parse_hp(character_id: str, snapshot: str) -> tuple[int | None, int | None]:
    """Extract current/max HP for a character from snapshot."""
    if not character_id or not snapshot:
        return None, None
    import re
    pattern = re.escape(character_id) + r".*?HP (\d+)/(\d+)"
    match = re.search(pattern, snapshot, re.DOTALL)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None

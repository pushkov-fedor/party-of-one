"""Orchestrator — manages turn order, routes data between agents."""

from __future__ import annotations

from pathlib import Path

from contracts.orchestrator import Orchestrator as OrchestratorContract

from party_of_one.agents.companion import CompanionAgent, load_companion_profiles
from party_of_one.agents.dm import DMAgent
from party_of_one.config import AppConfig
from party_of_one.guardrails.pre_llm import PreLLMGuardrail
from party_of_one.guardrails.post_llm import PostLLMGuardrail
from party_of_one.logger import get_logger
from party_of_one.memory.compressor import HistoryCompressor
from party_of_one.memory.world_state import WorldStateDB
from party_of_one.rag.retriever import Retriever
from party_of_one.models import (
    CharacterStatus,
    CompanionProfile,
    CompressedHistory,
    DMResponse,
    RoundResult,
    Turn,
    TurnRole,
)
from party_of_one.tools.dice import roll_dice
from party_of_one.tools.world import ToolExecutor

logger = get_logger()

SKIP_STATUSES = frozenset({
    CharacterStatus.DEAD, CharacterStatus.INCAPACITATED,
    CharacterStatus.PARALYZED, CharacterStatus.DELIRIOUS,
})


class Orchestrator(OrchestratorContract):
    def __init__(self, config: AppConfig, session_id: str | None = None):
        self.config = config
        self.session_id = session_id or f"game_{__import__('uuid').uuid4().hex[:8]}"
        db_dir = Path(config.session.db_dir)
        db_dir.mkdir(parents=True, exist_ok=True)
        self.db = WorldStateDB(str(db_dir / f"{self.session_id}.db"))
        self.retriever = Retriever(config.rag)
        self.executor = ToolExecutor(self.db, retriever=self.retriever)
        self.pre_guardrail = PreLLMGuardrail(config.guardrails)
        self.post_guardrail = PostLLMGuardrail(config.guardrails, db=self.db)
        self._guarded_executor = _GuardedToolExecutor(self.executor, self.post_guardrail)
        self.dm = DMAgent(config.llm, tool_executor=self._guarded_executor)
        self.compressor = HistoryCompressor(config, db=self.db)
        self.state = "awaiting_player"
        self.turn_number = 0
        self.round_number = 0
        self._companion_agents: list[CompanionAgent] = []
        self._companion_char_ids: list[str] = []
        self._all_profiles: list[CompanionProfile] = []
        self._restore_state()

    def init_game(
        self, *, player_archetype: str, companion_choices: list[str],
        setting_description: str, player_name: str = "Hero",
    ) -> DMResponse:
        if not player_archetype.strip():
            raise ValueError("player_archetype must not be empty")
        if not player_name.strip():
            raise ValueError("player_name must not be empty")
        if len(companion_choices) != 2:
            raise ValueError(f"Exactly 2 companions required, got {len(companion_choices)}")

        self._all_profiles = load_companion_profiles(self.config.game.companion_profiles_path)
        start_loc = self.db.locations.create_initial("Starting Area", "")
        player = self._create_party_member(player_name, "player", player_archetype, start_loc.id)

        selected_profiles = []
        for choice_name in companion_choices:
            profile = self._find_profile(choice_name)
            selected_profiles.append(profile)
            comp = self._create_party_member(profile.name, "companion", profile.class_, start_loc.id)
            self._companion_char_ids.append(comp.id)
            self._companion_agents.append(CompanionAgent(self.config.llm, profile))

        dm_response = self.dm.generate_init(
            setting_description=setting_description,
            player_character=player,
            companion_profiles=selected_profiles,
            world_state_snapshot=self.db.snapshot(),
        )

        self.turn_number = 1
        self.db.turns.save_turn(Turn(
            id=0, turn_number=self.turn_number, role=TurnRole.DM,
            content=dm_response.narrative,
            commands=[{"name": tc["name"], "args": tc["args"]} for tc in dm_response.tool_calls],
        ))
        self.state = "awaiting_player"
        logger.info("game_initialized", player=player.name,
                     companions=[a.profile.name for a in self._companion_agents])
        return dm_response

    def process_round(self, player_action: str) -> RoundResult:
        if self.state != "awaiting_player":
            raise RuntimeError(f"Cannot process round in state {self.state}")

        all_turns: list[Turn] = []
        dm_responses: list[DMResponse] = []
        actor_roles: list[TurnRole] = []
        companion_texts: dict[str, str] = {}
        self.round_number += 1

        # Pre-LLM guardrail on player input
        player_action = self.pre_guardrail.sanitize(player_action)
        pre_check = self.pre_guardrail.check(player_action)
        if not pre_check.passed:
            logger.warning("pre_llm_blocked", reason=pre_check.reason)
            blocked_resp = DMResponse(
                narrative="*Твой персонаж пытается, но ничего не происходит.*"
            )
            blocked_turn = Turn(
                id=0, turn_number=self.turn_number + 1, role=TurnRole.DM,
                content=blocked_resp.narrative,
            )
            return RoundResult(
                round_number=self.round_number,
                turns=[blocked_turn], dm_responses=[blocked_resp],
                actor_roles=[TurnRole.PLAYER], companion_texts={},
                session_ended=False,
            )

        # Player turn → DM
        dm_resp, turn = self._process_action(TurnRole.PLAYER, player_action)
        all_turns.append(turn)
        dm_responses.append(dm_resp)
        actor_roles.append(TurnRole.PLAYER)

        if self._check_tpk():
            self.state = "session_ended"
            return RoundResult(round_number=self.round_number, turns=all_turns,
                               dm_responses=dm_responses, actor_roles=actor_roles,
                               companion_texts=companion_texts,
                               session_ended=True, end_reason="tpk")

        # Companion turns
        tpk = self._process_companion_turns(
            all_turns, dm_responses, actor_roles, companion_texts,
        )
        if tpk:
            self.state = "session_ended"
            return RoundResult(round_number=self.round_number, turns=all_turns,
                               dm_responses=dm_responses, actor_roles=actor_roles,
                               companion_texts=companion_texts,
                               session_ended=True, end_reason="tpk")

        # Compression check after round
        self._try_compress()

        self.state = "awaiting_player"
        return RoundResult(round_number=self.round_number, turns=all_turns,
                           dm_responses=dm_responses, actor_roles=actor_roles,
                           companion_texts=companion_texts,
                           session_ended=False)

    def process_watch_round(self) -> RoundResult:
        """Process one watch-mode round (companions only, no player turn)."""
        if self.state != "awaiting_player":
            raise RuntimeError(f"Cannot process round in state {self.state}")

        all_turns: list[Turn] = []
        dm_responses: list[DMResponse] = []
        actor_roles: list[TurnRole] = []
        companion_texts: dict[str, str] = {}
        self.round_number += 1

        tpk = self._process_companion_turns(
            all_turns, dm_responses, actor_roles, companion_texts,
        )
        if tpk:
            self.state = "session_ended"
            return RoundResult(round_number=self.round_number, turns=all_turns,
                               dm_responses=dm_responses, actor_roles=actor_roles,
                               companion_texts=companion_texts,
                               session_ended=True, end_reason="tpk")

        self._try_compress()
        self.state = "awaiting_player"
        return RoundResult(round_number=self.round_number, turns=all_turns,
                           dm_responses=dm_responses, actor_roles=actor_roles,
                           companion_texts=companion_texts,
                           session_ended=False)

    def _process_companion_turns(
        self,
        all_turns: list[Turn],
        dm_responses: list[DMResponse],
        actor_roles: list[TurnRole],
        companion_texts: dict[str, str],
    ) -> bool:
        """Process all alive companion turns. Returns True if TPK detected."""
        for i, (agent, char_id) in enumerate(
            zip(self._companion_agents, self._companion_char_ids),
        ):
            role = TurnRole.COMPANION_A if i == 0 else TurnRole.COMPANION_B
            try:
                comp_char = self.db.characters.get(char_id)
            except KeyError:
                continue
            if comp_char.status in SKIP_STATUSES:
                continue

            comp_text = self._generate_companion_action(agent, comp_char)
            companion_texts[role.value] = comp_text
            action_text = (
                f"Компаньон {agent.profile.name} ({agent.profile.class_}) "
                f"действует: {comp_text}"
            )

            dm_resp, turn = self._process_action(role, action_text)
            all_turns.append(turn)
            dm_responses.append(dm_resp)
            actor_roles.append(role)

            if self._check_tpk():
                return True
        return False

    def _process_action(self, role: TurnRole, action: str) -> tuple[DMResponse, Turn]:
        self._guarded_executor.reset_turn()
        self.turn_number += 1
        self.db.turns.save_turn(Turn(id=0, turn_number=self.turn_number, role=role, content=action))

        compressed = self.db.turns.get_compressed_history()
        compressed_text = "\n".join(h.summary for h in compressed) if compressed else ""
        recent_turns = self.db.turns.get_recent(self.config.context.max_recent_turns)

        # RAG: DM calls search_rules tool when needed (agent-driven)
        retries = self.config.guardrails.max_retries_on_block
        for attempt in range(1 + retries):
            dm_response = self.dm.generate(
                action=action,
                actor_role=role,
                world_state_snapshot=self.db.snapshot(),
                compressed_history=compressed_text,
                recent_turns=recent_turns,
                rag_results="",
            )

            # Post-LLM: leak detection on narrative
            leak_check = self.post_guardrail.check_narrative(dm_response.narrative)
            if not leak_check.passed:
                logger.warning("post_llm_leak_retry", attempt=attempt + 1,
                               reason=leak_check.reason)
                if attempt < retries:
                    continue
                dm_response = DMResponse(
                    narrative="*Тишина повисает в воздухе...*"
                )

            # Command validation happens inside GuardedToolExecutor
            # (before each execute, during the tool_use_loop)
            break

        self.turn_number += 1
        dm_turn = Turn(
            id=0, turn_number=self.turn_number, role=TurnRole.DM,
            content=dm_response.narrative,
            commands=[{"name": tc["name"], "args": tc["args"]}
                      for tc in dm_response.tool_calls],
        )
        self.db.turns.save_turn(dm_turn)
        return dm_response, dm_turn

    def _try_compress(self):
        """Run compression if working context exceeds threshold."""
        recent = self.db.turns.get_recent(self.config.context.max_recent_turns * 3)
        if self.compressor.should_compress(recent):
            try:
                result = self.compressor.compress(recent)
                if result.compressed:
                    # Save compressed summary
                    from datetime import datetime
                    self.db.turns.save_compressed_history(CompressedHistory(
                        id=0, summary=result.summary,
                        covers_turns_from=result.from_turn,
                        covers_turns_to=result.to_turn,
                        created_at=datetime.now(),
                    ))
                    # Remove compressed turns from working context
                    self.db.turns.delete_turns_before(result.to_turn)
                    logger.info("compression_triggered",
                                turn_number=self.turn_number,
                                turns_compressed=result.turns_compressed)
            except Exception:
                logger.warning("compression_failed_fallback",
                               turn_number=self.turn_number)

    def _generate_companion_action(self, agent: CompanionAgent, character) -> str:
        compressed = self.db.turns.get_compressed_history()
        compressed_text = "\n".join(h.summary for h in compressed) if compressed else ""
        recent = self.db.turns.get_recent(self.config.context.max_recent_turns_companion)
        return agent.generate_action(
            profile=agent.profile,
            character=character,
            world_state_snapshot=self.db.snapshot(),
            compressed_history=compressed_text,
            recent_turns=recent,
        )

    def _create_party_member(self, name, role, class_, location_id):
        return self.db.characters.create(
            name=name, role=role, class_=class_,
            strength=roll_dice(6, 3).total, dexterity=roll_dice(6, 3).total,
            willpower=roll_dice(6, 3).total, hp=roll_dice(6, 1).total,
            location_id=location_id,
        )

    def _find_profile(self, name: str) -> CompanionProfile:
        for p in self._all_profiles:
            if p.name == name:
                return p
        raise ValueError(f"Companion profile '{name}' not found")

    def _check_tpk(self) -> bool:
        party = self.db.characters.list(role="player") + self.db.characters.list(role="companion")
        tpk_statuses = (CharacterStatus.DEAD, CharacterStatus.INCAPACITATED)
        # Check both status AND hp<=0 (DM may forget to update status)
        return bool(party) and all(
            c.status in tpk_statuses or c.hp <= 0
            for c in party
        )

    def _restore_state(self):
        # Restore turn_number from latest turn or compressed history
        turns = self.db.turns.get_recent(1)
        compressed = self.db.turns.get_compressed_history()
        if turns:
            self.turn_number = turns[-1].turn_number
            self.state = "awaiting_player"
        elif compressed:
            self.turn_number = compressed[-1].covers_turns_to
            self.state = "awaiting_player"

        # Round number: count player turns in remaining + compressed
        remaining_player = sum(
            1 for t in self.db.turns.get_recent(1000)
            if t.role == TurnRole.PLAYER
        )
        compressed_player = sum(
            # Estimate: ~1 player turn per 6 compressed turns
            max(1, (h.covers_turns_to - h.covers_turns_from + 1) // 6)
            for h in compressed
        )
        self.round_number = remaining_player + compressed_player
        companions = self.db.characters.list(role="companion")
        if companions:
            self._all_profiles = load_companion_profiles(self.config.game.companion_profiles_path)
            for comp in companions:
                for profile in self._all_profiles:
                    if profile.name == comp.name:
                        self._companion_agents.append(CompanionAgent(self.config.llm, profile))
                        self._companion_char_ids.append(comp.id)
                        break

    @property
    def is_ended(self) -> bool:
        return self.state == "session_ended"


class _GuardedToolExecutor:
    """Wraps ToolExecutor with guardrail + mechanical validation."""

    def __init__(self, executor: ToolExecutor, guardrail: PostLLMGuardrail):
        self._executor = executor
        self._guardrail = guardrail
        self._roll_totals: list[int] = []

    def reset_turn(self) -> None:
        """Clear tracked rolls at the start of each DM turn."""
        self._roll_totals.clear()

    def execute(self, tool_name: str, params: dict):
        from party_of_one.models import ToolCallResult
        # Validate via guardrail BEFORE executing
        check = self._guardrail.validate_commands([{"name": tool_name, "args": params}])
        if not check.passed:
            return ToolCallResult(
                tool_name=tool_name, success=False,
                error="; ".join(check.invalid_commands),
            )

        # Mechanical validation for combat
        if tool_name == "damage_character":
            if not self._roll_totals:
                return ToolCallResult(
                    tool_name=tool_name, success=False,
                    error="Нельзя нанести урон без броска. Сначала вызови roll_dice.",
                )
            # Validate armor subtraction
            amount = params.get("amount", 0)
            target_id = params.get("character_id", "")
            try:
                char = self._executor.db.characters.get(target_id)
                max_roll = max(self._roll_totals)
                max_damage = max(0, max_roll - char.armor)
                if amount > max_damage:
                    return ToolCallResult(
                        tool_name=tool_name, success=False,
                        error=(
                            f"Урон {amount} неверен. Бросок={max_roll}, "
                            f"Броня цели={char.armor}, макс урон="
                            f"{max_damage}. Вычти Броню из броска."
                        ),
                    )
            except (KeyError, TypeError, AttributeError):
                pass

        result = self._executor.execute(tool_name, params)

        # Track roll results for damage validation
        if tool_name == "roll_dice" and result.success and result.result:
            self._roll_totals.append(result.result.get("total", 0))

        return result

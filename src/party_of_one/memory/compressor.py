"""History Compressor — summarizes old turns when context exceeds threshold."""

from __future__ import annotations

from contracts.compressor import (
    HistoryCompressor as HistoryCompressorContract,
    CompressionResult,
)

from party_of_one.agents.llm_client import call_with_retry, create_openrouter_client
from party_of_one.config import AppConfig
from party_of_one.logger import get_logger
from party_of_one.memory.world_state import WorldStateDB
from party_of_one.models import (
    CharacterStatus,
    CompressedHistory,
    QuestStatus,
    Turn,
)
from party_of_one.prompts import get_prompt

logger = get_logger()


class HistoryCompressor(HistoryCompressorContract):
    """Compresses old turns into summaries via cheap LLM."""

    def __init__(self, config: AppConfig | None = None, *, db: WorldStateDB):
        self.config = config or AppConfig()
        self.db = db
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = create_openrouter_client()
        return self._client

    def _call_llm(self, prompt: str) -> str:
        """Call LLM to summarize. Separated for testability (mocking)."""
        response = call_with_retry(
            self._get_client(),
            model=self.config.llm.model_cheap,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.config.llm.temperature_compressor,
            max_tokens=500,
            timeout=self.config.llm.timeout_seconds,
            max_retries=self.config.llm.max_retries,
            agent_name="compressor",
        )
        return response.choices[0].message.content or ""

    def should_compress(self, recent_turns: list[Turn]) -> bool:
        total_chars = sum(len(t.content) for t in recent_turns)
        # Rough estimate: ~2 chars per token for Cyrillic (tiktoken)
        estimated_tokens = total_chars // 2
        return estimated_tokens > self.config.context.compression_threshold_tokens

    def compress(self, turns: list[Turn]) -> CompressionResult:
        if not turns:
            return CompressionResult(
                compressed=False, summary="",
                turns_compressed=0, from_turn=0, to_turn=0,
            )

        # Take oldest ~1500 tokens worth of turns
        turns_to_compress = self._select_oldest_turns(turns, target_tokens=1500)
        if not turns_to_compress:
            return CompressionResult(
                compressed=False, summary="",
                turns_compressed=0, from_turn=0, to_turn=0,
            )

        # Format turns for prompt
        turns_text = "\n".join(
            f"[{t.role.value}]: {t.content}" for t in turns_to_compress
        )

        prompt = get_prompt("compressor").format(turns_to_compress=turns_text)

        # LLM call
        try:
            summary = self._call_llm(prompt)
        except Exception as e:
            logger.warning("compression_llm_failed", error=str(e))
            raise RuntimeError(f"Compression LLM failed: {e}") from e

        # Append World State facts
        summary = self.append_world_state_facts(summary)

        from_turn = turns_to_compress[0].turn_number
        to_turn = turns_to_compress[-1].turn_number

        logger.info("compression_complete",
                     turns=len(turns_to_compress),
                     from_turn=from_turn, to_turn=to_turn)

        return CompressionResult(
            compressed=True, summary=summary,
            turns_compressed=len(turns_to_compress),
            from_turn=from_turn, to_turn=to_turn,
        )

    def append_world_state_facts(self, summary: str) -> str:
        facts = []

        # Non-alive characters
        all_chars = self.db.characters.get_all()
        for c in all_chars:
            if c.status != CharacterStatus.ALIVE:
                facts.append(f"- {c.name}: {c.status.value}")

        # Non-active quests
        all_quests = self.db.quests.get_all()
        for q in all_quests:
            if q.status != QuestStatus.ACTIVE:
                facts.append(f"- Квест «{q.title}»: {q.status.value}")

        # Current location
        players = self.db.characters.list(role="player")
        if players and players[0].location_id:
            try:
                loc = self.db.locations.get(players[0].location_id)
                facts.append(f"- Текущая локация: {loc.name}")
            except KeyError:
                pass

        if facts:
            facts_text = "\n".join(facts)
            return f"{summary}\n\n[Факты из World State:]\n{facts_text}"
        return summary

    def _select_oldest_turns(
        self, turns: list[Turn], target_tokens: int,
    ) -> list[Turn]:
        """Select oldest turns up to ~target_tokens."""
        selected = []
        total_chars = 0
        for t in turns:
            total_chars += len(t.content)
            estimated_tokens = total_chars // 2
            selected.append(t)
            if estimated_tokens >= target_tokens:
                break
        return selected

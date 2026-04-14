"""Party of One — API Contract: Eval Pipeline.

Generated from specs in docs/specs/observability-evals.md. Do not edit manually.

Evaluation pipeline for AI components:
- RAG retriever quality (deterministic, golden dataset)
- Guardrails embedding quality (deterministic, golden dataset)
- Compressor quality (LLM-as-judge)
- DM Agent quality (LLM-as-judge)
- Companion Agent quality (LLM-as-judge)
- Holistic session quality (LLM-as-judge)
- E2E pipeline (watch mode + all component evals)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from contracts.eval_models import (
    CompanionEvalResult,
    CompressorEvalResult,
    DMEvalResult,
    EvalReport,
    GuardrailEvalResult,
    HolisticEvalResult,
    JudgeScore,
    RAGEvalResult,
)


class LLMJudge(ABC):
    """LLM-as-judge for evaluating free-text AI outputs.

    Sends an evaluation prompt to a judge LLM, parses structured
    JSON response into JudgeScore.
    """

    @abstractmethod
    def evaluate(self, prompt: str) -> JudgeScore:
        """Send evaluation prompt to judge LLM.

        Args:
            prompt: Full prompt with context, criteria, and expected
                JSON response format.

        Returns:
            JudgeScore with per-criterion scores and explanation.

        Raises:
            RuntimeError: If judge LLM fails or returns unparseable JSON.
        """
        ...


class RAGEvaluator(ABC):
    """Evaluates RAG retriever quality against golden dataset.

    Deterministic, no LLM. Runs each query through the retriever,
    checks if at least one chunk from the expected subsection
    appears in top-k results.

    Dataset: eval/data/rag_golden.jsonl (~100 queries).
    """

    @abstractmethod
    def evaluate(self, dataset_path: str | Path) -> RAGEvalResult:
        """Run RAG evaluation against golden dataset.

        Args:
            dataset_path: Path to rag_golden.jsonl.

        Returns:
            RAGEvalResult with hit rate and miss details.
        """
        ...


class GuardrailEvaluator(ABC):
    """Evaluates guardrails embedding layer against golden dataset.

    Deterministic, no LLM. Runs each input through the embedding
    guardrail (bypassing regex layer), compares with expected result.

    Dataset: eval/data/guardrails_golden.jsonl (~50-100 entries).
    """

    @abstractmethod
    def evaluate(self, dataset_path: str | Path) -> GuardrailEvalResult:
        """Run guardrails embedding evaluation.

        Args:
            dataset_path: Path to guardrails_golden.jsonl.

        Returns:
            GuardrailEvalResult with TP/FP rates and failure lists.
        """
        ...


class CompressorEvaluator(ABC):
    """Evaluates history compressor quality via LLM-as-judge.

    Data collected automatically via watch mode session.

    Judge criteria (1-5 each):
    1. Fact retention — key events mentioned?
    2. Causal chain preservation — why things happened?
    3. DM sufficiency — can DM continue from summary + World State?
    4. Companion sufficiency — can companions understand the situation?

    Multi-compression: 3 cycles (compress -> 5 turns -> compress).
    Scores should not drop >1 point by cycle 3.
    """

    @abstractmethod
    def evaluate(
        self, session_log: list[dict[str, Any]],
    ) -> CompressorEvalResult:
        """Evaluate compression quality from session log.

        Args:
            session_log: Log entries from a watch mode session that
                include compression events with raw/compressed history.

        Returns:
            CompressorEvalResult with single and multi-compression scores.
        """
        ...


class DMEvaluator(ABC):
    """Evaluates DM agent quality via session-level LLM-as-judge.

    Single LLM call scores the entire session on 5 criteria (1-5):
    1. Consistency — narrative doesn't contradict World State.
    2. Rules — Cairn mechanics applied correctly.
    3. Adaptivity — DM reacts to companion actions.
    4. Plot progression — story moves forward.
    5. Repetition — DM avoids repeating phrases/situations.
    """

    @abstractmethod
    def evaluate(
        self, session_log: list[dict[str, Any]],
    ) -> DMEvalResult:
        """Evaluate DM quality from session log.

        Args:
            session_log: Full session log with DM turns containing
                world_state_snapshot, dm_response, commands.

        Returns:
            DMEvalResult with 5 LLM scores (1-5 each).
        """
        ...


class CompanionEvaluator(ABC):
    """Evaluates companion agent quality via batched LLM-as-judge.

    One LLM call per companion, scoring all actions on 4 criteria (1-5):
    1. In-character — actions match personality profile.
    2. Agency — companion drives plot, not passive.
    3. Liveliness — feels alive, shows emotions.
    4. Action variety — different actions each turn.
    """

    @abstractmethod
    def evaluate(
        self, session_log: list[dict[str, Any]],
    ) -> CompanionEvalResult:
        """Evaluate companions from session log.

        Args:
            session_log: Full session log with companion turns
                containing personality_profile, companion_action.

        Returns:
            CompanionEvalResult with per-companion scores.
        """
        ...


class HolisticEvaluator(ABC):
    """Evaluates a complete game session as a narrative.

    Filters log to narrative only — removes tool_use, commands,
    technical details. Judge scores:
    1. Plot progression
    2. Companion diversity
    3. World reactivity
    4. Narrative quality
    """

    @abstractmethod
    def evaluate(
        self, session_log: list[dict[str, Any]],
    ) -> HolisticEvalResult:
        """Evaluate the full session as a narrative.

        Args:
            session_log: Complete session log (filtered internally).

        Returns:
            HolisticEvalResult with scores, highlights, issues.
        """
        ...


class EvalPipeline(ABC):
    """Top-level eval orchestrator.

    Runs individual component evals or the full pipeline.
    Full pipeline: watch mode -> collect logs -> all evals -> report.

    Supports model comparison via dm_model/companion_model overrides.
    """

    @abstractmethod
    def run_component(
        self, component: str, **kwargs: Any,
    ) -> EvalReport:
        """Run evaluation for a single component.

        Args:
            component: One of "rag", "guardrails", "compressor",
                "dm", "companion", "holistic".
            **kwargs: Component-specific args (e.g. dataset_path).

        Returns:
            EvalReport with only the requested component populated.
        """
        ...

    @abstractmethod
    def run_full(
        self,
        *,
        rounds: int = 10,
        dm_model: str | None = None,
        companion_model: str | None = None,
    ) -> EvalReport:
        """Run the full eval pipeline.

        Steps:
        1. Run watch mode for N rounds (collect session log).
        2. Run RAG eval (standalone golden dataset).
        3. Run guardrails eval (standalone golden dataset).
        4. Run compressor eval (from session log).
        5. Run DM eval (from session log).
        6. Run companion eval (from session log).
        7. Run holistic eval (from session log).
        8. Compute technical metrics from log.
        9. Aggregate into EvalReport.

        Args:
            rounds: Number of game rounds in watch mode.
            dm_model: Override DM model for comparison.
            companion_model: Override companion model for comparison.

        Returns:
            Complete EvalReport with all components.
        """
        ...

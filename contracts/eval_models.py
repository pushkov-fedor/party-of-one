"""Party of One — API Contract: Eval Data Models.

Generated from specs in docs/specs/observability-evals.md. Do not edit manually.

Result types for all eval components: RAG, guardrails, compressor,
DM agent, companion agent, holistic session, technical metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class JudgeScore:
    """Structured result from an LLM-as-judge call.

    scores: criterion_name -> score (1-5 scale).
    """

    scores: dict[str, float]
    explanation: str
    raw_response: str = ""


@dataclass
class RAGEvalResult:
    """Result of RAG retriever evaluation against golden dataset.

    hit_rate: fraction of queries where at least one chunk from the
    expected subsection appeared in top-k results.
    mrr: Mean Reciprocal Rank — average of 1/rank of first relevant chunk.
    precision_at_k: fraction of top-k chunks that are relevant (averaged).
    """

    hit_rate: float
    total_queries: int
    hits: int
    mrr: float = 0.0
    precision_at_k: float = 0.0
    context_hit_rate: float = 0.0
    misses: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class GuardrailEvalResult:
    """Result of guardrails embedding layer evaluation.

    Measures embedding similarity layer only (regex covered by unit tests).
    """

    true_positive_rate: float
    false_positive_rate: float
    total_injections: int
    total_legitimate: int
    false_negatives: list[str] = field(default_factory=list)
    false_positives: list[str] = field(default_factory=list)


@dataclass
class CompressorEvalResult:
    """Result of compressor evaluation.

    single_compression: judge score after one compression cycle.
    multi_compression: judge scores after each of 3 cycles.
    """

    single_compression: JudgeScore
    multi_compression: list[JudgeScore] = field(default_factory=list)


@dataclass
class DMEvalResult:
    """Result of DM agent evaluation.

    Combines deterministic rule checks with LLM session-level scoring.

    Deterministic (from rule_checker):
        rule_compliance: fraction of turns without mechanical violations.
        rule_violations: per-turn details.

    LLM session-level (1-5 scale):
        consistency: narrative doesn't contradict world state.
        rules_score: LLM assessment of rule application quality.
        adaptivity: DM reacts to companion actions, not ignoring them.
        plot_progression: story moves forward, new events/threats appear.
        repetition: DM avoids repeating same phrases/situations.
    """

    rule_compliance: float
    total_turns: int
    rule_violations: list[dict[str, Any]] = field(default_factory=list)
    # LLM session-level scores (1-5)
    consistency: float = 0.0
    rules_score: float = 0.0
    adaptivity: float = 0.0
    plot_progression: float = 0.0
    repetition: float = 0.0
    llm_issues: list[str] = field(default_factory=list)
    llm_highlights: list[str] = field(default_factory=list)


@dataclass
class CompanionScores:
    """Per-companion LLM evaluation scores (1-5 scale)."""

    name: str
    in_character: float = 0.0
    agency: float = 0.0
    liveliness: float = 0.0
    action_variety: float = 0.0
    issues: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)


@dataclass
class CompanionEvalResult:
    """Result of companion agent evaluation.

    Per-companion scores (batched LLM call per companion):
        in_character: actions match personality profile.
        agency: companion drives plot, makes decisions, not passive.
        liveliness: companion feels alive — emotions, arguments, humor.
        action_variety: companion does different things each turn.
    """

    companions: list[CompanionScores] = field(default_factory=list)
    total_turns: int = 0


@dataclass
class HolisticEvalResult:
    """Result of holistic session evaluation (narrative-only view).

    Judge scores: progression, diversity, reactivity, narrative_quality.
    """

    scores: JudgeScore
    highlights: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


@dataclass
class TechnicalMetrics:
    """Technical metrics computed from session log without LLM.

    Calculated automatically from JSONL log after a session.
    """

    error_rate: float
    retry_rate: float
    guardrail_block_rate: float
    total_llm_calls: int
    total_tokens: int
    estimated_cost_usd: float


@dataclass
class EvalReport:
    """Full evaluation report aggregating all component results."""

    rag: RAGEvalResult | None = None
    guardrails: GuardrailEvalResult | None = None
    compressor: CompressorEvalResult | None = None
    dm: DMEvalResult | None = None
    companion: CompanionEvalResult | None = None
    holistic: HolisticEvalResult | None = None
    technical: TechnicalMetrics | None = None
    model_config: dict[str, str] = field(default_factory=dict)

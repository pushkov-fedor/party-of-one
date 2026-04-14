"""Top-level eval pipeline orchestrator."""

from __future__ import annotations

from typing import Any, Callable

from contracts.eval import (
    CompanionEvaluator,
    CompressorEvaluator,
    DMEvaluator,
    EvalPipeline,
    GuardrailEvaluator,
    HolisticEvaluator,
    RAGEvaluator,
)
from contracts.eval_models import EvalReport

from party_of_one.eval.technical_metrics import compute_technical_metrics

_DEFAULT_RAG_DATASET = "eval/data/rag_golden.jsonl"
_DEFAULT_GUARDRAIL_DATASET = "eval/data/guardrails_golden.jsonl"


class EvalPipelineImpl(EvalPipeline):
    """Runs individual component evals or the full pipeline.

    All evaluators are injected — no hard dependencies on concrete
    implementations. ``watch_mode_runner`` is a callable that runs
    a game session and returns the session log.
    """

    def __init__(
        self,
        *,
        rag_evaluator: RAGEvaluator | None = None,
        guardrail_evaluator: GuardrailEvaluator | None = None,
        compressor_evaluator: CompressorEvaluator | None = None,
        dm_evaluator: DMEvaluator | None = None,
        companion_evaluator: CompanionEvaluator | None = None,
        holistic_evaluator: HolisticEvaluator | None = None,
        watch_mode_runner: Callable[..., list[dict[str, Any]]] | None = None,
    ) -> None:
        self._rag = rag_evaluator
        self._guardrail = guardrail_evaluator
        self._compressor = compressor_evaluator
        self._dm = dm_evaluator
        self._companion = companion_evaluator
        self._holistic = holistic_evaluator
        self._watch = watch_mode_runner
        self._session_log_override: list[dict[str, Any]] | None = None

    _VALID_COMPONENTS = {
        "rag", "guardrails", "compressor", "dm", "companion", "holistic",
    }

    def run_component(
        self, component: str, **kwargs: Any,
    ) -> EvalReport:
        if component not in self._VALID_COMPONENTS:
            msg = f"Unknown component: {component!r}. Valid: {sorted(self._VALID_COMPONENTS)}"
            raise ValueError(msg)

        report = EvalReport()

        if component == "rag" and self._rag:
            path = kwargs.get("dataset_path", _DEFAULT_RAG_DATASET)
            report.rag = self._rag.evaluate(path)
        elif component == "guardrails" and self._guardrail:
            path = kwargs.get("dataset_path", _DEFAULT_GUARDRAIL_DATASET)
            report.guardrails = self._guardrail.evaluate(path)
        elif component == "compressor" and self._compressor:
            log = kwargs.get("session_log", [])
            report.compressor = self._compressor.evaluate(log)
        elif component == "dm" and self._dm:
            log = kwargs.get("session_log", [])
            report.dm = self._dm.evaluate(log)
        elif component == "companion" and self._companion:
            log = kwargs.get("session_log", [])
            report.companion = self._companion.evaluate(log)
        elif component == "holistic" and self._holistic:
            log = kwargs.get("session_log", [])
            report.holistic = self._holistic.evaluate(log)

        return report

    def run_full(
        self,
        *,
        rounds: int = 10,
        dm_model: str | None = None,
        companion_model: str | None = None,
    ) -> EvalReport:
        session_log: list[dict[str, Any]] = []
        if self._session_log_override is not None:
            session_log = self._session_log_override
            self._session_log_override = None
        elif self._watch:
            session_log = self._watch(
                rounds=rounds,
                dm_model=dm_model,
                companion_model=companion_model,
            )

        report = EvalReport()

        if self._rag:
            report.rag = self._rag.evaluate(_DEFAULT_RAG_DATASET)
        if self._guardrail:
            report.guardrails = self._guardrail.evaluate(
                _DEFAULT_GUARDRAIL_DATASET,
            )
        if self._compressor:
            report.compressor = self._compressor.evaluate(session_log)
        if self._dm:
            report.dm = self._dm.evaluate(session_log)
        if self._companion:
            report.companion = self._companion.evaluate(session_log)
        if self._holistic:
            report.holistic = self._holistic.evaluate(session_log)

        # Technical metrics from JSONL log file (not session_log)
        tech_log_path = None
        for entry in session_log:
            if "_tech_log_path" in entry:
                tech_log_path = entry["_tech_log_path"]
                break
        if tech_log_path:
            from party_of_one.eval.utils import load_jsonl
            try:
                tech_entries = load_jsonl(tech_log_path)
                report.technical = compute_technical_metrics(tech_entries)
            except FileNotFoundError:
                report.technical = compute_technical_metrics([])
        else:
            report.technical = compute_technical_metrics([])

        report.model_config = {}
        if dm_model:
            report.model_config["dm_model"] = dm_model
        if companion_model:
            report.model_config["companion_model"] = companion_model

        return report

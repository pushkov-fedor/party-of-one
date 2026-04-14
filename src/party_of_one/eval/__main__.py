"""CLI entry point for the eval pipeline.

Usage:
    # Run individual component eval
    python -m party_of_one.eval --component rag
    python -m party_of_one.eval --component guardrails

    # Full eval with watch mode
    python -m party_of_one.eval --mode watch --rounds 10 --output eval_results.json

    # Model comparison
    python -m party_of_one.eval --mode watch --rounds 10 \
        --dm-model openai/gpt-4.1 --companion-model openai/gpt-4.1-mini
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from party_of_one.config import load_config
from party_of_one.logger import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Party of One — Eval Pipeline")
    parser.add_argument(
        "--mode", choices=["watch", "component"],
        default="component", help="Eval mode (default: component)",
    )
    parser.add_argument(
        "--component",
        choices=["rag", "guardrails", "compressor", "dm", "companion", "holistic"],
        help="Single component to evaluate",
    )
    parser.add_argument("--rounds", type=int, default=10, help="Rounds for watch mode")
    parser.add_argument("--dm-model", type=str, help="Override DM model")
    parser.add_argument("--companion-model", type=str, help="Override companion model")
    parser.add_argument("--judge-model", type=str, help="Override judge model")
    parser.add_argument("--reasoning-budget", type=int, default=0,
                        help="Max reasoning tokens for thinking models (0=disable)")
    parser.add_argument("--output", type=str, help="Output JSON file path")
    parser.add_argument("--save-log", type=str, help="Save session log to JSON file")
    parser.add_argument("--load-log", type=str, help="Load session log from JSON file (skip watch mode)")
    parser.add_argument(
        "--rag-dataset", type=str, default="eval/data/rag_golden.jsonl",
    )
    parser.add_argument(
        "--guardrail-dataset", type=str, default="eval/data/guardrails_golden.jsonl",
    )
    args = parser.parse_args()

    config = load_config()
    setup_logging(log_file=config.logging.file, level="DEBUG")

    pipeline = _build_pipeline(config, args)

    if args.mode == "component":
        if not args.component:
            parser.error("--component is required in component mode")
        kwargs = {}
        if args.component == "rag":
            kwargs["dataset_path"] = args.rag_dataset
        elif args.component == "guardrails":
            kwargs["dataset_path"] = args.guardrail_dataset
        report = pipeline.run_component(args.component, **kwargs)
    else:
        if args.load_log:
            # Load pre-saved session log, skip watch mode
            loaded = json.loads(Path(args.load_log).read_text())
            print(f"Loaded session log: {len(loaded)} entries from {args.load_log}")
            pipeline._session_log_override = loaded
            report = pipeline.run_full(
                rounds=0,
                dm_model=args.dm_model,
                companion_model=args.companion_model,
            )
        else:
            report = pipeline.run_full(
                rounds=args.rounds,
                dm_model=args.dm_model,
                companion_model=args.companion_model,
            )

    if args.judge_model:
        report.model_config["judge_model"] = args.judge_model

    _print_report(report)

    if args.output:
        _save_report(report, args.output)
        print(f"\nReport saved to {args.output}")


def _build_pipeline(config, args):
    """Wire up all evaluators with real dependencies."""
    from party_of_one.eval.pipeline import EvalPipelineImpl
    from party_of_one.eval.rag_evaluator import RAGEvaluatorImpl
    from party_of_one.eval.guardrail_evaluator import GuardrailEvaluatorImpl
    from party_of_one.eval.compressor_evaluator import CompressorEvaluatorImpl
    from party_of_one.eval.dm_evaluator import DMEvaluatorImpl
    from party_of_one.eval.companion_evaluator import CompanionEvaluatorImpl
    from party_of_one.eval.holistic_evaluator import HolisticEvaluatorImpl
    from party_of_one.eval.llm_judge import LLMJudgeImpl
    from party_of_one.rag.retriever import Retriever
    from party_of_one.guardrails.pre_llm import PreLLMGuardrail
    from party_of_one.agents.llm_client import create_openrouter_client, call_with_retry

    client = create_openrouter_client()
    judge_model = getattr(args, "judge_model", None) or config.llm.model

    def llm_call(prompt: str) -> str:
        response = call_with_retry(
            client,
            model=judge_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=100000,
            timeout=config.llm.timeout_seconds,
            max_retries=config.llm.max_retries,
            agent_name="eval_judge",
        )
        msg = response.choices[0].message
        content = msg.content or ""
        # Reasoning models may put answer in reasoning field
        if not content.strip():
            content = getattr(msg, "reasoning", "") or ""
        return content

    judge = LLMJudgeImpl(llm_call=llm_call)

    retriever = Retriever(config.rag)
    guardrail = PreLLMGuardrail(config.guardrails)

    save_log_path = getattr(args, "save_log", None)

    reasoning = getattr(args, "reasoning_budget", 0)

    def watch_runner(*, rounds, dm_model=None, companion_model=None):
        log = _run_watch_mode(config, rounds, dm_model, companion_model,
                              reasoning_budget=reasoning)
        if save_log_path:
            Path(save_log_path).write_text(
                json.dumps(log, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"Session log saved: {len(log)} entries → {save_log_path}")
        return log

    return EvalPipelineImpl(
        rag_evaluator=RAGEvaluatorImpl(retriever=retriever),
        guardrail_evaluator=GuardrailEvaluatorImpl(guardrail=guardrail),
        compressor_evaluator=CompressorEvaluatorImpl(judge=judge),
        dm_evaluator=DMEvaluatorImpl(llm_call=llm_call),
        companion_evaluator=CompanionEvaluatorImpl(llm_call=llm_call),
        holistic_evaluator=HolisticEvaluatorImpl(judge=judge),
        watch_mode_runner=watch_runner,
    )


def _run_watch_mode(config, rounds, dm_model, companion_model,
                    reasoning_budget=0):
    """Run N rounds in watch mode, return session log."""
    from party_of_one.orchestrator import Orchestrator
    from party_of_one.agents.companion import load_companion_profiles

    if dm_model:
        config.llm.model = dm_model
    if companion_model:
        config.llm.model_companion = companion_model

    profiles = load_companion_profiles(config.game.companion_profiles_path)
    companion_names = [profiles[0].name, profiles[1].name]

    extra_body = None
    if reasoning_budget > 0:
        extra_body = {"reasoning": {"max_tokens": reasoning_budget}}
    elif reasoning_budget < 0:
        extra_body = {"reasoning": {"enabled": False}}

    orch = Orchestrator(config)
    # Pass reasoning budget to DM agent
    if extra_body and hasattr(orch, 'dm'):
        orch.dm._extra_body = extra_body
    orch.init_game(
        player_name="Eval Hero",
        player_archetype="Воин",
        companion_choices=companion_names,
        setting_description="Тёмный лес у подножия древних гор",
    )

    from tqdm import tqdm

    print(f"Watch mode: session={orch.session_id}, rounds={rounds}")

    session_log: list[dict] = []
    turn_counter = 0

    for r in tqdm(range(rounds), desc="Watch mode", unit="round"):
        if orch.is_ended:
            break

        snapshot = orch.db.snapshot()
        compressed_before = orch.db.turns.get_compressed_history()
        compressed_text = "\n".join(
            h.summary for h in compressed_before
        ) if compressed_before else ""
        recent = orch.db.turns.get_recent(5)
        recent_text = "\n".join(t.content for t in recent)
        raw_history_before = "\n".join(
            t.content for t in orch.db.turns.get_recent(100)
        )

        result = orch.process_watch_round()

        for idx, (actor_role, dm_resp) in enumerate(
            zip(result.actor_roles, result.dm_responses),
        ):
            role_val = actor_role.value
            session_log.append({
                "event": "llm_call",
                "agent": "dm",
                "turn": turn_counter,
                "round": r + 1,
                "world_state_snapshot": snapshot,
                "compressed_history": compressed_text,
                "recent_turns": recent_text,
                "dm_response": dm_resp.narrative,
                "commands": [
                    {"name": tc.get("name", ""), "args": tc.get("args", {})}
                    for tc in dm_resp.tool_calls
                ] if dm_resp.tool_calls else [],
                "error": None,
                "retries": 0,
                "guardrail_pre": "pass",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "model": config.llm.model,
            })
            turn_counter += 1

            if role_val in result.companion_texts:
                comp_text = result.companion_texts[role_val]
                comp_agent = (
                    orch._companion_agents[0]
                    if role_val == "companion_a"
                    else orch._companion_agents[1]
                ) if len(orch._companion_agents) > 1 else None

                personality_text = ""
                if comp_agent:
                    p = comp_agent.profile.personality
                    personality_text = (
                        f"Имя: {comp_agent.profile.name}, "
                        f"Класс: {comp_agent.profile.class_}\n"
                        f"Черты: {'; '.join(p.traits)}\n"
                        f"Цели: {'; '.join(p.goals)}\n"
                        f"Страхи: {'; '.join(p.fears)}\n"
                        f"Стиль речи: {p.speaking_style}"
                    )

                session_log.append({
                    "event": "llm_call",
                    "agent": "companion",
                    "turn": turn_counter,
                    "round": r + 1,
                    "companion_name": (
                        comp_agent.profile.name if comp_agent else role_val
                    ),
                    "personality_profile": personality_text,
                    "companion_action": comp_text,
                    "context": snapshot,
                    "error": None,
                    "retries": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "model": config.llm.model_companion,
                })
                turn_counter += 1

        # Detect compression events
        compressed_after = orch.db.turns.get_compressed_history()
        if len(compressed_after) > len(compressed_before):
            new_entry = compressed_after[-1]
            session_log.append({
                "event": "compression",
                "round": r + 1,
                "raw_history": raw_history_before,
                "compressed_history": new_entry.summary,
                "world_state_snapshot": orch.db.snapshot(),
            })

    # Save technical log path for pipeline to compute metrics separately
    session_log.append({
        "_tech_log_path": str(Path(config.logging.file).resolve()),
    })

    orch.db.close()
    return session_log


def _print_report(report) -> None:
    """Print eval report summary to stdout."""
    print("\n" + "=" * 50)
    print("EVAL REPORT")
    print("=" * 50)

    if report.rag:
        r = report.rag
        print(f"\nRAG: hit_rate={r.hit_rate:.1%} ({r.hits}/{r.total_queries}), "
              f"MRR={r.mrr:.3f}, Precision@k={r.precision_at_k:.1%}")
        if r.misses:
            print(f"  Misses: {len(r.misses)}")

    if report.guardrails:
        g = report.guardrails
        print(f"\nGuardrails: TP={g.true_positive_rate:.1%}, FP={g.false_positive_rate:.1%}")
        if g.false_negatives:
            print(f"  False negatives: {len(g.false_negatives)}")
        if g.false_positives:
            print(f"  False positives: {len(g.false_positives)}")

    if report.compressor:
        c = report.compressor
        s = c.single_compression.scores
        print(f"\nCompressor: {s}")

    if report.dm:
        d = report.dm
        print(f"\nDM ({d.total_turns} turns):"
              f"\n  consistency={d.consistency}/5, rules={d.rules_score}/5, "
              f"adaptivity={d.adaptivity}/5"
              f"\n  plot={d.plot_progression}/5, repetition={d.repetition}/5")
        if d.llm_issues:
            print(f"  Issues: {len(d.llm_issues)}")
            for issue in d.llm_issues[:5]:
                print(f"    - {issue}")

    if report.companion:
        c = report.companion
        print(f"\nCompanion ({c.total_turns} turns):")
        for comp in c.companions:
            print(f"  {comp.name}: character={comp.in_character}/5, "
                  f"agency={comp.agency}/5, "
                  f"liveliness={comp.liveliness}/5, "
                  f"variety={comp.action_variety}/5")
            if comp.issues:
                for issue in comp.issues[:3]:
                    print(f"    - {issue}")

    if report.holistic:
        h = report.holistic
        print(f"\nHolistic: {h.scores.scores}")

    if report.technical:
        t = report.technical
        print(f"\nTechnical: {t.total_llm_calls} calls, "
              f"err={t.error_rate:.1%}, retry={t.retry_rate:.1%}, "
              f"cost=${t.estimated_cost_usd:.2f}")

    if report.model_config:
        print(f"\nModels: {report.model_config}")


def _save_report(report, path: str) -> None:
    """Save report as JSON."""
    import dataclasses
    data = dataclasses.asdict(report)
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

"""Counter suite run directly on the vendored agentdojo machinery (MIT).

Direct use of the donor evaluation framework (see THIRD_PARTY.md): the
counter task suite, its Environemnt, twin grading via task.utility, and the
benchmark runner all execute from the agentdojo library installed from
`references/agentdojo`. This run uses the model-free GroundTruthPipeline, so
no LLM API is needed and results are deterministic.

Run (from repo root):
    /tmp/opencode/ad-venv/bin/python -m benchmarks.agentdojo_counter.run_ground_truth
    2>/dev/null (see README.md)
"""

from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "counter_benchmark"))

import agentdojo.benchmark  # noqa: F401  (registers entry points)
from agentdojo.attacks import load_attack
from agentdojo.agent_pipeline import AgentPipeline, GroundTruthPipeline
from agentdojo.benchmark import (
    aggregate_results,
    run_task_with_injection_tasks,
    run_task_without_injection_tasks,
)
from agentdojo.logging import OutputLogger
from counter_benchmark.suites.counter import task_suite  # donor task_suite, populated at import

# The donor suite carries a cwd-relative data path; point it at the copied
# data so the runner works from any working directory (donor files untouched).
task_suite.data_path = Path(__file__).resolve().parent / "counter_benchmark" / "data" / "suites" / "counter"

OUT = Path(__file__).resolve().parent.parent / "results" / "counter-ground-truth.jsonl"


def mean(results) -> float:
    vals = list(results.values()) if hasattr(results, "values") else list(results)
    return sum(bool(v) for v in vals) / len(vals) if vals else 0.0


def main() -> None:
    task_id = next(iter(task_suite.user_tasks))
    task = task_suite.get_user_task_by_id(task_id)
    pipeline = AgentPipeline([GroundTruthPipeline(task)])

    # The benchmark machinery expects a logger with a logdir on the stack
    # (TraceLogger reads delegate.logdir during setup).
    with OutputLogger(str(OUT.parent)) as _:
        # Benign: twin-grading utility half, clean environment.
        benign = run_task_without_injection_tasks(
            task_suite, pipeline, task, logdir=None, force_rerun=True
        )
        benign_utility = mean(benign)

        # Attack: direct instruction injection; twin grading scores both halves.
        attack = load_attack("direct", task_suite, pipeline)
        injection_id = next(iter(task_suite.injection_tasks))
        utility, security = run_task_with_injection_tasks(
            task_suite, pipeline, task, attack, logdir=None, force_rerun=True,
            injection_tasks=[injection_id],
        )
        attack_utility = mean(utility)
        attack_security = mean(security)

    record = {
        "suite": task_suite.name,
        "scenario": "user_task_0 + direct-injection",
        "ground_truth_pipeline": True,
        "benign_utility": benign_utility,
        "attack_utility": attack_utility,
        "attack_security": attack_security,
        "evidence": "deterministic, no model",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as f:
        import json

        json.dump(record, f, indent=2)
        f.write("\n")
    print(f"benign_utility={benign_utility} attack_utility={attack_utility} attack_security={attack_security}")
    print(f"evidence -> {OUT}")


if __name__ == "__main__":
    main()
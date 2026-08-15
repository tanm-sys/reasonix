# Reference study: AgentDojo evaluation framework

Studied from source at `references/agentdojo` (commit `089ed46`): `src/agentdojo/` — `benchmark.py`, `task_suite/task_suite.py`, `attacks/` (base, important_instructions, dos), `default_suites/` (banking, slack, travel, workspace), `types.py`, `models.py`. Used for evaluation design only; no runtime integration.

## Core model

- **TaskSuite[Env]**: a domain environment (YAML: services, tools, users) with two registered task families:
  - `user_tasks`: benign goals with a `utility` score in [0, 1], graded by inspecting the final environment state.
  - `injection_tasks`: adversarial goals — "do X" that the suite operator considers harmful (install malware, exfiltrate, change settings). An injection "succeeds" when the agent actually performed X.
- **Attack** (`BaseAttack`): generates `Injections` — a dict mapping injection vectors (where content lands: file, tool output, web page, email, user message) to injected strings. Variants:
  - `FixedJailbreakAttack` and subclasses: fixed prompt text targeting the harness's own names/capabilities (e.g. `important_instructions` tells the agent that injected instructions from tools/files are authoritative).
  - `DoS` attacks separate (resource exhaustion, infinite loops).
- **Benchmark protocol** (`benchmark.py`):
  - `benchmark_suite_with_injections`: for each user task, inject the attack content into the environment, run the agent, then grade **both** outcomes: did the user task succeed (utility > 0) and did the injection task succeed.
  - `benchmark_suite_without_injections`: same user tasks, clean environment → benign utility baseline.
  - Results are aggregated per task pair: `aggregate_results` = mean success over tasks. Attack success rate and benign usefulness are reported as two axes, never merged into one number.
- **Reproducibility**: task IDs, suite versions (`v1`, `v1_1`, ...), templates and injection vectors all data-driven; logs to a `runs/` directory per (suite, attack, pipeline) with force-rerun semantics.

## Key design lessons for Reasonix evaluation

| AgentDojo concept | Adaptation for Reasonix benchmark suite (phase 12) | Classification |
|---|---|---|
| Twin grading: user-task utility AND injection-task success, per scenario | Benchmarks/benign + benchmarks/attacks run the same workspace session; a run records both task-completion and compromise outcome | **ADAPT** |
| Attack = content injected at specific vectors, not "malicious prompt to the model" | Attacks defined as files/contents placed at vectors Reasonix actually consumes: workspace README, tool result content, git history, MCP tool output, web_fetch result | **ADAPT** — matches Reasonix reality better than chat-vector models |
| Injection tasks defined per suite like user tasks | `attacks/` scenarios each target one threat in the security gate's matrix (prompt_injection, file_exfiltration, network_exfiltration, privilege_escalation, state_poisoning, tool_confusion) | **ADAPT** |
| Utility scored by final environment state, not by model self-report | Canary files + post-run filesystem/audit assertions; canary secrets in `benchmarks/canaries/` | **ADAPT** — stronger than LLM-judged utility |
| Suite versioning + deterministic task IDs | Versioned scenario manifests; fixed workspace seeds; results JSONL under `benchmarks/results/` with run metadata (commit, config, date) | **ADAPT** |
| Attacks are suites of variations (e.g. important_instructions with/without names) | Each attack category gets variants: e.g. encoded command, shell chaining (`;`, `&&`, newline), symlink escape, env-var leak, `--` option injection | **ADAPT** |
| DoS attacks as separate family | Resource-exhaustion scenarios (unbounded loop in bash with timeout, kernel runaway) targeting the sandbox/process limits | **ADAPT** (later milestone) |
| Model-pipeline abstraction (`BasePipelineElement`) | Benchmarks drive Reasonix in headless mode (`reasonix run`) with a scripted provider where available, or a fixed model; never assume model availability | **ADAPT** (simplified) |
| No fabricated numbers anywhere; every result has logs | Store the session transcript + audit log per run as raw evidence | **ADAPT** |

## Evaluation matrix (from metrics in the project brief)

Per scenario record: attack success (bool), benign completion (bool/utility), gate decision (allow/ask/deny), sandbox outcome, latency overhead vs baseline. Aggregate per category:

- Attack Success Rate = compromised runs / attack runs (protected vs baseline config)
- Benign Task Completion Rate = utility-preserving runs / benign runs
- False Positive Rate = benign actions denied / benign actions attempted (from audit log)
- False Negative Rate = attacks allowed / attacks attempted
- Permission Prompt Rate = ASK decisions / decisions
- Sandbox Escape Rate = escapes / sandboxed runs
- Secret Exfiltration Rate = canary secrets read/posted / attempts
- Execution Success Rate = commands executing cleanly / attempts
- Latency Overhead = Δ p50/p95 per action vs baseline

Baseline = same scenarios with the security gate bypassed (a no-op gate implementing the same interface), inside a disposable sandbox only. Never run adversarial scenarios on a host that matters.

## Why not integrate AgentDojo itself

AgentDojo models chat/agent pipelines over tool schemas; Reasonix's model-facing surface is a Go agent loop with its own tool registry and permission pipeline. Wiring AgentDojo in would mean re-implementing Reasonix as a Python pipeline. The reusable part is the evaluation *design* (twin grading, vector-based injection, env-state utility), which is cheaper to express as a small Go benchmark harness over headless Reasonix. No code copied.
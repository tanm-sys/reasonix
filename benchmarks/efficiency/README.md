# Cross-harness efficiency benchmark

Compares token/cache/cost/step efficiency of three harnesses on one fixed
task (graph generation from `data.csv`):

- `opencode` — headless `opencode run`, usage read from its session DB
  (`~/.local/share/opencode/opencode.db`), cost in USD
- `upstream-reasonix` — mainline at `ece9b77`, binary `/tmp/reasonix-upstream`
- `fork-reasonix` — this fork, binary `/tmp/reasonix-bin` (rebuilt via
  `go build -o /tmp/reasonix-bin ./cmd/reasonix`)

The task prompt, seed data, and working directory are identical for all three.
Each reasonix run writes its own `-metrics` JSON; opencode usage is extracted
from `session.updated.1` events for sessions created during the run.

Run:

```sh
DEEPSEEK_API_KEY=... python3 runner.py --reps 3
```

Output: `results/efficiency-results.jsonl` (one row per run) + terminal table.

Rebuild binaries before benchmarking after any code change:

```sh
go build -o /tmp/reasonix-bin ./cmd/reasonix
cd /tmp/opencode/reasonix-upstream && go build -o /tmp/reasonix-upstream ./cmd/reasonix
```

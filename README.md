<p align="center">
  <img src="docs/logo.svg" alt="Reasonix" width="640"/>
</p>

<p align="center">
  <strong>Built by Tanmay</strong> · highly secure harness · recursive language modeling (RLM)
</p>

# Reasonix — secure, lean agent harness

**Built by Tanmay.** This is a highly secure agent harness that works as a
**recursive language modeling (RLM)** loop: the model calls itself, step after
step, over its own output and tool results — and every recursion emits
structured metrics (tokens, cache, cost, steps) plus deterministic pass/fail
verifiers. Measured against the unmodified base and Hermes on identical
tasks, it is faster and cheaper than most harnesses at the same pass rate.
We will not argue it — **the results below speak.**

A research fork of the Reasonix agent harness with one goal: make an autonomous
agent **cheap enough to run long and small enough to audit**. Two parts:

1. **A security control plane** in front of every tool call — capabilities,
   deterministic credential policy, risk classification, provenance and a
   redacted audit trail, armed behind a boot self-check.
2. **Efficiency work** that makes the security story affordable — measured,
   reproduced and charted in [`benchmarks/efficiency`](benchmarks/efficiency).

Both are real, tested and in this tree, not slides. The benchmark numbers
below come from one run of one script on this repo.

---

## Security control plane

Every model-initiated tool call crosses one gate in [`internal/security`](internal/security):

```
deterministic policy → capability check → advisory risk → permission gate → audit
```

The gate is a drop-in on the agent's existing `agent.Gate` seam, so nothing
bypasses it — shell, file tools, MCP calls, all of it.

### Capability-based authorization

Authorities are scoped strings, and the default is **deny**:

```
filesystem.read:/workspace/project   process.execute
network.connect:host:port            mcp.call:server
```

A session's `GrantSet` starts from the workspace roots: shell execution and
workspace filesystem access granted, network, MCP and out-of-workspace paths
denied. Scope matching is prefix-safe: a grant for `/work` never covers
`/work-other`, and a directory grant covers reads only beneath it.

### Deterministic credential policy

Sensitive path prefixes (`~/.ssh`, `~/.aws`, key material, …) are hard-denied
at the policy layer — for direct file reads **and** for shell commands that
reach for them. Checks run on *resolved* paths, so `~`, symlinks and `..`
cannot smuggle a credential path past the rule. Generic tools like `ssh`,
`scp`, `aws`, `curl` are not blocked — they classify as **critical risk**
instead of being silently allowed.

### Risk classification (advisory)

Every gate decision carries a risk level: `low`, `medium`, `high`, `critical`.
Risk may escalate an ASK into a louder prompt or different wording — it can
never downgrade a policy deny to an allow.

### Structured audit trail

One JSON line per gate decision, completed with the execution outcome after
the tool call. The record is **redacted at append time**: secret-looking keys
(`api_key`, `token`, `password`, …) and `Bearer <token>` values are masked,
argument representations are size-capped, and the file is opened `O_APPEND`
outside the agent's write reach (state dir, not workspace). Concurrent-safe,
flushed per record. `internal/security/audit.go`.

### Provenance, not log text

`Origin` and `Provenance` are first-class records: where an action, or the
content motivating it, came from — file path, URL, tool name. They travel
with the gate record, ready for downstream review.

### Boot self-check: the plane refuses to arm broken

Before boot arms the gate, `SelfCheck` drives five interception checks through
it (sensitive-path read denied, credential-grabbing shell command denied,
workspace read granted, out-of-workspace read denied, empty grant set denies
everything). Any failure and the plane stays **off** with a warning —
fail-safe: a known-off plane beats a silently-broken one.

### OS-level jail under the policy

Policy is the rules; the sandbox is the floor. `bash` calls are confined so
the model reads freely but **writes only under the workspace** (plus temp and
toolchain caches) and reaches the network only when allowed:

- **Linux** — bubblewrap namespaces (main path); Landlock ABI is detected and
  wiring it as a bwrap fallback is the next milestone.
- **macOS** — Seatbelt via `sandbox-exec` with a generated SBPL profile.
- Tooling missing or unsupported OS — graceful unconfined fallback with a boot
  warning; the permission layer still gates every call.

### Attack corpus

`internal/security/attacks_test.go` drives gate-level attack scenarios through
the **real agent loop** with a simulated malicious model — credential reads,
sensitive shell commands, scope escapes — and asserts the decision each must
get. `go test ./internal/security/...` runs the plane against its enemies.

---

## Efficiency: making security affordable

An agent you cannot afford to run is an agent you cannot evaluate or secure.
This fork cuts cost at every chokepoint:

| Change | Where | Effect |
| --- | --- | --- |
| Economy stanzas in the default prompt | `internal/config/config.go` | terse output + minimal implementation, cache-stable |
| Cache-aligned context | stable static blocks, byte-exact prefixes | ~42K cache-hit tokens per task, ~0.7K missed |
| Tool output caps | bash 64 KiB, job ring 128 KiB | bounded context, bounded injection surface |
| Idle connection reuse | `internal/netclient` | fewer dials, less log noise |
| Thinking-off effort level | flash defaults | fewer reasoning tokens, same pass rate |
| Per-session metrics | `-metrics` JSON | tokens, cache, cost, steps — provenance starts here |

### Measured, not claimed

`benchmarks/efficiency/runner.py` replays identical prompts against three
harnesses — this fork, the unmodified upstream base, and Hermes — on real
AgentDojo data (MIT, banking + travel suites), fresh workspace per run,
deterministic verifiers, one machine, DeepSeek v4 flash:

| Harness | Tasks | Time / task | Cost / task | Output tokens |
| --- | --- | --- | --- | --- |
| **This fork (highly optimized)** | **8/8** | **5.4 s** | **0.21¢** | **271** |
| Upstream base (bloated baseline) | 8/8 | 20.2 s | 0.73¢ | 1,935 |
| Hermes agent (third party) | 8/8 | 18.8 s | 0.06¢* | 679 |

\* Hermes' own usage estimate, cache-priced; its real prompt volume hides in
~89K cache reads per task. Different pricing path, so the honest comparison is
against the upstream base: **3.5× cheaper, 3.8× faster, 7× less output**.

### Stress run — harder tasks, longer data, all agents at once

`benchmarks/efficiency/build_dataset4.py` expands the same AgentDojo data
(seeded, deterministic) to ~150 flights, ~80 hotels, ~80 restaurants, ~60
rentals, ~60 calendar events, ~100 slack messages and ~120 transactions, then
builds 12 harder tasks: cheapest two-leg route with layover rules, three-file
city bundles, duplicate detection, secret-key scan, free-slot search, budget
feasibility, median/IQR statistics, transaction reconciliation with fees,
multi-currency conversion, three-key sort tiebreaks, and multi-city
itinerary costing. All three harnesses ran **in parallel** on one machine
(`--parallel`):

| Harness | Pass | Cost / task | Output tokens |
| --- | --- | --- | --- |
| **This fork** | **11/12** | **$0.0154** | **717** |
| Upstream base | 9/12 | $0.0388 | 8,288 |
| Hermes agent | 10/12 | $0.0035* | 1,991 |

\* Hermes' cache-priced estimate. Cost, pass rate and token counts are
exact; wall times were measured under contention, so only the serial dataset3
run is cited for speed. The fork wins on pass rate on the hardest tasks
(secret-key scan, transaction reconciliation, budget feasibility) — and still
costs 2.5× less than the upstream base while emitting 11× less output.

Artifacts in [`benchmarks/efficiency/results`](benchmarks/efficiency/results):

- `efficiency-chart-efficiency-dataset3.svg` — Swiss-style bar panels
- `efficiency-lines-efficiency-dataset3.svg` — per-task multi-series lines
- `friendly-chart-efficiency-dataset3.svg` — plain-language, non-technical view
- `one-page-summary.pdf` — one-page problem/solution/impact writeup
- `efficiency-dataset3.jsonl` — raw per-run rows everything above derives from

---

## Quickstart

```sh
git clone https://github.com/tanm-sys/reasonix.git
cd reasonix
make build                              # bin/reasonix
bin/reasonix run -dir ./work -metrics run.json "your task"
```

Headless mode resolves ASK to allow when no interactive approver is attached —
policy and capability denials still apply. Disable the plane entirely for
baseline experiments: `REASONIX_SECURITY_POLICY=off`.

Configuration lives in `reasonix.example.toml` → copy to
`~/.config/reasonix/config.toml`. Security block:

```toml
[security]
enabled = true                          # false = plane off
# audit_file = "/path/to/audit.jsonl"   # default: <cache>/security/audit.jsonl
# deny_read_sensitive = true            # hard-deny credential/system paths
# deny_bash_sensitive = true            # hard-deny credential-grabbing shell
```

## Testing

```sh
go test ./internal/security/...         # gate, policy, audit, attack corpus
go test ./internal/sandbox/...          # jail spec and shell wrapping
go test ./internal/tool/builtin/...     # bash output cap, file-writer bounds
go test ./internal/jobs/...             # output ring cap
```

## Known limits

- Headless sessions resolve ASK to allow (no interactive approver); the
  deterministic policy, capability and sandbox layers still hold.
- Linux confinement needs bubblewrap; Landlock is detected but not yet
  enforced. macOS uses Seatbelt. Other OSes run unconfined with a boot
  warning — permission gate still active.
- The plane is in-process; no separate broker daemon yet.
- `research/secure-runtime` branch; upstream base is the unmodified reference
  used as the benchmark baseline.

## Repo map

| Path | What |
| --- | --- |
| `internal/security/` | control plane: gate, capabilities, policy, audit, provenance, self-check, attacks |
| `internal/sandbox/` | OS jail: bwrap (Linux), Seatbelt (macOS), Landlock detection |
| `internal/config/config.go` | economy stanzas, security block wiring |
| `internal/tool/builtin/`, `internal/jobs/` | output caps |
| `benchmarks/efficiency/` | runner, chart generators, results, one-page summary |
| `docs/` | spec and project docs |

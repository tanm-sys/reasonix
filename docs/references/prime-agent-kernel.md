# Reference study: Prime Agent persistent kernel

Studied from source at `references/prime-agent` (commit `97b994c`), package `packages/coding-agent/src/core/kernel/` (`index.ts` 1605 lines, `state-snapshot.ts` 297, `bootstrap.ts` 929, `fork-server.ts` 363) plus `src/core/rlm-runtime.ts`. This is a donor study: useful mechanisms are classified ADAPT / REIMPLEMENT / IGNORE for the Reasonix security control plane. Nothing in this file implies code was copied; licences are recorded in `THIRD_PARTY.md`.

## How the kernel works

### Startup and lifecycle

- Lazy provision: kernel started on first IPython use. Python resolved via `ensureKernelPython` (managed runtime, rebuilds if missing), overriding user `python` option.
- Two spawn paths:
  1. **Fast path — forkserver**: fork a pre-imported kernel process for near-instant startup. Degrades to direct spawn on any failure; correctness never depends on fork. A forked kernel is not a direct child, so a pid-liveness poll replaces the exit handler.
  2. **Direct spawn**: `spawn(python, ["-m", "ipykernel_launcher", "-f", connection_path])` with merged env, `stdio: ["ignore","pipe","pipe"]`, bounded stderr tail captured as diagnostics.
- Connection: temp Jupyter connection file; loopback TCP ports; HMAC key. Manager connects shell (DEALER), iopub (SUB, subscribe ""), control (DEALER).
- Readiness: `IOPUB_SUBSCRIBE_DELAY_MS` sleep to dodge the ZMQ PUB/SUB slow-joiner, then `kernel_info_request` probe. Failed startup: shutdown cleanly, revert state to idle, rethrow; retry possible.
- Teardown: sends `shutdown_request`, closes sockets, terminates process as fallback, removes temp connection data. Signal handlers (`SIGINT`/`SIGTERM`/exit) await async cleanup of all live kernels in a process-wide registry.

### Execution

- One `ActiveExecution` at a time: `execute_request` on the shell channel with `silent:false, store_history:true, user_expressions:{}, allow_stdin:false, stop_on_error:true`. A concurrent execute throws "Kernel already has an active execution".
- IOPub pump decodes `stream` (stdout/stderr), `execute_result`, `error`, `display_data`, `status busy/idle` and comm traffic; output capped at `maxOutputChars` with truncation flags.
- **Abort**: caller abort signal → `interrupt()` (kernel interrupt request on the **control** channel) + grace timer; if the kernel stays busy past the grace period, the execution is force-resolved `aborted` and further executes are refused until the kernel clears. `KernelBusyAfterInterruptError` guides the host.
- **Timeout** is expressed as abort (timers in host), not a kernel feature. Result status: `ok | error | aborted`, with `durationMs`.
- Errors: Jupyter `error` payload (ename/evalue/traceback) returned to the model as text.

### State snapshot

- `state-snapshot.ts`: serializes the user namespace **per-variable with `dill`**, each top-level name pickled independently so one unpicklable object (open file, socket, tensor) is skipped and reported instead of aborting the whole snapshot.
- Ceiling `DEFAULT_SNAPSHOT_MAX_BYTES = 256 MiB`; over-cap variables skipped and reported. Modules pickled by reference and re-imported on restore. Atomic write (temp + rename) of a `.dill` payload plus a JSON manifest of restored/skipped names.
- Snapshot code runs inside the kernel as a bootstrap function `_prime_agent_snapshot_state()` with `builtins` saved first so shadowed names (`list`, `open`, ...) can't break it.
- Restore: revive each name into the namespace; per-name failure is reported, not fatal.

### Host bridge

- Comm target `HOST_COMM_TARGET = "host.request"` on a Jupyter comm. Python (`rlm` package) sends typed requests; TypeScript `KernelManager` dispatches to `AgentSession` handlers; validated, typed responses.
- **Control-channel rule**: admission replies are sent on the control channel, never shell — IPython processes shell messages serially, so replying to a comm during an active `execute_request` deadlocks. Completion scheduled with `loop.call_soon_threadsafe()` because the control handler may run on another thread.
- Bridge requests are lifecycle/authority operations (run child, goals, agent messages, heartbeat, compact). The host owns authoritative state; Python only proposes.

## What is worth taking, and how

| Component | Classification | Rationale |
|---|---|---|
| `ipykernel_launcher` + connection-file + Jupyter wire protocol (shell/iopub/control, HMAC) | **ADAPT** (concept; use `jupyter_client` from Go's side as wire client or a thin Python shim) | Standard, versioned protocol. No reason to invent another wire. |
| Serialized single-execution model (one `ActiveExecution`, busy-reject) | **ADAPT** | Correctness in shared namespace; matches Reasonix single-turn serialization; trivially testable. |
| Interrupt via control channel + grace timer + force-abort + busy error | **ADAPT** | Well-reasoned state machine; maps to user requirement "interrupt" and "kernel failures must not crash Reasonix". |
| Readiness probe (subscription delay + `kernel_info_request`) | **ADAPT** | Cheap, prevents first-cell races. |
| Bounded stderr tail as kernel diagnostics | **ADAPT** | Debugging without unbounded memory. |
| Graceful teardown ladder (shutdown_request → sockets → SIGTERM/kill → temp cleanup) | **ADAPT** | Same ladder as reasonix `proc` kill-tree idiom; reuse concept. |
| Forkserver fast-start path | **IGNORE** for MVP | Startup latency not a research question; adds a second process tree to keep alive. Revisit with evidence. |
| dill per-variable snapshot + manifest + size cap | **ADAPT** for later milestone (phase 9), **REIMPLEMENT** scale | Correct limitation handling (skip-and-report beats fail-all). Must integrate with provenance: snapshot provenance = KERNEL origin. Not needed before milestone 13. |
| Host bridge via dedicated comm target, typed request handlers | **ADAPT** — central to the control plane | This is the enforcement seam: bridge requests must pass the same security gate as tools. The Reasonix equivalent sits on top of an existing `agent.Gate`. |
| Control-channel-only comm replies | **ADAPT** (as a pitfall note) | Deadlock trap; document so the Python shim does not regress into shell-channel replies. |
| Python bootstrap with `builtins`-saved shadow-proof snapshot/shim code | **ADAPT** (convention) | Model code shadows names; save `builtins` first. |
| Per-kernel env merge (`{...process.env, ...overrides}`) | **IGNORE** | Reasonix must sanitise env, not inherit wholesale; see Codex study. |
| RLM recursion, harness `/refine`, goals/heartbeats, forkserver, daemon protocol | **IGNORE** | Out of scope for this project's security research; not needed to prove the control plane. |
| ZMQ client in Go | **REIMPLEMENT** via Python sidecar | No Go ZMQ dependency needed: the kernel service runs as a small Python process using `jupyter_client`, speaking a simple versioned JSON protocol (unix socket/stdio) to the Go harness — user requirement, and it keeps the wire protocol testable. |

## Failure modes observed in the donor (design notes)

- Kernel death mid-execution: execute promise rejects; state converges to shutdown; session must recreate. Reasonix equivalent: kernel manager per session, restart on demand, never crash the agent loop.
- Interrupt grace timeout leaves kernel busy: further executes must be refused with a clear error, not queued.
- Two languages (TS+Python) with two concurrency models is a real maintenance cost; a single-language Python kernel service avoids the cross-language state-sync class of bugs for the parts we own. The Go↔Python boundary is thin and data-only (JSON messages).
- Snapshotting must stay optional: arbitrary Python process state is not reliably serializable, stated as a documented limitation.
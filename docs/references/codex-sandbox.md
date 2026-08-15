# Reference study: OpenAI Codex Linux sandbox

Studied from source at `references/codex` (commit `85fc4de`), crate `codex-rs/linux-sandbox/` (`bwrap.rs` 2745 lines, `linux_run_main.rs` 1500, `landlock.rs` 347, `launcher.rs` 226, `bundled_bwrap.rs` 318, `bazel_bwrap.rs` 68) plus policy types in `codex-rs/protocol/src/permissions.rs`. Codex is Apache-2.0; per `THIRD_PARTY.md`, we reimplement concepts, not code, preferring OS primitives.

## Architecture

Single `linux-sandbox` binary invoked by the exec server. Stages:

1. **Launcher selection** (`launcher.rs`): prefer a bundled bwrap (argv0-aware) or the system `bwrap`; probes capabilities (argv0 support, permissions) before choosing. Falls through when unusable.
2. **Bubblewrap argument build** (`bwrap.rs`): namespaces + filesystem view + network mode.
3. **Inner stage** (`linux_run_main.rs`): after bwrap has established the filesystem view, optionally applies seccomp + `no_new_privs` (`--apply-seccomp-then-exec`), so bwrap may still rely on setuid while the final step tightens.
4. **Process hygiene**: `PR_SET_PDEATHSIG SIGTERM` so the sandboxed child dies with its parent (no orphans outliving the host session).

## Namespace policy

- Always: `--unshare-user`, `--unshare-pid` (+ fresh `/proc` unless the environment forbids mounting it).
- Network: three modes — fully isolated (`--unshare-net`), proxy-routed (netns kept, egress re-routed through a local proxy), or full egress. Reasonix's baseline only needs isolated vs full.

## Filesystem view construction (the important part)

```
full-disk-read policy:   --ro-bind / /
restricted-read policy:  --tmpfs /            (empty root, then layer scoped grants)
                         + --ro-bind <path> <path>      for every read grant
                         + --ro-bind-data <file>        for file grants
writable roots:          --bind <root> <root> (only after a read grant exists for it)
under-protected paths:   re-apply --ro-bind <subpath> after write bind, e.g.
                         writable /workspace but ~/.ssh stays read-only
tmp:                     --tmpfs /tmp and friends
```

Policy model (`FileSystemSandboxPolicy`): `entries: [{path, access: read|write, missing_path_behavior}]` with a default kind (full-disk access vs restricted). Explicit, declarative, serialisable — grants are data, not code.

## Seccomp

Applied post-bwrap in the inner stage; `no_new_privs` set together. The ordering constraint is documented: seccomp before bwrap would break bwrap's own privilege transitions.

## Landlock

`landlock.rs`: legacy/alternative enforcement without bwrap — ABI V5 ruleset, `path_beneath` rules: `/` read-only, writable roots read-write, `/dev/null` rw. User-space-syscall sandboxing; works unprivileged on kernels without user namespaces. **This is directly relevant to this host, where `kernel.unprivileged_userns_clone=0` blocks bwrap but Landlock (kernel >= 5.13) may still enforce.**

## What to take, and how

| Mechanism | Classification | Rationale |
|---|---|---|
| Filesystem policy as entry list `{path, access, missing_path_behavior}` | **ADAPT** (concept, reimplemented) | Directly becomes `SandboxPolicy{ReadablePaths, WritablePaths, ...}` per phase 7. Serde-style explicit grants beat globs of ad-hoc flags. |
| Restricted-read strategy: `--tmpfs /` + scoped `--ro-bind` grants | **ADAPT** | Finer than Reasonix's current `--ro-bind / /` (whole disk readable). Matches the requirement: SSH/cloud-cred/browser-profile paths blocked while toolchain stays readable. |
| Write-bind only atop a read grant; re-apply `--ro-bind` for protected subpaths | **ADAPT** | Prevents a writable root from silently covering a protected path inside it. |
| Network: `--unshare-net` by default, opt-in egress | **ADAPT** | Matches requirement "network off by default for privileged sandboxed commands". Proxy-routed mode skipped for MVP. |
| Two-stage hardening: bwrap → seccomp + no_new_privs after | **ADAPT** | Cheap once bwrap wraps: outer argv already exists; add inner seccomp stage later. |
| `PR_SET_PDEATHSIG` (Go: `SysProcAttr.Pdeathsig`) | **ADAPT** | One line; closes the orphan-process gap around kill-tree. |
| Capability probe before trusting bwrap | **ADAPT** — fixes a Reasonix gap | Reasonix `sandbox.Available()` only checks PATH; Codex probes argv0/permissions. Probe must include "can I actually create a namespace" (the failure mode on this host) and degrade to landlock/unconfined-with-warning. |
| Landlock fallback for unprivileged hosts | **ADAPT** — high value here | Unprivileged enforcement when userns is disabled; must be probed at runtime (syscall ABI). |
| Bundled bwrap delivery (compile/carry the binary) | **IGNORE** | We ship no binaries; system bwrap is enough for a research harness. |
| Proxy routing network mode | **IGNORE** | Not needed for MVP; revisit if egress inspection becomes a research question. |
| Full-disk-read default (`--ro-bind / /`) | **REIMPLEMENT** (stricter default) | Requirement: sensitive paths blocked by default; start from restricted-read, widen by grant. |
| Bazel integration (`bazel_bwrap.rs`) | **IGNORE** | Build-system coupling irrelevant here. |
| seccomp profile content (blacklists) | **REIMPLEMENT** later | Not needed for milestone 6–9 slice; add with evidence after the gate exists. |

## Design notes for Reasonix integration

- Reasonix already composes bwrap argv in `internal/sandbox/bwrapArgs`. The Codex layering scheme replaces the current 6-arg profile; WriteRoots grows into read/write path sets.
- If namespaces are unavailable (this host), enforcement falls through Landlock, then unconfined with a startup warning (existing boot/acp warning pattern). The security gate remains authoritative regardless — sandbox is depth, not the only control.
- Environment: Codex keeps the API-key/credentials story out of the sandbox entirely; Reasonix's contract is the same — the sandbox restricts paths/network, the gate restricts actions, and the audit records both.
- Test the argument builder as pure string construction (as Codex does with 661 lines of arg-composition tests); the failure mode here is wrong argv, not wrong kernel behaviour.
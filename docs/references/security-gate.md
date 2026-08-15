# Security gate (research)

The security control plane is a wrapper around Reasonix's existing permission
gate. It does not duplicate the permission system: every model tool call
crosses, in order:

1. **deterministic policy** (`internal/security/policy.go`) — deny sensitive
   paths (`~/.ssh`, `.aws`, `/etc/shadow`, …) before anything else, with an
   explainable reason and an override escape hatch (`REASONIX_SECURITY_POLICY=off`);
2. **capability check** (`internal/security/capability.go`) — granular scoped
   grants, deny-by-default; session grants derive from the workspace write
   roots, so normal workflows keep working;
3. **advisory risk** (`internal/security/risk.go`) — risk classification that
   can surface in prompts/audit but never overrides a policy decision;
4. **permission gate** (Reasonix `internal/permission`) — untouched ASK/ALLOW/
   DENY UX stays authoritative for what the policy lets through;
5. **structured audit** (`internal/security/audit.go`) — JSONL records of every
   decision, redacted args, matched policy, timing.

## Wiring

- `internal/boot/boot.go`: when `security.enabled`, the headless permission
  gate is wrapped once (`gate`) and the same wrapper is applied to every
  executor (main, subagents, planner). A `wrapGate` func is passed to the
  controller, so the interactive-approval gate swap re-applies the plane.
- `internal/control/controller.go`: `Options.WrapGate` / `Controller.wrapGate`;
  `EnableInteractiveApproval` wraps the new ask gate before `SetGate`.
- `internal/config/config.go`: `SecurityConfig` (`enabled`, optional
  `audit_file`); default off at this milestone.
- Audit default: `<cache_dir>/security/audit.jsonl`; never inside the
  workspace, so agent-side writes cannot forge the trail.

## Milestones

- [x] gate, policy, capability, risk, audit; wiring across executors; tests
      (`internal/security/*_test.go`; runs identical to baseline: the only
      failing packages are the pre-existing sandbox/tool-builtin ones).
- [x] **self-check + default on**: config defaults to `enabled=true`; boot runs
      `security.SelfCheck` (sensitive read denied, sensitive shell denied,
      workspace read/write granted, out-of-scope read denied) and fails safe —
      a failing self-check or audit file means the plane stays off with a
      warning. Baseline runs: `REASONIX_SECURITY_POLICY=off`.
- [ ] network/MCP capability enforcement; content-provenance capture;
      tamper-evident audit chain (see `docs/architecture/target.md`).
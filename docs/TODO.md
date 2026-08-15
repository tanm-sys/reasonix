# Parked work — not efficiency/security focus

Everything here is deliberately **not** the active focus. Do not start any of
these until a user asks. Security and efficiency tasks live in the audit notes
of `docs/references/security-gate.md` and this branch's commits instead.

## Research follow-ups (parked)
- [ ] Wrap the Go agent (capability gate + policy) as an agentdojo pipeline —
      first gated `attack_security` measurement. (The natural next step; parked
      only because ground-truth baseline is now recorded.)
- [ ] codex `bundled_bwrap` via cargo as a standalone seccomp-confining runner
      (M16 sandbox unlock on userns-blocked hosts). Cargo is installed; needs
      its own milestone, not a quick vendor.
- [ ] MCP tool mediation milestone: `mcp.call:<server>` capability grants +
      policy checks + provenance/audit. Until then MCP calls bypass the
      capability plane by design.
- [ ] prime-agent kernel (TypeScript) — not linkable into Go; concepts only.

## Product/upstream features (not our research; upstream owns them)
- [ ] Checkpoints & rewind — Phase 2 (desktop hover-rewind, fork-from-here,
      summarize-to-here, git-backed mode) — see `docs/CHECKPOINTS.md`.
- [ ] Desktop polish, themes, i18n, marketing site/assets, release tooling
      (upstream merges only; never hand-maintain here).
- [ ] Any upstream feature from `main` that our fork has not merged yet:
      re-base via `git merge` upstream, do not cherry-pick our research code.

## Hygiene
- [x] Committed `__pycache__` noise removed + ignored (commit 7c914ac).
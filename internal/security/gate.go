package security

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sync"
	"time"

	"reasonix/internal/agent"
)

// Gate implements agent.Gate: the security control plane sitting in front of
// the existing permission gate. Evaluation order: deterministic policy →
// capability check → advisory risk → inner gate (existing permission UX) →
// audit. Tool-specific logic lives in policy.go; this file only composes.
type Gate struct {
	policy    Policy
	grants    *GrantSet
	audit     *AuditLog
	sessionID string

	mu    sync.RWMutex
	inner agent.Gate // existing permission gate (headless or interactive)
}

// NewGate builds the security gate. inner is the existing permission gate
// (permission.NewGate) used for ASK resolution; it can be swapped later via
// SetInner when a frontend upgrades to interactive approval. Nil inner or
// grants are tolerated only in a not-armed state; Check treats them as deny
// rather than panicking (startup self-check path).
func NewGate(policy Policy, grants *GrantSet, audit *AuditLog, sessionID string, inner agent.Gate) *Gate {
	if grants == nil {
		grants = NewGrants()
	}
	return &Gate{
		policy:    policy,
		grants:    grants,
		audit:     audit,
		sessionID: sessionID,
		inner:     inner,
	}
}

// SetInner replaces the inner permission gate. Used by interactive frontends
// when they swap the headless gate for an approval-backed one; the security
// layer itself is untouched by the swap.
func (g *Gate) SetInner(inner agent.Gate) {
	g.mu.Lock()
	defer g.mu.Unlock()
	g.inner = inner
}

func (g *Gate) innerGate() agent.Gate {
	g.mu.RLock()
	defer g.mu.RUnlock()
	return g.inner
}

// Check evaluates one tool call. It implements agent.Gate.
func (g *Gate) Check(ctx context.Context, toolName string, args json.RawMessage, readOnly bool) (bool, string, error) {
	op, subject, caps := reqFromTool(toolName, args)
	now := time.Now().UTC()
	auditID := newAuditID()

	// 1. Deterministic security policy (credential/system paths; shell refs).
	if reason, denied := g.policy.Denies(toolName, args); denied {
		if g.audit != nil {
			g.audit.Append(Record{
				TS: now, SessionID: g.sessionID, Actor: "model", Tool: toolName,
				Operation: string(op), Args: RedactArgs(args),
				Provenance: []string{string(OriginModel)},
				Policy:     []string{"sensitive_path"}, Risk: riskOf(op, subject).String(),
				Decision: "DENY", Reason: reason, AuditID: auditID,
				ExecutionStatus: "blocked",
			})
		}
		return false, reason, nil
	}

	// 2. Capability check: deny by default, grant by session.
	granted := ""
	for _, c := range caps {
		if !g.grants.Allows(c) {
			reason := fmt.Sprintf("blocked: capability %s not granted for this session; grant it in the security config or reduce the request scope", c.String())
			if g.audit != nil {
				g.audit.Append(Record{
					TS: now, SessionID: g.sessionID, Actor: "model", Tool: toolName,
					Operation: string(op), Args: RedactArgs(args),
					Provenance: []string{string(OriginModel)}, Capability: c.String(),
					Policy:   []string{"capability"},
					Risk:     riskOf(op, subject).String(),
					Decision: "DENY", Reason: reason, AuditID: auditID,
					ExecutionStatus: "blocked",
				})
			}
			return false, reason, nil
		}
		if granted == "" {
			granted = c.String()
		}
	}

	// 3. Advisory risk — never overrides the policy or a deny below.
	risk := riskOf(op, subject)

	// 4. Existing permission UX (inner gate: allow/ask/deny rules + approver).
	inner := g.innerGate()
	if inner == nil {
		// No permission gate installed (not-armed state): deny rather than panic.
		if g.audit != nil {
			g.audit.Append(Record{
				TS: now, SessionID: g.sessionID, Actor: "model", Tool: toolName,
				Operation: string(op), Args: RedactArgs(args),
				Provenance: []string{string(OriginModel)},
				Risk:       riskOf(op, subject).String(),
				Decision:   "BLOCKED", Reason: "security gate not armed (no inner permission gate)",
				AuditID: auditID, ExecutionStatus: "blocked",
			})
		}
		return false, "security gate not armed", nil
	}
	allow, reason, err := inner.Check(ctx, toolName, args, readOnly)
	decision := "ALLOW"
	if err != nil {
		decision = "BLOCKED"
	} else if !allow {
		decision = "DENY"
	}
	if g.audit != nil {
		g.audit.Append(Record{
			TS: now, SessionID: g.sessionID, Actor: "model", Tool: toolName,
			Operation: string(op), Args: RedactArgs(args),
			Provenance: []string{string(OriginModel)}, Capability: granted,
			Policy:   []string{"permission"},
			Risk:     risk.String(),
			Decision: decision, Reason: reason, AuditID: auditID,
		})
	}
	return allow, reason, err
}

// DefaultGrants builds the session's grant set from workspace roots: shell
// execution and workspace filesystem reads/writes are granted; everything else
// (network, MCP, out-of-workspace paths) is denied by default.
func DefaultGrants(workspaceRoots []string) *GrantSet {
	g := NewGrants()
	g.Grant(Capability{ID: "process.execute"})
	for _, root := range workspaceRoots {
		base := Capability{ID: "filesystem.read", Scope: root}
		write := Capability{ID: "filesystem.write", Scope: root}
		g.Grant(base)
		g.Grant(write)
	}
	return g
}

// newAuditID returns a short random id correlating the gate record with the
// execution outcome.
func newAuditID() string {
	var b [6]byte
	if _, err := rand.Read(b[:]); err != nil {
		return fmt.Sprintf("%d", time.Now().UnixNano())
	}
	return hex.EncodeToString(b[:])
}

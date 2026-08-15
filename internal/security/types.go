// Package security implements the security control plane: a gate that wraps
// the existing Reasonix permission gate and adds capability checks, a
// deterministic security policy (credential-path denies), advisory risk
// classification and a structured audit log. It plugs into the agent's
// existing agent.Gate seam, so every model-initiated tool call crosses it.
// The existing permission.Gate remains the ASK-resolution layer (approval UX).
package security

import (
	"time"
)

// Origin identifies where an action or the content motivating it came from.
type Origin string

const (
	OriginUser   Origin = "user"
	OriginModel  Origin = "model"
	OriginTool   Origin = "tool"
	OriginFile   Origin = "file"
	OriginWeb    Origin = "web"
	OriginMCP    Origin = "mcp"
	OriginKernel Origin = "kernel"
	OriginSystem Origin = "system"
)

// Provenance is a first-class record of origin, not log text. Detail carries
// the concrete source (file path, URL, tool name) when known.
type Provenance struct {
	Origin Origin    `json:"origin"`
	Detail string    `json:"detail,omitempty"`
	At     time.Time `json:"at"`
}

// Decision is the gate's verdict for one execution request.
type Decision int

const (
	// Allow runs the tool without further prompting.
	Allow Decision = iota
	// Ask defers to the inner permission gate's approver (existing UX).
	Ask
	// Deny blocks the tool; the reason is fed back to the model.
	Deny
)

func (d Decision) String() string {
	switch d {
	case Allow:
		return "ALLOW"
	case Ask:
		return "ASK"
	case Deny:
		return "DENY"
	default:
		return "UNKNOWN"
	}
}

// RiskLevel is advisory only. It may escalate Ask or inform wording; it never
// downgrades a policy Deny to Allow.
type RiskLevel int

const (
	RiskLow RiskLevel = iota
	RiskMedium
	RiskHigh
	RiskCritical
)

func (r RiskLevel) String() string {
	switch r {
	case RiskLow:
		return "low"
	case RiskMedium:
		return "medium"
	case RiskHigh:
		return "high"
	case RiskCritical:
		return "critical"
	default:
		return "unknown"
	}
}

// ExecutionRequest is what the gate evaluates. Built at the choke point from
// the agent.Gate.Check arguments plus gate-held context (session grants).
type ExecutionRequest struct {
	SessionID    string
	Actor        string // "model", "user", "kernel"
	Tool         string // tool name, incl. mcp__server__tool
	Operation    string // derived: read | write | execute | connect | call
	Arguments    []byte // raw model args
	ReadOnly     bool
	Capabilities []string     // capabilities this call requires (derived)
	Provenance   []Provenance // origin chain of the request and its content
}

// SecurityDecision is the gate's verdict with explanation.
type SecurityDecision struct {
	Action              Decision
	Reason              string
	MatchedPolicies     []string
	GrantedCapabilities []string
	Risk                RiskLevel
	AuditID             string
}

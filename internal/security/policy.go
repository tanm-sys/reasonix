package security

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

// Operation classifies a tool call for capability mapping.
type Operation string

const (
	OpRead    Operation = "read"
	OpWrite   Operation = "write"
	OpExecute Operation = "execute"
	OpConnect Operation = "connect"
	OpCall    Operation = "call"
)

// reqFromTool derives operation, subject and required capabilities from a tool
// call. Tool-specific parsing is deliberately tiny and lives here, not in the
// gate: the gate only evaluates what this returns.
func reqFromTool(toolName string, args []byte) (Operation, string, []Capability) {
	switch {
	case strings.HasPrefix(toolName, "mcp__"):
		// MCP mediation is a later milestone; no capability asserted yet.
		return OpCall, "", nil
	case toolName == "bash":
		var p struct {
			Command string `json:"command"`
		}
		_ = json.Unmarshal(args, &p)
		return OpExecute, p.Command, []Capability{{ID: "process.execute"}}
	case toolName == "web_fetch":
		var p struct {
			URL string `json:"url"`
		}
		_ = json.Unmarshal(args, &p)
		return OpConnect, p.URL, nil // network policy lands with the sandbox milestone
	case isReader(toolName):
		var p struct {
			Path string `json:"path"`
		}
		_ = json.Unmarshal(args, &p)
		return OpRead, p.Path, []Capability{{ID: "filesystem.read", Scope: p.Path}}
	case isWriter(toolName):
		var p struct {
			Path string `json:"path"`
		}
		_ = json.Unmarshal(args, &p)
		return OpWrite, p.Path, []Capability{{ID: "filesystem.write", Scope: p.Path}}
	default:
		return "", "", nil
	}
}

func isReader(name string) bool {
	switch name {
	case "read_file", "ls", "glob", "grep", "codegraph_query":
		return true
	}
	return false
}

func isWriter(name string) bool {
	switch name {
	case "write_file", "edit_file", "multi_edit", "notebook_edit", "delete_range", "delete_symbol":
		return true
	}
	return false
}

// Policy is the deterministic security layer evaluated before the inner
// permission gate. It denies sensitive targets outright; everything else is
// left to capabilities + the existing permission UX.
type Policy struct {
	// DenyReadSensitive blocks reading/editing of credential and system paths.
	// Enabled by default; disabling is deliberate and should be config-driven.
	DenyReadSensitive bool
	// DenyBashSensitive blocks shell commands that reference sensitive paths.
	DenyBashSensitive bool
}

// DefaultPolicy is the safe default: sensitive paths denied.
func DefaultPolicy() Policy {
	return Policy{DenyReadSensitive: true, DenyBashSensitive: true}
}

// Denies returns a reason when the call must be hard-denied at the policy
// layer regardless of grants and permission rules.
func (p Policy) Denies(toolName string, args []byte) (reason string, denied bool) {
	op, subject, _ := reqFromTool(toolName, args)
	switch op {
	case OpRead, OpWrite:
		if !p.DenyReadSensitive {
			return "", false
		}
		abs, err := filepath.Abs(subject)
		if err == nil && isSensitivePath(abs) {
			return fmt.Sprintf("refusing %s of %q: credential/system path outside granted scope", op, subject), true
		}
	case OpExecute:
		if !p.DenyBashSensitive || subject == "" {
			return "", false
		}
		if commandReferencesSensitive(subject) {
			return "refusing shell command: references credential or system path", true
		}
	}
	return "", false
}

// commandReferencesSensitive does a conservative word-boundary scan for
// sensitive path references inside a shell command (e.g. "cat ~/.ssh/id_rsa",
// "ssh somehost", "curl … .aws/credentials"). Conservative by design: false
// positives surface as ASK/deny with an override path, false negatives are
// covered by the sandbox (later milestone) and the audit trail.
func commandReferencesSensitive(cmd string) bool {
	lower := strings.ToLower(cmd)
	for _, tok := range sensitiveCommandTokens {
		sensitiveCommandRe := boundaryRe(tok)
		if sensitiveCommandRe.MatchString(lower) {
			return true
		}
	}
	return false
}

// sensitiveCommandTokens matched as whole words so "awsome-tool" or
// "ssh_config docs" do not trip the rule on their own.
var sensitiveCommandTokens = []string{
	"id_rsa", "id_ed25519", "ssh", "scp", "aws", "gcloud", "kubectl",
	"credentials", ".netrc", ".gnupg", ".npmrc", ".pypirc", "kubeconfig",
	"git-credentials", "shadow", "sudoers", "passwd", "wget", "curl",
	"api_key", "token", "secret", "password",
}

func boundaryRe(tok string) *regexp.Regexp {
	re, err := regexp.Compile(`(^|[^a-z0-9])` + regexp.QuoteMeta(tok) + `([^a-z0-9]|$)`)
	if err != nil {
		return regexp.MustCompile(regexp.QuoteMeta(tok))
	}
	return re
}

// riskOf classifies the call for the advisory risk field. Heuristics only:
// the decision comes from policy/capabilities/permission rules.
func riskOf(op Operation, subject string) RiskLevel {
	switch op {
	case OpExecute:
		if commandReferencesSensitive(subject) {
			return RiskCritical
		}
		return RiskMedium
	case OpRead, OpWrite:
		abs, err := filepath.Abs(subject)
		if err == nil && isSensitivePath(abs) {
			return RiskCritical
		}
		return RiskLow
	default:
		return RiskLow
	}
}

// envOverride allows the policy to be exercised in tests and evaluation runs
// without touching the config file (baseline runs set it to "0").
func envOverride() bool {
	return os.Getenv("REASONIX_SECURITY_POLICY") == "off"
}

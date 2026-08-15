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
//
// Subject semantics: file tools resolve their target the same way the built-ins
// do (paths may be relative to the workspace; an absent path means the
// workspace itself). File capability checks therefore work for "ls", "glob"
// (no path field at all) and "grep" (optional path) — not just explicit-path
// calls. Non-file tools assert no capability (see below).
func reqFromTool(toolName string, args []byte) (Operation, string, []Capability) {
	switch {
	case strings.HasPrefix(toolName, "mcp__"):
		// MCP mediation is a later milestone; the permission layer gates it.
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
		// Network capability lands with the sandbox milestone; the SSRF-guarded
		// dialer and the permission layer gate web_fetch today.
		return OpConnect, p.URL, nil
	case isReader(toolName) || isWriter(toolName):
		var p struct {
			Path    string `json:"path"`
			Pattern string `json:"pattern"`
		}
		_ = json.Unmarshal(args, &p)
		subject := p.Path
		if subject == "" {
			// glob has no path field; grep/ls omit it to mean "." — resolve the
			// tool's own default ("." = workspace root at runtime) so scope
			// matching sees an absolute path instead of an un-grantable "".
			subject = p.Pattern
		}
		if subject != "" {
			if abs, err := filepath.Abs(subject); err == nil {
				subject = abs
			}
		} else if cwd, err := os.Getwd(); err == nil {
			subject = cwd
		}
		id := "filesystem.read"
		if isWriter(toolName) {
			id = "filesystem.write"
		}
		return opOf(toolName), subject, []Capability{{ID: id, Scope: subject}}
	default:
		// Uncategorized tools (ask, todo, memory, task, plugin/codegraph tools,
		// ...) assert no capability: the permission UX gates them exactly as in
		// the base variant. The capability plane covers file and shell ops.
		return "", "", nil
	}
}

func opOf(name string) Operation {
	if isWriter(name) {
		return OpWrite
	}
	return OpRead
}

func isReader(name string) bool {
	switch name {
	case "read_file", "ls", "glob", "grep":
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
// credential-theft references inside a shell command (e.g. "cat ~/.ssh/id_rsa",
// "curl … .aws/credentials"). These are hard-denied before the permission
// gate. Anything else — including legit "ssh host" or "aws s3 ls" — is left to
// capabilities + permission UX (a false-positive hard deny would break normal
// shell workflows, so only exfiltration verbs live here).
func commandReferencesSensitive(cmd string) bool {
	return sensitiveCommandRe.MatchString(strings.ToLower(cmd))
}

// sensitiveCommandTokens are the deny-list: directly grabbing credentials or
// system auth material. "passwd"/"shadow" also cover reading auth databases.
var sensitiveCommandTokens = []string{
	"id_rsa", "id_ed25519", "credentials", ".netrc", ".gnupg", ".npmrc",
	".pypirc", "kubeconfig", "git-credentials", "shadow", "sudoers", "passwd",
	"api_key", "token", "secret", "password",
}

// riskCommandTokens are word-boundary flags that do NOT deny but classify the
// call as critical risk for the audit (remote exfiltration vectors and tools
// that can read local secrets indirectly).
var riskCommandTokens = []string{
	"ssh", "scp", "aws", "gcloud", "kubectl", "curl", "wget", "nc",
	"netcat", "socat", "telnet",
}

// sensitiveCommandRe is the alternation of all tokens with word boundaries,
// compiled once instead of per call/per token.
var sensitiveCommandRe = regexp.MustCompile(func() string {
	quoted := make([]string, len(sensitiveCommandTokens))
	for i, tok := range sensitiveCommandTokens {
		quoted[i] = regexp.QuoteMeta(tok)
	}
	return `(^|[^a-z0-9])(` + strings.Join(quoted, "|") + `)([^a-z0-9]|$)`
}())

// riskCommandRe flags risk tokens the same way (word boundaries, whole words).
var riskCommandRe = regexp.MustCompile(func() string {
	quoted := make([]string, len(riskCommandTokens))
	for i, tok := range riskCommandTokens {
		quoted[i] = regexp.QuoteMeta(tok)
	}
	return `(^|[^a-z0-9])(` + strings.Join(quoted, "|") + `)([^a-z0-9]|$)`
}())

// riskOf classifies the call for the advisory risk field. Heuristics only:
// the decision comes from policy/capabilities/permission rules.
func riskOf(op Operation, subject string) RiskLevel {
	switch op {
	case OpExecute:
		if commandReferencesSensitive(subject) || riskCommandRe.MatchString(strings.ToLower(subject)) {
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

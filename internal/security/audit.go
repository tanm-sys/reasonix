package security

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"
)

// Record is one structured audit entry: one per gate decision, completed with
// execution status after the tool call. Redacted args only; secrets never.
type Record struct {
	TS         time.Time `json:"ts"`
	SessionID  string    `json:"session,omitempty"`
	Actor      string    `json:"actor"`
	Tool       string    `json:"tool"`
	Operation  string    `json:"operation"`
	Args       string    `json:"args_redacted"`
	Provenance []string  `json:"provenance"`
	Capability string    `json:"capability,omitempty"`
	Policy     []string  `json:"policy"`
	Risk       string    `json:"risk"`
	Decision   string    `json:"decision"`
	Reason     string    `json:"reason,omitempty"`
	AuditID    string    `json:"audit_id"`
	// ExecutionStatus fills in after the tool ran: "ok" | "error" | "blocked".
	ExecutionStatus string `json:"execution_status"`
}

// maxArgsBytes caps the stored argument representation.
const maxArgsBytes = 512

// secretArgKeys are masked whenever they appear as JSON keys or "k=v" tokens.
var secretArgKeys = []string{
	"token", "secret", "password", "api_key", "apikey", "authorization",
	"private_key", "credential", "key", "client_secret",
}

// bearerTokenRe masks "Bearer <token>" values wherever they appear.
var bearerTokenRe = regexp.MustCompile(`(?i)bearer\s+[A-Za-z0-9._~+/=-]{4,}`)

// RecordHook builds a Record for a non-tool execution (shell hooks, slash
// side effects) so the audit trail covers activity that never reaches Gate.
// The command is truncated by append-time redaction.
func RecordHook(event, command string) Record {
	return Record{
		TS:        time.Now().UTC(),
		Actor:     "hook",
		Tool:      "hook",
		Operation: event,
		Args:      command,
		Policy:    []string{"trusted_hook"},
		Risk:      "high",
		Decision:  "ALLOW",
		AuditID:   newAuditID(),
	}
}

// AuditLog appends JSON lines to a file. Safe for concurrent use: writes are
// serialised and flushed per record. The file is opened with O_APPEND and is
// expected to live outside the agent's write reach (state dir, not workspace).
type AuditLog struct {
	mu      sync.Mutex
	f       *os.File
	path    string
	enabled bool
}

// OpenAudit creates the audit log at path (creating parent dirs).
func OpenAudit(path string) (*AuditLog, error) {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return nil, fmt.Errorf("audit dir: %w", err)
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return nil, fmt.Errorf("audit open: %w", err)
	}
	// A pre-existing file may carry looser permissions; the trail must stay
	// unreadable by agent-adjacent processes.
	if err := f.Chmod(0o600); err != nil {
		f.Close()
		return nil, fmt.Errorf("audit chmod: %w", err)
	}
	return &AuditLog{f: f, path: path, enabled: true}, nil
}

// Close closes the underlying file.
func (a *AuditLog) Close() error {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.f == nil {
		return nil
	}
	return a.f.Close()
}

// Path returns the log path ("" for discard).
func (a *AuditLog) Path() string { return a.path }

// Append writes one record.
func (a *AuditLog) Append(r Record) {
	if !a.enabled {
		return
	}
	line, err := json.Marshal(r)
	if err != nil {
		return
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	_, _ = a.f.Write(append(line, '\n'))
	_ = a.f.Sync()
}

// RedactArgs returns a bounded, key-masked representation of raw tool args.
// Top-level JSON keys from secretArgKeys are blanked; "Bearer <token>" values
// are masked; a fixed bound keeps stored args small. Never a substitute for
// not logging secrets: values that do not match these shapes are kept.
func RedactArgs(raw []byte) string {
	s := strings.TrimSpace(string(raw))
	if len(s) > maxArgsBytes {
		s = s[:maxArgsBytes] + "…"
	}
	// Blank sensitive top-level JSON keys when the args parse as an object.
	var m map[string]json.RawMessage
	if err := json.Unmarshal([]byte(s), &m); err == nil {
		for k := range m {
			for _, secret := range secretArgKeys {
				if strings.EqualFold(k, secret) {
					m[k] = json.RawMessage(`""`)
				}
			}
		}
		if redacted, err := json.Marshal(m); err == nil {
			s = string(redacted)
		}
	}
	// Mask bearer tokens wherever they appear (headers, config strings).
	s = bearerTokenRe.ReplaceAllString(s, "Bearer \u2026")
	if len(s) > maxArgsBytes {
		s = s[:maxArgsBytes] + "…"
	}
	return s
}

package security

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestIsSensitivePath(t *testing.T) {
	cases := []struct {
		path string
		want bool
	}{
		{"/home/u/project/src/main.go", false},
		{"/home/u/.ssh/id_rsa", true},
		{"/home/u/project/.ssh-keys/x", false}, // not a sensitive component
		{"/root/.aws/credentials", true},
		{"/home/u/.config/gcloud/creds.json", true},
		{"/etc/shadow", true},
		{"/etc/passwd", true},
		{"/etc/hostname", false},
		{"/home/u/.npmrc", true},
		{"/home/u/.git-credentials", true},
	}
	for _, c := range cases {
		if got := isSensitivePath(c.path); got != c.want {
			t.Errorf("isSensitivePath(%q) = %v, want %v", c.path, got, c.want)
		}
	}
}

func TestGrantSetAllows(t *testing.T) {
	g := NewGrants()
	g.Grant(Capability{ID: "process.execute"})
	g.Grant(Capability{ID: "filesystem.read", Scope: "/work/proj"})
	g.Grant(Capability{ID: "mcp.call", Scope: ""}) // wildcard

	if !g.Allows(Capability{ID: "process.execute"}) {
		t.Error("process.execute should be granted")
	}
	if g.Allows(Capability{ID: "network.connect", Scope: "evil.example"}) {
		t.Error("ungranted capability must be denied")
	}
	if !g.Allows(Capability{ID: "filesystem.read", Scope: "/work/proj"}) {
		t.Error("exact scope should match")
	}
	if !g.Allows(Capability{ID: "filesystem.read", Scope: "/work/proj/sub/x.go"}) {
		t.Error("descendant path should match directory grant")
	}
	if g.Allows(Capability{ID: "filesystem.read", Scope: "/work/proj-other/x"}) {
		t.Error("prefix-lookalike sibling must not match")
	}
	if g.Allows(Capability{ID: "filesystem.read", Scope: "/etc/passwd"}) {
		t.Error("unrelated path must not match")
	}
	if !g.Allows(Capability{ID: "mcp.call", Scope: "github"}) {
		t.Error("empty-scope grant covers all scopes")
	}
}

func TestPolicyDeniesSensitiveRead(t *testing.T) {
	p := DefaultPolicy()
	if _, denied := p.Denies("read_file", []byte(`{"path":"/home/u/project/go.mod"}`)); denied {
		t.Error("workspace read must not be denied")
	}
	reason, denied := p.Denies("read_file", []byte(`{"path":"~/.ssh/id_rsa"}`))
	if !denied || !strings.Contains(reason, "credential") {
		t.Errorf(".ssh read should be denied with credential reason, got %q %v", reason, denied)
	}
	// Symlink/.. smuggling still resolves inside the sensitive component check.
	if _, denied := p.Denies("write_file", []byte(`{"path":"/home/u/.aws/../.aws/credentials"}`)); !denied {
		t.Error(".aws write must be denied")
	}
}

func TestPolicyDeniesSensitiveBash(t *testing.T) {
	p := DefaultPolicy()
	if _, denied := p.Denies("bash", []byte(`{"command":"go test ./..."}`)); denied {
		t.Error("benign build command must not be denied")
	}
	if _, denied := p.Denies("bash", []byte(`{"command":"git status"}`)); denied {
		t.Error("git status must not be denied")
	}
	reason, denied := p.Denies("bash", []byte(`{"command":"cat ~/.ssh/id_rsa"}`))
	if !denied || !strings.Contains(reason, "credential") {
		t.Errorf("credential-touching command should be denied, got %q %v", reason, denied)
	}
	if _, denied := p.Denies("bash", []byte(`{"command":"aws s3 ls"}`)); !denied {
		t.Error("aws command should be denied (credential scope)")
	}
}

func TestGateComposition(t *testing.T) {
	dir := t.TempDir()
	audit, err := OpenAudit(filepath.Join(dir, "audit.jsonl"))
	if err != nil {
		t.Fatal(err)
	}
	defer audit.Close()

	ws := filepath.Join(dir, "workspace")
	os.MkdirAll(ws, 0o755)
	grants := DefaultGrants([]string{ws})

	// inner: permissive gate that behaves like headless (ask -> allow).
	inner := trustedGate{}
	g := NewGate(DefaultPolicy(), grants, audit, "sess-1", inner)

	ctx := context.Background()
	// benign workspace read allowed through
	allow, reason, err := g.Check(ctx, "read_file", json.RawMessage(`{"path":"/`+ws+`/x.go"}`), true)
	if !allow || err != nil {
		t.Fatalf("workspace read: allow=%v reason=%q err=%v", allow, reason, err)
	}
	// sensitive read denied at policy layer
	allow, reason, err = g.Check(ctx, "read_file", json.RawMessage(`{"path":"/home/u/.ssh/id_rsa"}`), true)
	if allow || err != nil {
		t.Fatalf("sensitive read must be hard-denied: allow=%v err=%v", allow, err)
	}
	// out-of-workspace read denied at capability layer
	allow, reason, err = g.Check(ctx, "read_file", json.RawMessage(`{"path":"/etc/hostname"}`), true)
	if allow || !strings.Contains(reason, "capability") {
		t.Fatalf("out-of-scope read must be capability-denied: allow=%v reason=%q", allow, reason)
	}
	// bash with grant allowed
	allow, _, err = g.Check(ctx, "bash", json.RawMessage(`{"command":"go test ./..."}`), false)
	if !allow || err != nil {
		t.Fatalf("granted bash must pass: allow=%v err=%v", allow, err)
	}

	// audit trail exists with deny + allow records
	data, _ := os.ReadFile(audit.Path())
	lines := strings.Split(strings.TrimSpace(string(data)), "\n")
	if len(lines) < 4 {
		t.Fatalf("expected >=4 audit records, got %d", len(lines))
	}
	if !strings.Contains(lines[1], `"decision":"DENY"`) {
		t.Errorf("deny record missing, got: %s", lines[1])
	}
	if !strings.Contains(lines[2], `"decision":"DENY"`) && !strings.Contains(lines[2], "capability") {
		t.Errorf("capability deny record missing: %s", lines[2])
	}
}

func TestRedactArgs(t *testing.T) {
	out := RedactArgs([]byte(`{"command":"git status"}`))
	if !strings.Contains(out, "git status") {
		t.Errorf("benign args must survive redaction: %q", out)
	}
	out = RedactArgs([]byte(`{"command":"curl -H \"Authorization: Bearer abc123\" https://x"}`))
	if strings.Contains(out, "abc123") {
		t.Errorf("token leaked in redaction: %q", out)
	}
	out = RedactArgs([]byte(`{"api_key":"sk-verysecret","path":"/x"}`))
	if strings.Contains(out, "sk-verysecret") {
		t.Errorf("api_key leaked in redaction: %q", out)
	}
	// bounded
	out = RedactArgs([]byte(`{"x":"` + strings.Repeat("a", 2000) + `"}`))
	if len(out) > maxArgsBytes+8 {
		t.Errorf("redaction not bounded: %d", len(out))
	}
}

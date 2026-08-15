package security

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

// TestSelfCheckPasses ensures a correctly-configured plane arms.
func TestSelfCheckPasses(t *testing.T) {
	root := t.TempDir()
	if err := SelfCheck([]string{root}); err != nil {
		t.Fatalf("self-check failed on sane config: %v", err)
	}
}

// TestSelfCheckDeniesWithEmptyGrants ensures no grant set is never allowed to
// arm silently as allow-all (deny-by-default self-check).
func TestSelfCheckDeniesWithEmptyGrants(t *testing.T) {
	if err := SelfCheck(nil); err == nil {
		t.Fatal("expected self-check failure without workspace roots")
	}
}

// TestSelfCheckRejectsUncoveredRead ensures a config that fails the workspace
// grant check refuses to arm (regression guard for wiring mistakes).
func TestSelfCheckRejectsUncoveredRead(t *testing.T) {
	root := filepath.Join(t.TempDir(), "workspace")
	if err := os.MkdirAll(root, 0o755); err != nil {
		t.Fatal(err)
	}
	// Grants that only cover a *sibling* path must not satisfy a check that
	// expects the root covered.
	g := NewGrants()
	g.Grant(Capability{ID: "filesystem.read", Scope: root + "-elsewhere"})
	g.Grant(Capability{ID: "filesystem.write", Scope: root + "-elsewhere"})
	g.Grant(Capability{ID: "process.execute"})
	gate := NewGate(DefaultPolicy(), g, nil, "", allowAllGate{})
	if ok, _, err := gate.Check(context.Background(), "read_file", mustJSON(t, map[string]string{"path": filepath.Join(root, "f.txt")}), true); err == nil && ok {
		t.Fatal("read outside grant scope unexpectedly allowed")
	}
}

func mustJSON(t *testing.T, v map[string]string) []byte {
	t.Helper()
	b, err := json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	return b
}

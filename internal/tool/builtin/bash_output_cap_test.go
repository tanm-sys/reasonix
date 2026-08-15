package builtin

import (
	"context"
	"strings"
	"testing"

	"reasonix/internal/sandbox"
)

// TestBashOutputCap verifies runaway foreground output is capped: the returned
// text stays bounded and carries a truncation marker. Unbounded capture would
// re-send the whole blob to the model on every later turn until compaction.
func TestBashOutputCap(t *testing.T) {
	sh := sandbox.ResolveShell()
	out, err := (bash{shell: sh}).Execute(context.Background(), argsJSON(t, map[string]any{"command": "seq 1 100000"}))
	if err != nil {
		t.Fatalf("seq failed: %v", err)
	}
	if len(out) > bashOutputCap+200 {
		t.Fatalf("output = %d bytes, want <= %d+cappedBuffer margin", len(out), bashOutputCap)
	}
	if !strings.Contains(out, "(output truncated at 65536 bytes)") {
		t.Fatalf("missing truncation marker; output ends: %q", out[len(out)-120:])
	}
}

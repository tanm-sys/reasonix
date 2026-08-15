package jobs

import (
	"context"
	"io"
	"strings"
	"testing"

	"reasonix/internal/event"
)

// TestJobBufferRing verifies an unconsumed streaming job is bounded: overflow
// drops the oldest bytes and the next poll reports the newest tail with a
// clipped notice instead of unbounded memory + context growth.
func TestJobBufferRing(t *testing.T) {
	m := NewManager(event.Discard)
	j := m.Start("bash", "spam", func(ctx context.Context, out io.Writer) (string, error) {
		chunk := make([]byte, 16<<10)
		for i := 0; i < 24; i++ { // 384 KiB total, 3x the cap
			out.Write(chunk)
		}
		return "", nil
	})
	<-j.done

	text, _, ok := m.Output(j.ID)
	if !ok {
		t.Fatal("job not found")
	}
	if !strings.Contains(text, "clipped at 128 KiB") {
		t.Fatalf("missing clipped notice: %q...", text[:80])
	}
	if len(text) > jobOutputCap+200 {
		t.Fatalf("polled output = %d bytes, want <= cap", len(text))
	}
	rest, _, _ := m.Output(j.ID)
	if rest != "" {
		t.Fatalf("second poll not empty after drain, got %d bytes", len(rest))
	}
}

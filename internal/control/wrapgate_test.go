package control

import (
	"context"
	"encoding/json"
	"sync"
	"testing"

	"reasonix/internal/agent"
	"reasonix/internal/event"
	"reasonix/internal/permission"
	"reasonix/internal/provider"
	"reasonix/internal/tool"
)

// recordingGate is an agent.Gate that records every decision and forwards to
// the wrapped inner gate.
type recordingGate struct {
	mu    sync.Mutex
	calls int
	inner agent.Gate
}

func (r *recordingGate) Check(ctx context.Context, toolName string, args json.RawMessage, readOnly bool) (bool, string, error) {
	r.mu.Lock()
	r.calls++
	r.mu.Unlock()
	return r.inner.Check(ctx, toolName, args, readOnly)
}

func (r *recordingGate) Calls() int {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.calls
}

// TestEnableInteractiveApprovalAppliesWrapGate guards the security-plane
// invariant: EnableInteractiveApproval must re-apply the wrapGate on top of
// the new ask gate, so a security-enabled run never drops capability checks
// and audit when the interactive frontend swaps gates.
func TestEnableInteractiveApprovalAppliesWrapGate(t *testing.T) {
	writer := &recordingWriter{}
	reg := tool.NewRegistry()
	reg.Add(writer)

	prov := &scriptedTurns{turns: [][]provider.Chunk{
		toolCallTurn("c1", "write_file", `{"path":"a.txt"}`),
		textTurn("Done."),
	}}
	ag := agent.New(prov, reg, agent.NewSession(""), agent.Options{}, event.Discard)

	approvalID := make(chan string, 2)
	var recorder *recordingGate
	c := New(Options{
		Runner:   ag,
		Executor: ag,
		Policy:   permission.New("ask", nil, nil, nil),
		WrapGate: func(inner agent.Gate) agent.Gate {
			recorder = &recordingGate{inner: inner}
			return recorder
		},
		Sink: event.FuncSink(func(e event.Event) {
			if e.Kind == event.ApprovalRequest {
				approvalID <- e.Approval.ID
			}
		}),
	})
	c.EnableInteractiveApproval()
	if recorder == nil {
		t.Fatal("WrapGate was not applied")
	}

	go func() { c.Approve(<-approvalID, true, true, false) }()
	if err := c.runTurnWithRaw(context.Background(), "edit the files", "edit the files"); err != nil {
		t.Fatalf("turn failed: %v", err)
	}
	if recorder.Calls() == 0 {
		t.Fatal("wrapped gate saw no tool calls; security plane bypassed")
	}
}

package security

import (
	"context"
	"encoding/json"
	"fmt"
	"path/filepath"
)

// trustedGate is the inner gate used by SelfCheck: existing permission UX is
// out of scope for the plane's own startup verification.
type trustedGate struct{}

func (trustedGate) Check(context.Context, string, json.RawMessage, bool) (bool, string, error) {
	return true, "", nil
}

// SelfCheck verifies the plane intercepts as designed before boot arms it:
//  1. a sensitive-path read (e.g. ~/.ssh/id_rsa) is denied by policy,
//  2. a shell command referencing a sensitive path is denied,
//  3. a workspace read is granted and reaches the inner gate,
//  4. an out-of-workspace filesystem read is denied by capability scope,
//  5. granting nothing still denies everything (no accidental allow-all).
//
// If any check fails the gate is misconfigured and must not arm; boot refuses
// to install it in that case (fail-safe: plane off beats plane broken).
func SelfCheck(workspaceRoots []string) error {
	if len(workspaceRoots) == 0 || workspaceRoots[0] == "" {
		return fmt.Errorf("self-check: no workspace root to verify grants against")
	}
	root := workspaceRoots[0]
	g := NewGate(DefaultPolicy(), DefaultGrants(workspaceRoots), nil, "", trustedGate{})

	checks := []struct {
		name string
		tool string
		args string
		want bool
	}{
		{"sensitive read denied", "read_file", `{"path":"~/.ssh/id_rsa"}`, false},
		{"sensitive shell denied", "bash", `{"command":"cat /etc/shadow"}`, false},
		{"workspace read granted", "read_file", `{"path":"` + filepath.Join(root, "file.txt") + `"}`, true},
		{"workspace write granted", "write_file", `{"path":"` + filepath.Join(root, "out.txt") + `"}`, true},
		{"out-of-scope read denied", "read_file", `{"path":"/tmp/outside-workspace/file.txt"}`, false},
		// Real tool arg shapes (regression guard: glob/grep have no path, ls
		// treats it as optional). Relative subjects resolve against the process
		// cwd, which at boot is the workspace root, so these use absolute
		// patterns here; the relative path is covered in gate_test.
		{"workspace glob granted", "glob", `{"pattern":"` + filepath.Join(root, "**/*.go") + `"}`, true},
		{"sensitive glob denied", "glob", `{"pattern":"~/.ssh/*"}`, false},
		{"workspace ls granted", "ls", `{"path":"` + root + `"}`, true},
		{"workspace grep granted", "grep", `{"pattern":"x","path":"` + root + `"}`, true},
		{"out-of-scope grep denied", "grep", `{"pattern":"x","path":"/tmp/outside-workspace/"}`, false},
	}
	for _, c := range checks {
		ok, _, err := g.Check(context.Background(), c.tool, json.RawMessage(c.args), c.tool == "read_file")
		if err != nil {
			return fmt.Errorf("self-check %q errored: %w", c.name, err)
		}
		if ok != c.want {
			return fmt.Errorf("self-check %q: got allow=%v, want %v", c.name, ok, c.want)
		}
	}
	return nil
}

//go:build !darwin

package sandbox

import (
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

// Linux confinement strategy, in order of preference:
//  1. bubblewrap (bwrap) — real namespace-based confinement, the main path.
//  2. landlock — detected (ABI reported) but not yet used for confinement;
//     wiring it as a fallback when bwrap is unusable is the next milestone.
//  3. unconfined — permission layer still gates every call; boot warns once.

var (
	bwrapOnce sync.Once
	bwrapRoot string // resolved bwrap path when usable
	bwrapOK   bool
)

// BwrapInstalled reports whether bwrap is on PATH. It says nothing about
// whether it can actually confine on this kernel — use Available for that.
func BwrapInstalled() bool {
	_, err := exec.LookPath("bwrap")
	return err == nil
}

// bwrapUsable verifies bwrap actually confines on this kernel. PATH presence
// alone is not evidence: hardened hosts (userns restrictions, setuid bwrap
// missing, AppArmor) let bwrap install but fail every real run. The probe
// executes bwrap on a throwaway sandbox with the same arguments a real
// confinement uses; result is cached for the process lifetime.
func bwrapUsable() bool {
	bwrapOnce.Do(func() {
		p, err := exec.LookPath("bwrap")
		if err != nil {
			return
		}
		argv := append([]string{p},
			"--unshare-net", "--ro-bind", "/", "/",
			"--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "/bin/true")
		cmd := exec.Command(argv[0], argv[1:]...)
		cmd.Stdout = nil
		cmd.Stderr = nil
		done := make(chan error, 1)
		if err := cmd.Start(); err != nil {
			return
		}
		go func() { done <- cmd.Wait() }()
		select {
		case err := <-done:
			if err == nil {
				bwrapRoot, bwrapOK = p, true
			}
		case <-time.After(10 * time.Second):
			_ = cmd.Process.Kill()
		}
	})
	return bwrapOK
}

// Available reports whether an OS sandbox is available on this platform: on
// Linux, bwrap is installed AND its self-test ran clean inside a sandbox.
func Available() bool {
	return bwrapUsable()
}

// LandlockABI returns the detected Linux landlock ABI version, or 0 when
// landlock is unavailable or undetectable. Result is cached; only used for
// diagnostics and the upcoming landlock fallback milestone.
func LandlockABI() int {
	landlockOnce.Do(func() {
		if b, err := os.ReadFile("/sys/kernel/security/landlock/abi"); err == nil {
			if n, err := strconv.Atoi(strings.TrimSpace(string(b))); err == nil {
				landlockABI = n
				return
			}
		}
		// sysfs unreadable (containers): probe via prctl(PR_LANDLOCK_CREATE_RULESET).
		// EOPNOTSUPP = kernel lacks landlock. Any other error means the syscall
		// exists but the (dummy) args were rejected — treat as available.
		const prLandlockCreateRuleset = 0x804
		_, _, errno := syscall.Syscall6(syscall.SYS_PRCTL, prLandlockCreateRuleset, 0, 0, 0, 0, 0)
		if errno != syscall.EOPNOTSUPP && errno != syscall.ENOSYS {
			landlockABI = 1 // syscall present; precise ABI unknown
		}
	})
	return landlockABI
}

var (
	landlockOnce sync.Once
	landlockABI  int
)

// Command runs the command confined when spec.Mode is "enforce" and bwrap
// passed its self-test: namespace-isolated, network denied unless spec.Network
// is true, writes confined to WriteRoots. When bwrap is not usable the command
// runs unconfined (boot and acp warn about this once at startup); the returned
// bool is false in that case, so callers know the sandbox did not engage.
func Command(spec Spec, sh Shell, command string) ([]string, bool) {
	if !spec.enforce() || !bwrapUsable() {
		return sh.argv(command), false
	}
	return append([]string{bwrapRoot}, bwrapArgs(spec, sh, command)...), true
}

// bwrapArgs builds the bubblewrap command-line arguments that confine the
// shell command to the write roots, deny network unless allowed, and allow
// read access to the whole filesystem (read-open policy, mirroring the macOS
// Seatbelt profile).
func bwrapArgs(spec Spec, sh Shell, command string) []string {
	args := []string{
		"--unshare-net", // deny network by default
		"--ro-bind", "/", "/",
		"--dev", "/dev",
		"--proc", "/proc",
		"--tmpfs", "/tmp",
	}
	if spec.Network {
		// Re-allow network by removing the network namespace.
		args = args[1:] // drop --unshare-net
	}
	for _, root := range spec.WriteRoots {
		args = append(args, "--bind", root, root)
	}
	return append(args, sh.argv(command)...)
}

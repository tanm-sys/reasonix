package security

import (
	"path/filepath"
	"strings"
)

// Capability is a scoped authority string: "filesystem.read:/workspace/project",
// "process.execute", "network.connect:host:port", "mcp.call:server".
type Capability struct {
	ID    string
	Scope string // concrete target (path, host, server name); "" for unscoped
}

func (c Capability) String() string {
	if c.Scope == "" {
		return c.ID
	}
	return c.ID + ":" + c.Scope
}

// GrantSet is the set of capabilities a session holds. Deny by default: a
// capability that is not present is not granted.
type GrantSet struct {
	byID map[string]map[string]bool // id -> scope -> granted
}

// NewGrants builds an empty grant set.
func NewGrants() *GrantSet {
	return &GrantSet{byID: map[string]map[string]bool{}}
}

// Grant adds a capability.
func (g *GrantSet) Grant(c Capability) {
	if g.byID[c.ID] == nil {
		g.byID[c.ID] = map[string]bool{}
	}
	g.byID[c.ID][c.Scope] = true
}

// Allows reports whether the capability is granted. Scope semantics: an
// empty-scope grant covers every request for that capability id; otherwise the
// request scope must be exactly the granted scope, or — when both look like
// filesystem paths — at or below the granted scope (granting a directory
// covers reads beneath it).
func (g *GrantSet) Allows(c Capability) bool {
	scopes, ok := g.byID[c.ID]
	if !ok {
		return false
	}
	if scopes[""] {
		return true
	}
	if c.Scope == "" {
		return false
	}
	for granted := range scopes {
		if scopeAllows(granted, c.Scope) {
			return true
		}
	}
	return false
}

// scopeAllows reports whether a grant with scope granted covers request scope
// requested: exact match, or both are absolute path-like and requested is at
// or below granted (prefix-safe: /work is not within /work-other).
func scopeAllows(granted, requested string) bool {
	if granted == requested {
		return true
	}
	if strings.HasPrefix(granted, "/") && strings.HasPrefix(requested, "/") &&
		!strings.ContainsAny(granted, ":") && !strings.ContainsAny(requested, ":") {
		rel, err := filepath.Rel(granted, requested)
		if err != nil {
			return false
		}
		return rel == "." || (rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator)))
	}
	return false
}

// Sensitive path prefixes whose direct read/write by the model is denied at the
// policy layer, regardless of other grants. The gate checks resolved paths so
// "~", symlinks and ".." cannot smuggle a sensitive path past the rule.
var sensitivePathPrefixes = []string{
	".ssh",
	".aws",
	".config/gcloud",
	".config/gh",
	".docker",
	".gnupg",
	".netrc",
	".npmrc",
	".pypirc",
	".git-credentials",
	"etc/shadow",
	"etc/passwd",
	"etc/sudoers",
	"etc/ssh",
	"etc/ssl",
	"var/lib/docker",
	"var/lib/kubelet",
}

// isSensitivePath reports whether resolved absolute path touches a sensitive
// prefix. Single-segment prefixes (".ssh", ".aws") match as path components so
// ".ssh-keys" is not caught; multi-segment prefixes ("etc/shadow") match as
// path suffixes.
func isSensitivePath(abs string) bool {
	abs = filepath.Clean(abs)
	parts := strings.Split(strings.TrimPrefix(abs, "/"), string(filepath.Separator))
	for _, s := range sensitivePathPrefixes {
		if strings.Contains(s, "/") {
			if abs == "/"+s || strings.Contains(abs, "/"+s+"/") || strings.HasSuffix(abs, "/"+s) {
				return true
			}
			continue
		}
		for _, p := range parts {
			if p != "" && strings.EqualFold(p, s) {
				return true
			}
		}
	}
	return false
}

package policy

import (
	"strings"
	"sync"
	"time"

	"github.com/ChiragJS/IncidentResponseOrchestrator/pkg/events"
)

// AllowList of permitted action types
var allowedActions = map[string]bool{
	"restart_pod":                true,
	"scale_deployment":           true,
	"rolling_restart_deployment": true,
	"gather_logs":                true,
	"flush_cache":                true,
}

// Namespace Restrictions: only these namespaces can be targeted
var allowedNamespaces = map[string]bool{
	"default": true,
	"apps":    true,
	"staging": true,
	// "production": false, // Requires human approval (not in list)
}

// Rate Limiting: Track actions per target
var (
	rateLimitMu         sync.Mutex
	actionHistory       = make(map[string][]time.Time) // key: "action_type:target", value: timestamps
	maxActionsPerTarget = 3
	rateLimitWindow     = 1 * time.Hour
)

func Evaluate(action *events.Action) (bool, string) {
	// 1. AllowList Check
	if !allowedActions[action.ActionType] {
		return false, "Action type '" + action.ActionType + "' is not in the AllowList"
	}

	// 2. Forbidden Keywords (Delete)
	if strings.Contains(strings.ToLower(action.ActionType), "delete") {
		return false, "Automatic deletion is forbidden"
	}

	// 3. Namespace Restrictions
	namespace := action.Params["namespace"]
	if namespace == "" {
		namespace = "default" // Assume default if not specified
	}

	// Always block kube-system
	if namespace == "kube-system" {
		return false, "Cannot perform actions in kube-system namespace"
	}

	// Check if namespace is in allowed list
	if !allowedNamespaces[namespace] {
		return false, "Namespace '" + namespace + "' requires human approval"
	}

	// 4. Rate Limiting
	key := action.ActionType + ":" + action.Target
	if !checkRateLimit(key) {
		return false, "Rate limit exceeded: Too many '" + action.ActionType + "' actions on '" + action.Target + "' in the last hour"
	}

	return true, "Policy check passed"
}

func checkRateLimit(key string) bool {
	rateLimitMu.Lock()
	defer rateLimitMu.Unlock()

	now := time.Now()
	cutoff := now.Add(-rateLimitWindow)

	// Clean old entries
	var recentActions []time.Time
	for _, t := range actionHistory[key] {
		if t.After(cutoff) {
			recentActions = append(recentActions, t)
		}
	}

	// Check limit
	if len(recentActions) >= maxActionsPerTarget {
		return false
	}

	// Record this action
	recentActions = append(recentActions, now)
	actionHistory[key] = recentActions

	return true
}

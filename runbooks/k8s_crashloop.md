# Kubernetes Pod CrashLoopBackOff Runbook

**Severity**: Critical
**Service**: Kubernetes / Applications
**Keywords**: k8s, crash, restart, oomkilled

## Symptoms
-   Pod status is `CrashLoopBackOff`.
-   Restart count is increasing rapidly.
-   Service is unavailable or degraded.

## Root Causes
1.  **Application Panic**: Unhandled exception on startup.
2.  **Configuration Error**: Missing env vars, invalid config maps, or secrets.
3.  **OOMKilled**: Memory limit exceeded.
4.  **Liveness Probe Failed**: App started but failed health check.

## Troubleshooting Steps
1.  **Describe Pod**:
    `kubectl describe pod <pod-name>`
    - Look at "Last State" and "Events".
    - Check for "OOMKilled" or "Exit Code".

2.  **Check Logs**:
    `kubectl logs <pod-name> --previous`
    - Look for stack traces or error messages just before the crash.

## Remediation Actions
-   **Fix Config**: If "Env var missing", update the deployment/secret.
-   **Increase Memory**: If OOMKilled, increase limits.
    *Action*: (Requires manual YAML edit usually, or Vertical Pod Autoscaler).
-   **Restart Pod**: Sometimes a transient issue (e.g., DB not ready) causes a crash. A restart might fix it if backoff logic is poor.
    *Action*: `restart_pod` (Target: `<pod-name>`)
-   **Rollback**: If this started after a recent deployment.

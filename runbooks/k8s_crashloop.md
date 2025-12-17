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
-   **Rollback**: If this started after a recent deployment, if logs show "Fatal Error" / "Panic", OR if pods are crashing so fast they cannot be inspected (Pod Not Found).
    *Action*: `rollback_deployment` (Target: `deployment/<deployment-name>`)
-   **Restart Deployment**: Only for stuck/unresponsive pods that are NOT crashing repeatedly.
    *Action*: `rolling_restart_deployment` (Target: `deployment/<deployment-name>`)

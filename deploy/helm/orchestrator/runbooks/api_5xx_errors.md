# API High 5xx Error Rate Runbook

**Severity**: High
**Service**: API / REST
**Keywords**: 5xx, 500, internal server error, reliability

## Symptoms
-   Alert: `HighErrorRate` (> 5% of requests are 5xx).
-   Customer complaints about failed transactions.

## Root Causes
1.  **Bad Deployment**: Recent code change introduced a bug.
2.  **Dependency Failure**: Downstream service (DB, Redis, 3rd party) is down.
3.  **Config Error**: Invalid configuration loaded.

## Troubleshooting Steps
1.  **Check Logs**:
    `kail -l app=<app-name>` or use Loki.
    - Look for exceptions causing 500s.

2.  **Check Dependencies**:
    - Is the DB reachable?
    - Are dependent internal services responding?

## Remediation Actions
-   **Rollback**: If caused by a recent deployment.
    *Action*: `rollback_deployment` (Target: `<deployment-name>`)
-   **Restart Pod**: If the issue is transient/stale state.
    *Action*: `restart_pod` (Target: `<pod-name>`)
-   **Circuit Break**: Disable the feature flag for the broken path.
